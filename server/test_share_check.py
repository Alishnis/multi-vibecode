"""Run with python -m unittest server.test_share_check. No API key needed."""

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from coord import git_sync
from . import conflicts, server

HOOK = server.PROJECT_ROOT / "coord/hooks/file_activity.py"


class ShareCheckServerTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        server.create_tables()
        self.client = TestClient(server.app)
        self.share = {"room": "demo", "author": "Mei", "branch": "mei/api",
                      "files": ["app.js"], "diff": "+const express = require('express')"}

    def test_findings_name_the_decision_and_only_findings_are_stored(self):
        self.assertEqual(self.client.post("/shares/check", json=self.share).json(),
                         {"check": "not needed", "findings": []})
        decision = server.save_decision(server.NewDecision(
            room="demo", author="Ali", category="stack", text="Backend is FastAPI."))
        review = conflicts.ShareReview(findings=[
            {"existing_id": decision["id"], "file": "app.js", "explanation": "Uses Express,\nnot FastAPI."},
            {"existing_id": 999, "file": "x", "explanation": "An id the checker made up."},
        ])
        with patch.object(conflicts, "check_share", return_value=review) as check:
            reply = self.client.post("/shares/check", json=self.share).json()
        self.assertEqual(check.call_args.args[0], self.share["diff"])
        self.assertEqual(reply["findings"], [{
            "decision_id": decision["id"], "decision": "Backend is FastAPI.", "decided_by": "Ali",
            "file": "app.js", "explanation": "Uses Express, not FastAPI.",
        }])
        checks = self.client.get("/state?room=demo").json()["git"]["checks"]
        self.assertEqual([(c["author"], c["branch"], len(c["findings"])) for c in checks], [("Mei", "mei/api", 1)])
        self.assertNotIn(b"require('express')", Path(server.DB_PATH).read_bytes())
        # A later clean check replaces the warning. An unavailable checker changes nothing.
        with patch.object(conflicts, "check_share", side_effect=conflicts.CheckerUnavailable("down")):
            self.assertEqual(self.client.post("/shares/check", json=self.share).json(),
                             {"check": "skipped: down", "findings": []})
        self.assertEqual(len(self.client.get("/state?room=demo").json()["git"]["checks"][0]["findings"]), 1)
        with patch.object(conflicts, "check_share", return_value=conflicts.ShareReview(findings=[])):
            self.client.post("/shares/check", json=self.share)
        self.assertEqual(self.client.get("/state?room=demo").json()["git"]["checks"][0]["findings"], [])
        self.assertEqual(self.client.post("/shares/check", json={**self.share, "diff": "x" * 20001}).status_code, 422)


class PublishCheckTest(unittest.TestCase):
    """publish asks the server before pushing, and stops when the code breaks a decision."""

    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.repo = directory / "client"
        self.repo.mkdir()
        self.enterContext(patch.object(git_sync, "PROJECT", self.repo))
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Team Contract Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.repo / "app.py").write_text("print('v1')\n")
        self.git("add", "app.py")
        self.git("commit", "-q", "-m", "Baseline")
        self.git("init", "-q", "--bare", str(directory / "remote.git"))
        self.git("remote", "add", "origin", str(directory / "remote.git"))
        self.git("push", "-q", "origin", "main")
        self.git("switch", "-q", "-c", "mei/api")
        (self.repo / "server.js").write_text("const express = require('express')\n")
        (self.repo / "coord").mkdir()
        (self.repo / "coord/tool.py").write_text("# Team Contract's own file\n")
        self.git("add", "server.js", "coord/tool.py")
        self.git("commit", "-q", "-m", "Add Express server")
        self.finding = {"decision_id": 1, "decision": "Backend is FastAPI.", "decided_by": "Ali",
                        "file": "server.js", "explanation": "Uses Express, not FastAPI."}
        self.sent = []

    def git(self, *args):
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True).strip()

    def publish(self, reply, me=None, **options):
        real = git_sync.command

        def fake_command(*args):
            if args[0] == "git":
                return real(*args)
            return "[]" if args[:3] == ("gh", "pr", "list") else "https://github.com/example/todos/pull/5"

        def fake_api(me, method, path, body=None, token="", timeout=15):
            if method == "GET":
                return {"repository": {"repository": "example/todos", "base_branch": "main"}}
            if path == "/shares/check":
                self.sent.append(body)
                if isinstance(reply, Exception):
                    raise reply
                return reply
            return {"ok": True}

        output = io.StringIO()
        with patch.object(git_sync, "command", fake_command), patch.object(git_sync, "api", fake_api), \
                patch("sys.stdout", output):
            git_sync.sync(me or {"room": "demo", "name": "Mei"}, "example/todos", "publish", None, True, **options)
        return output.getvalue()

    def pushed(self):
        return "mei/api" in self.git("ls-remote", "--heads", "origin")

    def test_broken_decision_stops_the_push_until_the_person_insists(self):
        with self.assertRaises(ValueError) as stopped:
            self.publish({"check": "checked", "findings": [self.finding]})
        message = str(stopped.exception)
        for part in ("Not shared", "server.js: Uses Express, not FastAPI.", "Backend is FastAPI.", "publish --anyway"):
            self.assertIn(part, message)
        self.assertFalse(self.pushed())
        # Only project code is sent: Team Contract's own files are left out.
        self.assertEqual(self.sent[0]["files"], ["server.js"])
        self.assertIn("require('express')", self.sent[0]["diff"])
        self.assertNotIn("Team Contract's own file", self.sent[0]["diff"])
        said = self.publish({"check": "checked", "findings": [self.finding]}, anyway=True)
        self.assertIn("Shared although this code breaks a team decision", said)
        self.assertTrue(self.pushed())

    def test_clean_or_unavailable_check_lets_the_push_through(self):
        self.assertIn("no contradictions detected", self.publish({"check": "checked", "findings": []}))
        self.assertTrue(self.pushed())
        self.git("commit", "-q", "--allow-empty", "-m", "More")
        self.assertIn("did not run (no key)", self.publish({"check": "skipped: no key", "findings": []}))
        self.git("commit", "-q", "--allow-empty", "-m", "More again")
        self.assertIn("could not run", self.publish(ValueError("HTTP 404")))  # an older server

    def test_the_check_can_be_switched_off(self):
        self.publish({"check": "checked", "findings": [self.finding]}, check=False)
        self.git("commit", "-q", "--allow-empty", "-m", "More")
        self.publish({"check": "checked", "findings": [self.finding]},
                     me={"room": "demo", "name": "Mei", "check_code": False})
        self.assertEqual(self.sent, [])  # nothing left the computer
        self.assertTrue(self.pushed())


class OverlapPauseTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        server.create_tables()
        self.client = TestClient(server.app)

    def edit(self, author, when):
        with patch.object(server, "now", return_value=when), \
                patch.object(server, "recent_file_cutoff", return_value="2030-01-01T00:00:00+00:00"):
            self.client.post("/files/edits", json={"room": "demo", "author": author, "path": "src/todos.py"})

    def asked(self, author):
        with patch.object(server, "recent_file_cutoff", return_value="2030-01-01T00:00:00+00:00"):
            reply = self.client.post("/files/check", json={"room": "demo", "author": author, "path": "src/todos.py"})
        return [edit["author"] for edit in reply.json()["edits"]]

    def test_a_person_is_asked_once_until_a_teammate_edits_again(self):
        self.edit("Ali", "2030-01-01T10:00:00+00:00")
        self.assertEqual(self.asked("Mei"), ["Ali"])       # Mei is asked before her first edit
        self.edit("Mei", "2030-01-01T10:05:00+00:00")      # she allowed it and edited
        self.assertEqual(self.asked("Mei"), [])            # her next edits go straight through
        self.assertEqual(self.asked("Ali"), ["Mei"])       # Ali is asked: Mei changed it after him
        self.edit("Ali", "2030-01-01T10:10:00+00:00")
        self.assertEqual(self.asked("Mei"), ["Ali"])       # and Mei again, after Ali's new edit

    def hook_output(self, me):
        """Run the real hook script against a canned server reply."""
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "coord/hooks").mkdir(parents=True)
            for name in ("hooks/file_activity.py", "git_sync.py", "tc_http.py"):
                (project / "coord" / name).write_text((server.PROJECT_ROOT / "coord" / name).read_text())
            (project / "coord/me.json").write_text(json.dumps({"name": "Mei", "room": "demo", "server": "http://x", **me}))
            (project / "coord/tc_http.py").write_text(
                "import io, json\n"
                "def urlopen(request, timeout, handlers=()):\n"
                "    return io.BytesIO(json.dumps({'edits': [{'author': 'Ali', 'branch': 'main', "
                "'edited_at': '2030-01-01T10:00:00+00:00'}]}).encode())\n")
            event = {"hook_event_name": "PreToolUse", "tool_name": "Edit", "cwd": str(project),
                     "tool_input": {"file_path": str(project / "src/todos.py")}}
            run = subprocess.run([sys.executable, str(project / "coord/hooks/file_activity.py")],
                                 input=json.dumps(event), capture_output=True, text=True, timeout=30)
        return json.loads(run.stdout)

    def test_hook_pauses_the_edit_by_default_and_can_be_set_to_a_note(self):
        paused = self.hook_output({})["hookSpecificOutput"]
        self.assertEqual((paused["hookEventName"], paused["permissionDecision"]), ("PreToolUse", "ask"))
        self.assertIn("Ali on main", paused["permissionDecisionReason"])
        self.assertIn("src/todos.py", paused["permissionDecisionReason"])
        noted = self.hook_output({"overlap": "note"})
        self.assertNotIn("permissionDecision", noted["hookSpecificOutput"])
        self.assertIn("FILE OVERLAP", noted["hookSpecificOutput"]["additionalContext"])
