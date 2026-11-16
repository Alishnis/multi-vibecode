"""Run with python -m unittest server.test_live. No API key needed."""

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from . import server

HOOK = Path(__file__).parent.parent / "coord/hooks/file_activity.py"
spec = importlib.util.spec_from_file_location("file_activity_live", HOOK)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

DIFF = "@@ -1,2 +1,2 @@\n def add(a, b):\n-    return a - b\n+    return a + b"


class LiveFeedTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        server.create_tables()
        self.client = TestClient(server.app)

    def edit(self, author="Ali", path="src/calc.py", room="live", **extra):
        body = {"room": room, "author": author, "path": path, "branch": f"{author.lower()}/work", "diff": DIFF, **extra}
        reply = self.client.post("/files/edits", json=body)
        self.assertEqual(reply.status_code, 200, reply.text)

    def feed(self, after=0, room="live"):
        return self.client.get(f"/live?room={room}&after={after}").json()

    def test_every_edit_is_kept_in_order_with_its_diff(self):
        self.assertEqual(self.feed(), {"edits": [], "oldest": None, "latest": None, "summaries": {},
                                       "now": self.feed()["now"]})
        self.edit(summary="+1/-1 lines", tool="Edit")
        self.edit()
        self.edit("Mei")
        feed = self.feed()
        self.assertEqual([edit["author"] for edit in feed["edits"]], ["Ali", "Ali", "Mei"])
        self.assertEqual(feed["edits"][0]["diff"], DIFF)
        self.assertEqual(feed["edits"][0]["summary"], "+1/-1 lines")
        self.assertEqual((feed["oldest"], feed["latest"]), (feed["edits"][0]["id"], feed["edits"][2]["id"]))
        newer = self.feed(after=feed["edits"][1]["id"])
        self.assertEqual([edit["author"] for edit in newer["edits"]], ["Mei"])
        self.assertEqual(self.feed(after=feed["latest"])["edits"], [])
        self.assertEqual(self.feed(room="other")["edits"], [])

    def test_no_diff_means_no_card_and_secret_files_are_refused(self):
        self.client.post("/files/edits", json={"room": "live", "author": "Ali", "path": "src/calc.py"})
        self.edit(path=".env")
        self.edit(path="config/secret_keys.py")
        self.assertEqual(self.feed()["edits"], [])
        # The 30-minute file list still has them: only the code is left out.
        self.assertEqual(len(self.client.get("/state?room=live").json()["files"]["edits"]), 3)

    def test_long_diff_is_cut_and_old_cards_are_dropped(self):
        self.edit(diff="+" + "x" * 20000)
        self.assertEqual(len(self.feed()["edits"][0]["diff"]), server.LIVE_DIFF_LIMIT)
        with patch.object(server, "LIVE_KEEP", 3):
            for _ in range(5):
                self.edit()
        feed = self.feed()
        self.assertEqual(len(feed["edits"]), 3)
        self.assertEqual(feed["oldest"], feed["edits"][0]["id"])

    def test_reset_clears_the_feed(self):
        self.edit()
        self.assertEqual(self.client.post("/reset?room=live").status_code, 200)
        self.assertEqual(self.feed()["latest"], None)

    def test_later_summary_reaches_cards_already_sent(self):
        self.edit(summary="+1/-1 lines")
        card = self.feed()["edits"][0]
        with patch.object(server.conflicts, "summarise_change", return_value="Fixes add to sum its inputs."):
            server.improve_summary("live", card["path"], "Ali", card["edited_at"], "+1/-1 lines", "+x")
        self.assertEqual(self.feed(after=card["id"])["summaries"][str(card["id"])],
                         "Fixes add to sum its inputs. (+1/-1 lines)")


class HookDiffTest(unittest.TestCase):
    def test_uses_the_patch_claude_code_reports(self):
        event = {"tool_name": "Edit", "tool_input": {"old_string": "b", "new_string": "B"},
                 "tool_response": {"structuredPatch": [{"oldStart": 10, "oldLines": 3, "newStart": 10, "newLines": 3,
                                                        "lines": [" a", "-b", "+B", " c"]}]}}
        self.assertEqual(hook.live_diff("src/x.py", event), "@@ -10,3 +10,3 @@\n a\n-b\n+B\n c")

    def test_works_out_a_diff_without_a_patch(self):
        edit = {"tool_name": "Edit", "tool_input": {"old_string": "a\nb\nc", "new_string": "a\nB\nc"}}
        self.assertEqual(hook.live_diff("src/x.py", edit), "@@\n a\n-b\n+B\n c")
        write = {"tool_name": "Write", "tool_input": {"content": "x = 1\ny = 2\n"}}
        self.assertEqual(hook.live_diff("src/x.py", write), "@@ new text @@\n+x = 1\n+y = 2")
        multi = {"tool_name": "MultiEdit", "tool_input": {"edits": [
            {"old_string": "one", "new_string": "1"}, {"old_string": "two", "new_string": "2"}]}}
        self.assertEqual(hook.live_diff("src/x.py", multi), "@@\n-one\n+1\n@@\n-two\n+2")

    def test_secret_files_and_odd_input_send_nothing(self):
        write = {"tool_name": "Write", "tool_input": {"content": "TOKEN=abc"}}
        self.assertIsNone(hook.live_diff(".env", write))
        self.assertIsNone(hook.live_diff("id_rsa", write))
        self.assertIsNone(hook.live_diff("src/x.py", {"tool_name": "Edit", "tool_input": None}))
        self.assertIsNone(hook.live_diff("src/x.py", {"tool_name": "Edit", "tool_input": {},
                                                      "tool_response": {"structuredPatch": [{"lines": 5}]}}))

    def test_long_diff_is_cut_at_a_whole_line(self):
        diff = hook.live_diff("src/x.py", {"tool_name": "Write", "tool_input": {"content": "line\n" * 5000}})
        self.assertLessEqual(len(diff), hook.LIVE_LIMIT)
        self.assertTrue(diff.endswith("the edit is longer"))


if __name__ == "__main__":
    unittest.main()
