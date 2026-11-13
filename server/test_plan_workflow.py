"""Run with python -m unittest server.test_plan_workflow. No API key needed."""

import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from . import conflicts, server


class PlanWorkflowTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        self.enterContext(patch.dict(os.environ, {"CONTRACT_APPROVAL_TOKEN": "local-test"}))
        server.create_tables()
        self.client = TestClient(server.app)
        self.headers = {"X-Contract-Token": "local-test"}
        self.question = {
            "topic": "get-todos-response",
            "category": "api",
            "question": "What should GET /todos return?",
            "options": ["GET /todos returns an object with an items array."],
        }

    def submit(self, author, room="demo"):
        return self.client.post("/decision-requests", json={"room": room, "author": author, **self.question})

    def answer(self, request_id, headers=None, room="demo"):
        return self.client.post(
            f"/decision-requests/{request_id}/answer",
            json={"room": room, "author": "Reviewer", "text": self.question["options"][0]},
            headers=headers,
        )

    def test_shared_request_and_one_approved_decision(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(self.submit, ["Frontend", "Backend"]))
        self.assertEqual([r.status_code for r in responses], [200, 200])
        a, b = [r.json() for r in responses]
        request_id = a["request"]["id"]
        self.assertEqual(request_id, b["request"]["id"])
        self.assertNotEqual(a["created"], b["created"])
        self.assertNotEqual(request_id, self.submit("Other", "other").json()["request"]["id"])
        self.assertIn(self.question["question"], self.client.get("/contract?room=demo").json()["text"])
        self.assertEqual(self.answer(request_id).status_code, 403)
        self.assertEqual(self.answer(request_id, self.headers, "other").status_code, 404)
        with ThreadPoolExecutor(max_workers=2) as executor:
            answers = list(executor.map(lambda _: self.answer(request_id, self.headers), range(2)))
        self.assertEqual(sorted(r.status_code for r in answers), [200, 409])
        contract = self.client.get("/contract?room=demo").json()
        self.assertEqual([d["text"] for d in contract["decisions"]], self.question["options"])
        self.assertNotIn(self.question["question"], contract["text"])
        self.assertEqual(self.submit("Later").json()["decision"], contract["decisions"][0])
        self.assertEqual(self.client.post("/reset?room=demo").status_code, 403)

    def test_plan_review_reports_conflict_and_gap_without_writing(self):
        decision = server.save_decision(server.NewDecision(
            room="demo", author="Ali", category="stack", text="Use FastAPI."
        ))
        review = conflicts.PlanReview(
            conflicts=[{"existing_id": decision["id"], "explanation": "Express contradicts FastAPI."}],
            missing_decisions=[self.question],
        )
        body = {"room": "demo", "author": "Frontend", "plan": "Use Express and list todos."}
        with patch.object(conflicts, "check_plan", return_value=review):
            response = self.client.post("/plans/check", json=body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["conflicts"][0]["decision"], decision)
        self.assertEqual(response.json()["missing_decisions"], [self.question])
        state = self.client.get("/state?room=demo").json()
        self.assertEqual(state["decisions"], [decision])
        self.assertEqual(state["conflicts"], [])
        self.assertEqual(state["decision_requests"], [])
        with patch.object(conflicts, "check_plan", side_effect=conflicts.CheckerUnavailable()):
            self.assertEqual(self.client.post("/plans/check", json=body).status_code, 503)

    def test_conflicting_or_unchecked_answer_leaves_request_open(self):
        original = server.save_decision(server.NewDecision(
            room="demo", author="Ali", category="api", text="GET /todos returns a bare array."
        ))
        request_id = self.submit("Frontend").json()["request"]["id"]
        with patch.object(conflicts, "check_decision", return_value=conflicts.Verdict(
            verdict="conflict", existing_id=original["id"], explanation="The response shapes differ."
        )):
            self.assertEqual(self.answer(request_id, self.headers).status_code, 409)
        with patch.object(conflicts, "check_decision", side_effect=conflicts.CheckerUnavailable()):
            self.assertEqual(self.answer(request_id, self.headers).status_code, 503)
        state = self.client.get("/state?room=demo").json()
        self.assertIsNone(state["decision_requests"][0]["decision_id"])
        self.assertEqual(state["decisions"], [original])
