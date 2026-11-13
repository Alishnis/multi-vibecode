import tempfile
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from coord import git_sync


class GitWatchTest(unittest.TestCase):
    def test_cli_defaults_to_every_merge_and_allows_explicit_approval_filter(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "coord").mkdir()
            (root / "coord/me.json").write_text(json.dumps({"name": "Mei", "room": "test"}))
            for flags, expected in (([], True), (["--any-merge"], True), (["--approved-only"], False)):
                with self.subTest(flags=flags), patch.object(git_sync, "PROJECT", root), \
                        patch.object(sys, "argv", ["git_sync.py", "watch", "--once", *flags]), \
                        patch.object(git_sync, "command", return_value=str(root)), \
                        patch.object(git_sync, "origin_repository", return_value="example/todos"), \
                        patch.object(git_sync, "linked_base", return_value="main"), \
                        patch.object(git_sync, "watch") as watch:
                    git_sync.main()
                    self.assertEqual(watch.call_args.args[-1], expected)

    def test_one_check_applies_approved_merge_and_exits_without_sleep(self):
        with patch.object(git_sync, "origin_repository", return_value="example/todos"), \
                patch.object(git_sync, "linked_base", return_value="main"), \
                patch.object(git_sync, "approved_requests", return_value={}), \
                patch.object(git_sync, "fetch_base", return_value="origin/main"), \
                patch.object(git_sync, "merged_update", return_value=("merged-sha", [7])), \
                patch.object(git_sync, "update_checkout", return_value="Updated local main.") as update, \
                patch.object(git_sync, "left_behind", return_value=""), \
                patch.object(git_sync, "report_base_status") as report, \
                patch.object(git_sync.time, "sleep") as sleep:
            git_sync.watch({}, 30, notify_only=False, once=True)
        update.assert_called_once_with("main", "merged-sha")
        report.assert_called_once()  # the dashboard hears that this checkout is up to date
        sleep.assert_not_called()

    def test_notice_and_fast_forward_only_after_approved_merge(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        checkout = Path(directory)
        self.enterContext(patch.object(git_sync, "PROJECT", checkout))
        def git(*args):
            return git_sync.command("git", *args)

        git("init", "-q", "-b", "main")
        git("config", "user.name", "Team Contract Test")
        git("config", "user.email", "test@example.invalid")
        git("commit", "-q", "--allow-empty", "-m", "Baseline")
        original = git("rev-parse", "HEAD")
        git("switch", "-q", "-c", "synthetic-merge")
        (checkout / "todos.txt").write_text("Merged work\n")
        git("add", "todos.txt")
        git("commit", "-q", "-m", "Add todos")
        target = git("rev-parse", "HEAD")
        git("commit", "-q", "--allow-empty", "-m", "Later unrelated push")
        git("switch", "-q", "main")

        approved = {"number": 7, "headRefOid": target, "isDraft": False, "reviewDecision": "APPROVED"}
        merged = {**approved, "mergeCommit": {"oid": target}}
        with patch.object(git_sync, "pull_requests", return_value=[approved]):
            self.assertEqual(git_sync.approved_requests("example/todos", "main"), {7: target})
            self.assertIsNone(git_sync.merged_update("example/todos", "main", "synthetic-merge", any_merge=False))
        self.assertEqual(git("rev-parse", "HEAD"), original)
        with patch.object(git_sync, "pull_requests", return_value=[
            {**merged, "reviewDecision": "REVIEW_REQUIRED"},
        ]):
            self.assertIsNone(git_sync.merged_update("example/todos", "main", "synthetic-merge", any_merge=False))
            self.assertEqual(git_sync.merged_update("example/todos", "main", "synthetic-merge"), (target, [7]))
        with patch.object(git_sync, "pull_requests", return_value=[merged]):
            self.assertEqual(git_sync.merged_update("example/todos", "main", "synthetic-merge"), (target, [7]))

        # Unsaved edits to a tracked file pause the sync and name the file.
        (checkout / "readme.txt").write_text("Baseline\n")
        git("add", "readme.txt")
        git("commit", "-q", "-m", "Add readme")
        original = git("rev-parse", "HEAD")
        git("switch", "-q", "synthetic-merge")
        git("merge", "-q", "--no-edit", "main")  # the approved work now sits on top of the new baseline
        git("commit", "-q", "--allow-empty", "-m", "Approved merge")
        target = git("rev-parse", "HEAD")
        git("switch", "-q", "main")
        (checkout / "readme.txt").write_text("Half-finished edit\n")
        paused = git_sync.update_checkout("main", target)
        self.assertIn("unsaved edits on main (readme.txt)", paused)
        self.assertIn("start my-task", paused)
        self.assertEqual(git("rev-parse", "HEAD"), original)
        git("restore", "readme.txt")
        # A new file that would be overwritten also pauses the sync, with a plain reason.
        (checkout / "todos.txt").write_text("My own notes\n")
        self.assertIn("same name as one of your new files", git_sync.update_checkout("main", target))
        self.assertEqual((checkout / "todos.txt").read_text(), "My own notes\n")
        (checkout / "todos.txt").unlink()
        # Any other new, untracked file is left alone and does not block.
        (checkout / "notes.md").write_text("Scratch notes")
        git("switch", "-q", "-c", "my-task")
        self.assertIn("Switch to main", git_sync.update_checkout("main", target))
        self.assertEqual(git("rev-parse", "HEAD"), original)
        git("switch", "-q", "main")
        self.assertIn("Updated local main", git_sync.update_checkout("main", target))
        self.assertEqual(git("rev-parse", "HEAD"), target)
        self.assertEqual((checkout / "todos.txt").read_text(), "Merged work\n")
        git("commit", "-q", "--allow-empty", "-m", "Local work after the update")
        local_head = git("rev-parse", "HEAD")
        self.assertEqual((checkout / "notes.md").read_text(), "Scratch notes")
        self.assertIn("has 1 commit(s) that GitHub does not have", git_sync.update_checkout(
            "main", git("rev-parse", "synthetic-merge"),
        ))
        self.assertEqual(git("rev-parse", "HEAD"), local_head)

    def test_watcher_reports_each_stage_once_and_never_updates_in_notify_only(self):
        pr = {7: "head-sha"}
        with patch.object(git_sync, "origin_repository", return_value="example/todos"), \
                patch.object(git_sync, "linked_base", return_value="main"), \
                patch.object(git_sync, "approved_requests", side_effect=[pr, pr, {}, {}]), \
                patch.object(git_sync, "fetch_base", return_value="origin/main"), \
                patch.object(git_sync, "merged_update", side_effect=[None, None, ("merged-sha", [7]), ("merged-sha", [7])]), \
                patch.object(git_sync, "update_checkout") as update, \
                patch.object(git_sync, "left_behind", return_value=""), \
                patch.object(git_sync.time, "sleep", side_effect=[None, None, None, KeyboardInterrupt]), \
                patch("builtins.print") as output:
            with self.assertRaises(KeyboardInterrupt):
                git_sync.watch({}, 30, notify_only=True)
        messages = [call.args[0] for call in output.call_args_list]
        self.assertEqual(sum("PR #7 approved" in message for message in messages), 1)
        self.assertEqual(sum("Merged PRs merged" in message for message in messages), 1)
        update.assert_not_called()


class UnreviewedMergeTest(unittest.TestCase):
    """Small teams often merge without a formal approval. The watcher must not stay silent."""

    def setUp(self):
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.checkout = directory / "client"
        self.checkout.mkdir()
        self.enterContext(patch.object(git_sync, "PROJECT", self.checkout))
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Team Contract Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.checkout / "app.py").write_text("print('v1')\n")
        self.git("add", "app.py")
        self.git("commit", "-q", "-m", "Baseline")
        self.git("init", "-q", "--bare", str(directory / "remote.git"))
        self.git("remote", "add", "origin", str(directory / "remote.git"))
        self.git("push", "-q", "origin", "main")
        # A teammate's pull request is merged on GitHub without an approval.
        self.git("switch", "-q", "-c", "teammate")
        (self.checkout / "todos.py").write_text("todos = []\n")
        self.git("add", "todos.py")
        self.git("commit", "-q", "-m", "Add todos")
        self.merged = self.git("rev-parse", "HEAD")
        self.git("push", "-q", "origin", "teammate:main")
        self.git("switch", "-q", "main")
        self.git("branch", "-q", "-D", "teammate")
        self.pr = {"number": 6, "mergeCommit": {"oid": self.merged}, "reviewDecision": "", "latestReviews": []}

    def git(self, *args):
        return git_sync.command("git", *args)

    def run_watch(self, any_merge):
        with patch.object(git_sync, "origin_repository", return_value="example/todos"), \
                patch.object(git_sync, "linked_base", return_value="main"), \
                patch.object(git_sync, "approved_requests", return_value={}), \
                patch.object(git_sync, "pull_requests", return_value=[self.pr]), \
                patch.object(git_sync, "api") as api, \
                patch("builtins.print") as output:
            git_sync.watch({"name": "Mei", "room": "demo"}, 30, notify_only=False, once=True, any_merge=any_merge)
        return " ".join(str(call.args[0]) for call in output.call_args_list), api

    def test_default_watch_explains_what_it_left_alone(self):
        before = self.git("rev-parse", "HEAD")
        said, api = self.run_watch(any_merge=False)
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertIn("1 newer commit(s) that did not come from an approved pull request", said)
        self.assertIn("watch --any-merge", said)
        api.assert_not_called()

    def test_any_merge_applies_it_and_reports_to_the_dashboard(self):
        said, api = self.run_watch(any_merge=True)
        self.assertEqual(self.git("rev-parse", "HEAD"), self.merged)
        self.assertIn("Merged PRs merged into main: #6. Updated local main", said)
        report = api.call_args.args[3]
        self.assertEqual((report["branch"], report["behind"], report["ahead"]), ("main", 0, 0))

    def test_start_rescues_work_begun_on_the_shared_branch(self):
        # The classic mistake: a commit and an unsaved edit made on main.
        (self.checkout / "app.py").write_text("print('v2')\n")
        self.git("commit", "-q", "-am", "Work done on main by mistake")
        mistake = self.git("rev-parse", "HEAD")
        (self.checkout / "app.py").write_text("print('v3, unsaved')\n")
        with patch("builtins.print"):
            git_sync.start_task("example/todos", "main", "ali/rescue")
        self.assertEqual(self.git("branch", "--show-current"), "ali/rescue")
        self.assertEqual(self.git("rev-parse", "HEAD"), mistake)  # the commit came along
        self.assertEqual((self.checkout / "app.py").read_text(), "print('v3, unsaved')\n")  # so did the edit
        self.assertEqual(self.git("rev-parse", "main"), self.git("rev-parse", "origin/main"))  # main is clean again
        self.assertEqual(self.git("rev-list", "--count", "origin/main..HEAD"), "1")  # and can be published
