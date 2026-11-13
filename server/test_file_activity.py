import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from . import server


class FileActivityTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        self.enterContext(patch.dict(os.environ, {"CONTRACT_APPROVAL_TOKEN": "local-test"}))
        server.create_tables()
        self.client = TestClient(server.app)
        self.edit = {"room": "test", "path": "src/todos.py", "author": "Dana", "branch": "dana/todos"}

    def test_overlap_matches_recent_edits_from_other_people_in_same_room(self):
        check = {**self.edit, "author": "Bob"}
        with patch.object(server, "now", return_value="2000-01-01T00:00:00+00:00"):
            self.assertEqual(self.client.post("/files/edits", json=self.edit).status_code, 200)
        self.assertEqual(self.client.post("/files/check", json=check).json()["edits"], [])
        self.assertEqual(self.client.post("/files/edits", json=self.edit).status_code, 200)
        self.assertEqual(self.client.post("/files/check", json=check).json()["edits"][0]["author"], "Dana")
        for separate in (self.edit, {**check, "path": "src/other.py"}, {**check, "room": "other"}):
            self.assertEqual(self.client.post("/files/check", json=separate).json()["edits"], [])
        self.assertEqual(self.client.get("/state?room=test").json()["files"]["edits"][0]["path"], "src/todos.py")

    def test_linked_room_ignores_wrong_checkout_and_rejects_unsafe_paths(self):
        response = self.client.put("/git", headers={"X-Contract-Token": "local-test"}, json={
            "room": "test", "repository": "example/todos", "base_branch": "main",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.post("/files/edits", json=self.edit).status_code, 409)
        linked_edit = {**self.edit, "repository": "example/todos"}
        self.assertEqual(self.client.post("/files/edits", json=linked_edit).status_code, 200)
        for path in ("../todos.py", "/private/todos.py", ".git/config"):
            self.assertEqual(self.client.post("/files/edits", json={**linked_edit, "path": path}).status_code, 422)
