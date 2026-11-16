"""Run with python -m unittest server.test_code_view. No API key needed."""

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from . import server

spec = importlib.util.spec_from_file_location("live_sync_test", server.PROJECT_ROOT / "coord/live_sync.py")
live_sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live_sync)

KEY = {"X-Contract-Token": "view-key-123"}


class CodeViewTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        server.create_tables()
        self.client = TestClient(server.app)
        self.client.post("/rooms/key", json={"room": "code", "author": "Ali", "key": KEY["X-Contract-Token"]})

    def upload(self, files, author="Ali", room="code", **extra):
        reply = self.client.post("/code/files", json={"room": room, "author": author, "files": files, **extra})
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()

    def tree(self):
        return self.client.get("/code/tree?room=code", headers=KEY).json()

    def test_a_room_without_a_team_key_keeps_no_code(self):
        reply = self.upload([{"path": "a.py", "content": "x = 1"}], room="open")
        self.assertFalse(reply["stored"])
        self.assertIn("team key", reply["reason"])
        self.client.post("/files/edits", json={"room": "open", "author": "Ali", "path": "a.py", "content": "SECRET_CODE"})
        self.assertNotIn(b"SECRET_CODE", server.DB_PATH.read_bytes())
        self.assertEqual(self.client.get("/code/tree?room=open").status_code, 503)

    def test_reading_needs_the_team_key(self):
        self.upload([{"path": "a.py", "content": "x = 1"}])
        for address in ("/code/tree?room=code", "/code/changes?room=code", "/code/file?room=code&author=Ali&path=a.py"):
            self.assertEqual(self.client.get(address).status_code, 403, address)
            self.assertEqual(self.client.get(address, headers={"X-Contract-Token": "wrong"}).status_code, 403, address)
            self.assertEqual(self.client.get(address, headers=KEY).status_code, 200, address)
        # The open dashboard state never carries file text.
        self.assertNotIn("x = 1", self.client.get("/state?room=code").text)

    def test_files_are_kept_per_teammate_and_changes_are_numbered(self):
        self.upload([{"path": "src/a.py", "content": "x = 1"}, {"path": "logo.png", "note": "binary file"}],
                    branch="ali/work", paths=["src/a.py", "logo.png"])
        self.upload([{"path": "src/a.py", "content": "x = 2"}], author="Mei")
        tree = self.tree()
        self.assertEqual([person["author"] for person in tree["people"]], ["Ali", "Mei"])
        self.assertEqual(tree["people"][0]["branch"], "ali/work")
        self.assertEqual([(file["path"], file["note"]) for file in tree["people"][0]["files"]],
                         [("logo.png", "binary file"), ("src/a.py", None)])
        file = self.client.get("/code/file?room=code&author=Mei&path=src/a.py", headers=KEY).json()
        self.assertEqual((file["content"], file["bytes"]), ("x = 2", 5))
        self.assertEqual(self.client.get("/code/file?room=code&author=Mei&path=nope.py", headers=KEY).status_code, 404)

        seq = tree["seq"]
        self.assertEqual(self.upload([{"path": "src/a.py", "content": "x = 1"}])["changed"], 0)   # same text
        self.assertEqual(self.client.get(f"/code/changes?room=code&after={seq}", headers=KEY).json()["files"], [])
        self.upload([{"path": "src/a.py", "content": "x = 3"}])
        changes = self.client.get(f"/code/changes?room=code&after={seq}", headers=KEY).json()
        self.assertEqual([(file["author"], file["path"]) for file in changes["files"]], [("Ali", "src/a.py")])
        self.assertEqual(changes["counts"], {"Ali": 2, "Mei": 1})
        self.assertGreater(changes["seq"], seq)

    def test_the_last_upload_removes_files_that_are_gone(self):
        self.upload([{"path": "a.py", "content": "1"}, {"path": "b.py", "content": "2"}])
        self.assertEqual(self.upload([], paths=["a.py"])["removed"], 1)
        self.assertEqual([file["path"] for file in self.tree()["people"][0]["files"]], ["a.py"])

    def test_secret_files_and_bad_input(self):
        self.upload([{"path": ".env", "content": "TOKEN=abc"}, {"path": "keys/id_rsa", "content": "PRIVATE"}])
        self.assertNotIn(b"TOKEN=abc", server.DB_PATH.read_bytes())
        self.assertNotIn(b"PRIVATE", server.DB_PATH.read_bytes())
        self.assertEqual({file["note"] for file in self.tree()["people"][0]["files"]}, {"secret file, not shared"})
        for bad in ([{"path": "../a.py", "content": "x"}], [{"path": "a.py", "content": "x" * (server.CODE_FILE_LIMIT + 1)}],
                    [{"path": "a.py", "content": "x"}] * (server.CODE_BATCH + 1)):
            reply = self.client.post("/code/files", json={"room": "code", "author": "Ali", "files": bad})
            self.assertEqual(reply.status_code, 422)

    def test_an_edit_report_updates_the_file_and_asks_for_the_project_once(self):
        edit = {"room": "code", "author": "Ali", "path": "src/a.py", "content": "x = 1\n", "diff": "@@\n+x = 1"}
        self.assertTrue(self.client.post("/files/edits", json=edit).json()["sync"])
        self.assertEqual(self.client.get("/code/file?room=code&author=Ali&path=src/a.py", headers=KEY).json()["content"], "x = 1\n")
        self.upload([], paths=["src/a.py"])                                   # the project was sent
        self.assertFalse(self.client.post("/files/edits", json=edit).json()["sync"])
        long = {**edit, "content": "x" * (server.CODE_FILE_LIMIT + 1)}        # too long: the report still counts
        self.assertEqual(self.client.post("/files/edits", json=long).status_code, 200)
        self.assertEqual(self.client.get("/code/file?room=code&author=Ali&path=src/a.py", headers=KEY).json()["content"], "x = 1\n")

    def test_reset_clears_the_code_and_the_page_is_served(self):
        self.upload([{"path": "a.py", "content": "x = 1"}], paths=["a.py"])
        self.assertEqual(self.client.post("/reset?room=code", headers=KEY).status_code, 200)
        self.assertNotIn(b"x = 1", server.DB_PATH.read_bytes())
        page = self.client.get("/ide?room=code")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Read-only", page.text)


class ProjectSyncTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(live_sync, "ROOT", self.root))
        self.enterContext(patch.object(live_sync, "STATE", self.root / "coord/.state/live-sync.json"))
        self.sent = []
        self.reply = {"stored": True, "removed": 0}
        self.enterContext(patch.object(live_sync, "post", lambda me, body: self.sent.append(body) or self.reply))
        self.me = {"name": "Ali", "room": "code", "server": "http://unused"}
        for path, data in {"src/app.py": b"print(1)\n", "README.md": b"# hi\n", ".env": b"TOKEN=abc\n",
                           "logo.png": b"\x89PNG\0\0", "big.txt": b"x" * (live_sync.FILE_LIMIT + 1),
                           "coord/team.py": b"tool", ".claude/settings.json": b"{}", "coopdev": b"#!/bin/sh"}.items():
            file = self.root / path
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)

    def files(self):
        return {file["path"]: (file["content"], file["note"]) for body in self.sent for file in body["files"]}

    def test_sends_text_lists_the_rest_and_skips_the_tool(self):
        self.assertEqual(live_sync.sync(self.me), "Code view updated: 5 files, 5 sent, 0 removed.")
        self.assertEqual(self.files(), {
            "src/app.py": ("print(1)\n", None), "README.md": ("# hi\n", None),
            ".env": (None, "secret file, not shared"), "logo.png": (None, "binary file"),
            "big.txt": (None, "larger than 200 KB"),
        })
        self.assertEqual(self.sent[-1]["paths"], [".env", "README.md", "big.txt", "logo.png", "src/app.py"])
        self.assertNotIn("TOKEN=abc", json.dumps(self.sent))

    def test_second_run_sends_only_what_changed(self):
        live_sync.sync(self.me)
        self.sent.clear()
        (self.root / "src/app.py").write_text("print(2)\n")
        (self.root / "README.md").unlink()
        self.assertIn("4 files, 1 sent", live_sync.sync(self.me))
        self.assertEqual(self.files(), {"src/app.py": ("print(2)\n", None)})
        self.assertNotIn("README.md", self.sent[-1]["paths"])

    def test_switched_off_or_no_team_key(self):
        self.assertIn("Nothing sent", live_sync.sync({**self.me, "live": False}))
        self.assertEqual(self.sent, [])
        self.reply = {"stored": False}
        self.assertIn("no team key", live_sync.sync(self.me))
        self.assertFalse(live_sync.STATE.exists())   # so the next run sends everything again

    def test_a_git_project_leaves_out_ignored_files(self):
        (self.root / ".gitignore").write_text("big.txt\n")
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        self.assertNotIn("big.txt", live_sync.project_files())
        self.assertIn("src/app.py", live_sync.project_files())


if __name__ == "__main__":
    unittest.main()
