import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coord import git_sync


class GitWatchTest(unittest.TestCase):
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
            self.assertIsNone(git_sync.merged_update("example/todos", "main", "synthetic-merge"))
        self.assertEqual(git("rev-parse", "HEAD"), original)
        with patch.object(git_sync, "pull_requests", return_value=[
            {**merged, "reviewDecision": "REVIEW_REQUIRED"},
        ]):
            self.assertIsNone(git_sync.merged_update("example/todos", "main", "synthetic-merge"))
        with patch.object(git_sync, "pull_requests", return_value=[merged]):
            self.assertEqual(git_sync.merged_update("example/todos", "main", "synthetic-merge"), (target, [7]))

        (checkout / "unsaved.txt").write_text("Local work")
        self.assertIn("Local changes detected", git_sync.update_checkout("main", target))
        self.assertEqual(git("rev-parse", "HEAD"), original)
        (checkout / "unsaved.txt").unlink()
        git("switch", "-q", "-c", "my-task")
        self.assertIn("Switch to main", git_sync.update_checkout("main", target))
        self.assertEqual(git("rev-parse", "HEAD"), original)
        git("switch", "-q", "main")
        self.assertIn("Updated local main", git_sync.update_checkout("main", target))
        self.assertEqual(git("rev-parse", "HEAD"), target)
        self.assertEqual((checkout / "todos.txt").read_text(), "Merged work\n")
        git("commit", "-q", "--allow-empty", "-m", "Local work after the update")
        local_head = git("rev-parse", "HEAD")
        self.assertIn("cannot be fast-forwarded", git_sync.update_checkout(
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
                patch.object(git_sync.time, "sleep", side_effect=[None, None, None, KeyboardInterrupt]), \
                patch("builtins.print") as output:
            with self.assertRaises(KeyboardInterrupt):
                git_sync.watch({}, 30, notify_only=True)
        messages = [call.args[0] for call in output.call_args_list]
        self.assertEqual(sum("PR #7 approved" in message for message in messages), 1)
        self.assertEqual(sum("Approved PRs merged" in message for message in messages), 1)
        update.assert_not_called()
