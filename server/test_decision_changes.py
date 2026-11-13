"""Run with python -m unittest server.test_decision_changes. No API key needed."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from . import conflicts, server


def verdict(kind, existing_id=0, explanation=""):
    return conflicts.Verdict(verdict=kind, existing_id=existing_id, explanation=explanation)


class DecisionChangesTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        self.enterContext(patch.dict(os.environ))
        os.environ.pop("CONTRACT_APPROVAL_TOKEN", None)
        server.create_tables()
        self.client = TestClient(server.app)
        self.key = {"X-Contract-Token": "our-team-key"}
        self.me = {"room": "demo", "author": "Dana"}

    def record(self, text, author="Ali", category="stack", check=None):
        body = {"room": "demo", "author": author, "category": category, "text": text}
        with patch.object(conflicts, "check_decision", return_value=check or verdict("ok")):
            return self.client.post("/decisions", json=body).json()

    def set_key(self, room="demo", key="our-team-key"):
        return self.client.post("/rooms/key", json={"room": room, "author": "Dana", "key": key})

    def contract(self, name=None):
        query = "/contract?room=demo" + (f"&name={name}" if name else "")
        return self.client.get(query).json()

    def state(self):
        return self.client.get("/state?room=demo").json()

    def test_team_key_is_set_once_and_guards_human_actions(self):
        django = self.record("Backend is Django.")["decision"]
        retire = f"/decisions/{django['id']}/retire"
        self.assertFalse(self.state()["approval_enabled"])
        self.assertEqual(self.client.post(retire, json=self.me, headers=self.key).status_code, 503)
        self.assertEqual(self.set_key(key="short").status_code, 422)
        self.assertEqual(self.set_key().status_code, 200)
        self.assertEqual(self.set_key(key="another-key-1").status_code, 409)
        state = self.state()
        self.assertTrue(state["approval_enabled"] and state["room_key"])
        self.assertNotIn("our-team-key", Path(server.DB_PATH).read_bytes().decode(errors="ignore"))
        for headers in (None, {"X-Contract-Token": "wrong-key-123"}):
            self.assertEqual(self.client.post(retire, json=self.me, headers=headers).status_code, 403)
        # A key belongs to one room, and a reset needs it but does not remove it.
        self.assertEqual(self.client.post("/reset?room=demo").status_code, 403)
        self.assertEqual(self.client.post("/reset?room=other", headers=self.key).status_code, 200)
        self.assertEqual(self.client.post("/reset?room=demo", headers=self.key).status_code, 200)
        self.assertTrue(self.state()["room_key"])
        with patch.dict(os.environ, {"CONTRACT_APPROVAL_TOKEN": "server-token"}):
            admin = {"X-Contract-Token": "server-token"}
            self.assertEqual(self.client.post("/reset?room=demo", headers=admin).status_code, 200)
            self.assertEqual(self.client.get("/git/link-access?room=demo", headers=self.key).status_code, 200)
            self.assertEqual(self.client.get("/git/link-access", headers=self.key).status_code, 403)

    def test_keep_closes_the_conflict_and_changes_nothing(self):
        self.set_key()
        django = self.record("Backend is Django.")["decision"]
        clash = verdict("conflict", django["id"], "Django and Express are two backends.")
        first = self.record("Backend is Express.", "Mei", check=clash)["conflict"]
        again = self.record("backend is express.", "Mei", check=clash)["conflict"]
        self.assertEqual(first["id"], again["id"])  # a repeated request is not logged twice
        resolve = f"/conflicts/{first['id']}/resolve"
        body = {**self.me, "action": "keep"}
        self.assertEqual(self.client.post(resolve, json=body).status_code, 403)
        self.assertEqual(self.client.post(resolve, json=body, headers=self.key).status_code, 200)
        self.assertEqual(self.client.post(resolve, json=body, headers=self.key).status_code, 409)
        state = self.state()
        self.assertEqual([d["text"] for d in state["decisions"]], ["Backend is Django."])
        self.assertEqual(state["conflicts"][0]["resolution"], "kept")
        self.assertEqual(state["conflicts"][0]["resolved_by"], "Dana")
        self.assertEqual(self.client.post("/conflicts/999/resolve", json=body, headers=self.key).status_code, 404)

    def test_replace_swaps_the_decision_and_tells_teammates(self):
        self.set_key()
        django = self.record("Backend is Django.")["decision"]
        port = self.record("The API runs on port 8001.", category="api")["decision"]
        self.contract("Ali")  # Ali's agent has now seen the contract
        clash = verdict("conflict", django["id"], "Django and FastAPI are two backends.")
        one = self.record("Backend is FastAPI.", "Mei", check=clash)["conflict"]
        two = self.record("Backend is Express.", "Omar", check=clash)["conflict"]
        resolve = f"/conflicts/{one['id']}/resolve"
        body = {**self.me, "action": "replace"}

        with patch.object(conflicts, "check_decision", side_effect=conflicts.CheckerUnavailable()):
            self.assertEqual(self.client.post(resolve, json=body, headers=self.key).status_code, 503)
        with patch.object(conflicts, "check_decision", return_value=verdict("conflict", port["id"], "Ports differ.")):
            blocked = self.client.post(resolve, json=body, headers=self.key)
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("port 8001", blocked.json()["detail"])
        self.assertEqual(len(self.state()["decisions"]), 2)  # nothing changed so far

        with patch.object(conflicts, "check_decision", return_value=verdict("ok")) as check:
            done = self.client.post(resolve, json=body, headers=self.key)
        self.assertEqual(done.status_code, 200)
        self.assertEqual([d["id"] for d in check.call_args.args[2]], [port["id"]])  # not checked against the old one
        state = self.state()
        self.assertEqual([d["text"] for d in state["decisions"]], ["The API runs on port 8001.", "Backend is FastAPI."])
        self.assertEqual(state["decisions"][1]["author"], "Mei")
        retired = state["retired_decisions"][0]
        self.assertEqual((retired["text"], retired["retired_by"], retired["replaced_by_text"]),
                         ("Backend is Django.", "Dana", "Backend is FastAPI."))
        by_id = {c["id"]: c["resolution"] for c in state["conflicts"]}
        self.assertEqual(by_id, {one["id"]: "replaced", two["id"]: "outdated"})

        text = self.contract("Ali")["text"]
        self.assertNotIn("ADDED by Mei", text)  # the swap is reported once, on the RETIRED line
        self.record("Tests use pytest.", "Mei", "convention")
        self.assertIn("ADDED by Mei: [convention] Tests use pytest.", self.contract("Ali")["text"])
        self.assertIn("RETIRED by Dana: [stack] Backend is Django. It is replaced by: Backend is FastAPI.", text)
        self.assertNotIn("- [stack] Backend is Django. (by Ali)", text)
        self.assertNotIn("Changed by the team", self.contract("Mei")["text"])  # first read: nothing to compare

    def test_retire_reopens_the_request_it_answered(self):
        self.set_key()
        question = {"room": "demo", "author": "Mei", "topic": "todos-shape", "category": "api",
                    "question": "What does GET /todos return?", "options": ["GET /todos returns a list."]}
        request_id = self.client.post("/decision-requests", json=question).json()["request"]["id"]
        answer = {**self.me, "text": question["options"][0]}
        saved = self.client.post(f"/decision-requests/{request_id}/answer", json=answer, headers=self.key)
        self.assertEqual(saved.status_code, 200)  # the room's own key approves, no server token needed
        decision_id = saved.json()["decision"]["id"]
        retire = f"/decisions/{decision_id}/retire"
        self.assertEqual(self.client.post(retire, json=self.me, headers=self.key).status_code, 200)
        self.assertEqual(self.client.post(retire, json=self.me, headers=self.key).status_code, 409)
        state = self.state()
        self.assertEqual(state["decisions"], [])
        self.assertIsNone(state["decision_requests"][0]["decision_id"])
        self.assertIn("What does GET /todos return?", self.contract()["text"])

    def test_old_database_files_gain_the_new_columns(self):
        with server.connect() as conn:
            conn.execute("DROP TABLE decisions")
            conn.execute("CREATE TABLE decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, room TEXT NOT NULL, "
                         "author TEXT NOT NULL, category TEXT NOT NULL, text TEXT NOT NULL, created_at TEXT NOT NULL)")
            conn.execute("INSERT INTO decisions (room, author, category, text, created_at) "
                         "VALUES ('demo', 'Ali', 'stack', 'Old row.', '2026-01-01T00:00:00+00:00')")
        server.create_tables()
        self.assertEqual([d["text"] for d in self.state()["decisions"]], ["Old row."])
