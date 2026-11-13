import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from coord import git_sync
from . import server


class RoomGitTest(unittest.TestCase):
    def test_room_link_and_activity(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        self.enterContext(patch.dict(os.environ, {"CONTRACT_APPROVAL_TOKEN": "local-test"}))
        server.create_tables()
        client = TestClient(server.app)
        link = {"room": "demo", "repository": "Example/Todos", "base_branch": "main"}
        headers = {"X-Contract-Token": "local-test"}
        self.assertEqual(client.put("/git", json=link).status_code, 403)
        self.assertEqual(client.get("/git/link-access").status_code, 403)
        self.assertEqual(client.get("/git/link-access", headers=headers).status_code, 200)
        for _ in range(2):
            self.assertEqual(client.put("/git", json=link, headers=headers).status_code, 200)
        changed = {**link, "base_branch": "other"}
        self.assertEqual(client.put("/git", json=changed, headers=headers).status_code, 409)
        activity = {**link, "author": "Ali", "branch": "ali/api", "ahead": 2, "behind": 1, "pr_number": 17}
        self.assertEqual(client.post("/git/activity", json={**activity, "room": "other"}).status_code, 409)
        self.assertEqual(client.post("/git/activity", json=activity).status_code, 200)
        self.assertEqual(client.post("/git/activity", json={**activity, "behind": 0}).status_code, 200)
        state = client.get("/state?room=demo").json()["git"]
        self.assertEqual(state["repository"]["repository"], "example/todos")
        self.assertEqual(len(state["activity"]), 1)
        self.assertEqual(state["activity"][0]["pr_number"], 17)
        self.assertEqual(state["activity"][0]["behind"], 0)
        self.assertIsNone(state["activity"][0]["pr_state"])
        self.assertEqual(client.post("/git/activity", json={**activity, "pr_state": "in_review"}).status_code, 200)
        self.assertEqual(client.get("/state?room=demo").json()["git"]["activity"][0]["pr_state"], "in_review")


class PublishTest(unittest.TestCase):
    def test_ready_publish_creates_reviewable_pr_or_promotes_existing_draft(self):
        url = "https://github.com/example/todos/pull/17"
        with patch.object(git_sync, "command", side_effect=["", "", url]) as run, \
                patch.object(git_sync, "open_pr", return_value=None):
            pr = git_sync.publish("example/todos", "ali/api", "main", 1, "API work", ready=True)
        self.assertEqual(git_sync.pull_request_state(pr), "in_review")
        self.assertIn("--set-upstream", run.call_args_list[1].args)
        self.assertNotIn("--draft", run.call_args.args)

        draft = {"number": 17, "url": url, "isDraft": True}
        with patch.object(git_sync, "command", return_value="") as run, \
                patch.object(git_sync, "open_pr", return_value=draft):
            pr = git_sync.publish("example/todos", "ali/api", "main", 1, None, ready=True)
        run.assert_called_with("gh", "pr", "ready", "17", "--repo", "github.com/example/todos")
        self.assertEqual(git_sync.pull_request_state(pr), "in_review")

    def test_create_private_repository_checks_approval_before_push(self):
        commands = []
        operations = []

        def run(*args):
            commands.append(args)
            if args == ("git", "branch", "--show-current"):
                return "main"
            if args[:3] == ("gh", "repo", "view"):
                return '{"defaultBranchRef":{"name":"main"}}'
            return ""

        def call(me, method, path, body=None, token=""):
            operations.append((method, path))
            if path.startswith("/git?"):
                return {"repository": None}
            self.assertEqual(token, "local-test")
            if path == "/git/link-access?room=demo":
                self.assertFalse(any(args[:3] == ("gh", "repo", "create") for args in commands))
            return {"ok": True}

        me = {"room": "demo"}
        with patch.object(git_sync, "command", run), patch.object(git_sync, "api", call), \
                patch.object(git_sync, "approval_token", return_value="local-test"), \
                patch.object(git_sync, "origin_repository", return_value="example/todos"):
            git_sync.create_repository(me, "Example/Todos")
        create = next(args for args in commands if args[:3] == ("gh", "repo", "create"))
        self.assertIn("--private", create)
        self.assertIn("--push", create)
        self.assertEqual(operations[-2:], [("GET", "/git/link-access?room=demo"), ("PUT", "/git")])

    def test_two_pushes_reuse_one_draft_and_fetch_preserves_local_work(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            repo = path / "client"
            repo.mkdir()

            def git(*args):
                return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()

            git("init", "-q", "-b", "main")
            git("config", "user.name", "Team Contract Test")
            git("config", "user.email", "test@example.invalid")
            git("commit", "-q", "--allow-empty", "-m", "Initial commit")
            git("init", "-q", "--bare", str(path / "remote.git"))
            git("remote", "add", "origin", str(path / "remote.git"))
            git("push", "-q", "origin", "main")
            git("switch", "-q", "-c", "ali/api")
            git("commit", "-q", "--allow-empty", "-m", "API work")
            (repo / "unfinished.txt").write_text("local work")
            self.assertEqual(git_sync.github_repository("git@github.com:Example/Todos.git"), "example/todos")
            with self.assertRaises(ValueError):
                git_sync.github_repository("https://github.com@other.example/Example/Todos")
            commands = git_sync.command
            pr_calls = []
            reports = []

            def fake_command(*args):
                if args[0] == "git":
                    return commands(*args)
                if args[:3] == ("gh", "pr", "list"):
                    return json.dumps([{"number": 17, "url": "https://github.com/example/todos/pull/17",
                                        "isCrossRepository": False, "isDraft": True}] if pr_calls else [])
                self.assertEqual(args[:3], ("gh", "pr", "create"))
                self.assertIn("--draft", args)
                pr_calls.append(args)
                return "https://github.com/example/todos/pull/17"

            def fake_api(me, method, path, body=None):
                if method == "GET":
                    return {"repository": {"repository": "example/todos", "base_branch": "main"}}
                reports.append(body)
                return {"ok": True}

            me = {"room": "demo", "name": "Ali"}
            with patch.object(git_sync, "PROJECT", repo), patch.object(git_sync, "command", fake_command), \
                    patch.object(git_sync, "api", fake_api):
                git_sync.sync(me, "example/todos", "publish", "API work")
                self.assertEqual(git("rev-parse", "--abbrev-ref", "@{upstream}"), "origin/ali/api")
                git("commit", "-q", "--allow-empty", "-m", "Follow-up")
                git_sync.sync(me, "example/todos", "publish", None)
                local_head = git("rev-parse", "HEAD")
                git("switch", "-q", "main")
                git("commit", "-q", "--allow-empty", "-m", "Teammate work")
                git("push", "-q", "origin", "main")
                latest_shared = git("rev-parse", "HEAD")
                git("switch", "-q", "ali/api")
                git_sync.sync(me, "example/todos", "status", None)
                self.assertEqual(git("rev-parse", "HEAD"), local_head)
                self.assertEqual((repo / "unfinished.txt").read_text(), "local work")
                self.assertEqual(reports[-1]["behind"], 1)
                self.assertEqual([r["pr_number"] for r in reports], [17, 17, 17])
                self.assertEqual(len(pr_calls), 1)
                with self.assertRaisesRegex(ValueError, "unsaved edits on ali/api"):
                    git_sync.start_task("example/todos", "main", "ali/next")
                (repo / "unfinished.txt").unlink()
                with self.assertRaisesRegex(ValueError, "already exists"):
                    git_sync.start_task("example/todos", "main", "ali/api")
                git_sync.start_task("example/todos", "main", "ali/next")
                self.assertEqual(git("branch", "--show-current"), "ali/next")
                self.assertEqual(git("rev-parse", "HEAD"), latest_shared)
                self.assertEqual(git("rev-parse", "ali/api"), local_head)
