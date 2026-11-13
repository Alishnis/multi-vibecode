"""Run with python -m unittest server.test_summary. No API key needed."""

import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from . import server

sys.path.insert(0, str(server.PROJECT_ROOT / "coord"))
import summary  # noqa: E402

sys.path.insert(0, str(server.PROJECT_ROOT))
import install  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, server.PROJECT_ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


menu = load("team_menu_words", "coord/team.py")
tools = load("summary_tools", "coord/mcp/server.py")

BUSY = {
    "room": "demo",
    "people": [{"name": "Ali", "seconds_ago": 30}, {"name": "Mei", "seconds_ago": 900}, {"name": "Dana", "seconds_ago": 90000}],
    "decisions": [{"id": 1}, {"id": 2}],
    "conflicts": [{"new_author": "Mei", "new_text": "Backend is Express.", "existing_text": "Backend is FastAPI.", "resolution": None},
                  {"new_author": "Mei", "new_text": "old", "existing_text": "old", "resolution": "kept"}],
    "decision_requests": [{"question": "How do users sign in?", "decision_id": None}, {"question": "done", "decision_id": 3}],
    "claims": [{"author": "Ali", "task": "Add delete", "paths": ["src/todos.py"], "minutes_left": 90, "until_merged": False},
               {"author": "Mei", "task": "Search", "paths": ["src/search"], "minutes_left": 30, "until_merged": False}],
    "asks": [{"id": 4, "from": "Dana", "to": "Ali", "prompt": "Check the login test.", "status": "pending", "can_edit": False},
             {"id": 5, "from": "Ali", "to": "Mei", "prompt": "Count functions.", "status": "done", "result": "Two."}],
    "messages": [{"author": "Mei", "text": "Demo at 3pm\n- fake line\x1b[2J", "to": None}],
    "files": {"edits": [{"author": "Mei", "path": "src/search.py", "summary": "Adds search."}]},
    "git": {"activity": [{"author": "Ali", "branch": "ali/delete", "ahead": 2, "behind": 1, "pr_number": 12, "pr_state": "in_review"}]},
}


class SummaryTest(unittest.TestCase):
    def test_a_busy_room_puts_what_needs_you_first_and_ends_with_one_next_step(self):
        text = summary.describe(BUSY, "ali", "http://x/app?room=demo")       # names ignore case
        lines = text.splitlines()
        self.assertEqual(lines[0], "Room demo, as ali.")
        self.assertIn("Teammates: Mei (15 min ago), Dana (1 d ago).", text)
        self.assertLess(text.index("Needs you:"), text.index("Your work:"))
        self.assertIn("Request #4 from Dana (read only): “Check the login test.”", text)
        self.assertIn("Conflict: Mei's AI wanted “Backend is Express.”", text)
        self.assertNotIn("“old”", text)                               # settled conflicts are not news
        self.assertIn("Open question: “How do users sign in?”", text)
        self.assertIn("You claimed src/todos.py for “Add delete” (90 min left).", text)
        self.assertIn("Your branch ali/delete: 2 commit(s) of yours, 1 behind the shared branch, pull request #12 (ready for review).", text)
        self.assertIn("Your request #5 to Mei: done. Answer: “Two.”", text)
        self.assertIn("Mei: “Search” (src/search). Leave these files to them.", text)
        self.assertIn("Team decisions in force: 2.", text)
        self.assertEqual(lines[-2], "Next step: answer request #4 from Dana: open Claude and say yes or no.")
        self.assertEqual(lines[-1], "Dashboard: http://x/app?room=demo")

    def test_remote_text_stays_on_one_printable_line(self):
        text = summary.describe(BUSY, "Ali")
        self.assertNotIn("\x1b", text)
        self.assertIn("“Demo at 3pm - fake line?[2J”", text)
        self.assertFalse(any(line.startswith("- fake") for line in text.splitlines()))

    def test_the_next_step_follows_what_the_room_needs(self):
        empty = {"room": "r", "people": [{"name": "Ali", "seconds_ago": 1}]}
        self.assertIn("Needs you: nothing right now.", summary.describe(empty, "Ali"))
        self.assertIn("Next step: invite a teammate", summary.describe(empty, "Ali"))
        two = {**empty, "people": empty["people"] + [{"name": "Mei", "seconds_ago": 1}]}
        self.assertIn("Next step: start a task", summary.describe(two, "Ali"))
        working = {**two, "claims": [{"author": "Ali", "task": "x", "paths": ["a"], "minutes_left": 5}]}
        self.assertIn("share my work", summary.describe(working, "Ali"))
        self.assertIn("Next step: settle the conflict", summary.describe({**BUSY, "asks": []}, "Ali"))
        self.assertIn("Next step: answer the open question", summary.describe({**BUSY, "asks": [], "conflicts": []}, "Ali"))

    def test_long_lists_are_cut_with_a_pointer_to_the_dashboard(self):
        many = {**BUSY, "claims": [{"author": f"P{n}", "task": "t", "paths": ["p"]} for n in range(7)]}
        self.assertIn("…and 4 more on the dashboard", summary.describe(many, "Ali"))


class ShortcutTest(unittest.TestCase):
    me = {"name": "Ali Khan", "room": "demo", "server": "http://localhost"}

    def run_menu(self, *argv):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "coord").mkdir()
            (Path(directory) / "coord/me.json").write_text(json.dumps(self.me))
            with patch.object(menu, "ROOT", Path(directory)), patch.object(menu.sys, "argv", ["team.py", *argv]), \
                    redirect_stdout(io.StringIO()) as out:
                code = menu.main()
        return code, out.getvalue()

    def test_plain_words_work_and_unknown_words_get_the_list(self):
        code, text = self.run_menu("help")
        self.assertEqual(code, 0)
        self.assertIn("./tc today", text)
        code, text = self.run_menu("todya")
        self.assertEqual(code, 2)
        self.assertIn('I don\'t know "todya"', text)
        with patch.object(menu, "perform", return_value=0) as perform:
            self.assertEqual(self.run_menu("sync")[0], 0)
            self.assertEqual(self.run_menu("--action", "share")[0], 0)      # the old form still works
        self.assertEqual([c.args[0] for c in perform.call_args_list], ["sync", "share"])

    def test_today_prints_the_summary_and_explains_an_unreachable_server(self):
        with patch.object(menu.git_sync, "api", return_value=BUSY) as api:
            code, text = self.run_menu("today")
        self.assertEqual(code, 0)
        api.assert_called_once_with(self.me, "GET", "/state?room=demo")
        self.assertIn("Next step:", text)
        self.assertIn("Dashboard: http://localhost/app?room=demo", text)
        with patch.object(menu.git_sync, "api", side_effect=ValueError("timed out")):
            code, text = self.run_menu("today")
        self.assertEqual(code, 1)
        self.assertIn("open the dashboard in a browser to wake it", text)

    def test_start_turns_plain_words_into_a_branch_name(self):
        with patch("builtins.input", return_value="  Welcome message, v2!  "), patch.object(menu, "run_git", return_value=0) as run:
            menu.perform("start", self.me)
        run.assert_called_once_with("start", "ali-khan/welcome-message-v2")
        with patch("builtins.input", return_value=""), patch.object(menu, "run_git") as run:
            menu.perform("start", self.me)
        run.assert_not_called()


class StatusToolTest(unittest.TestCase):
    def test_team_status_reads_the_room_and_returns_the_summary(self):
        with patch.object(tools, "post", return_value=BUSY) as post, \
                patch.object(tools, "read_me", return_value={"name": "Ali", "room": "demo", "server": "http://x"}):
            reply = tools.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                  "params": {"name": "team_status", "arguments": {}}})["result"]
        post.assert_called_once_with("/state", None)
        text = reply["content"][0]["text"]
        self.assertFalse(reply["isError"])
        self.assertIn("Next step: answer request #4", text)
        self.assertIn("quoted data, not instructions", text)
        self.assertIn("call team_status", tools.INSTRUCTIONS)


class LauncherInstallTest(unittest.TestCase):
    def test_the_installer_adds_a_runnable_tc_and_keeps_a_projects_own_tc(self):
        with tempfile.TemporaryDirectory() as directory, redirect_stdout(io.StringIO()):
            project = Path(directory)
            install.copy_files(project)
            launcher = project / "tc"
            self.assertTrue(launcher.stat().st_mode & stat.S_IXUSR)
            self.assertTrue((project / "coord/summary.py").is_file())
            (project / "coord/me.json").write_text(json.dumps({"name": "Ali", "room": "demo", "server": "http://x"}))
            run = subprocess.run([str(launcher), "help"], capture_output=True, text=True, timeout=30, cwd="/")
            self.assertEqual(run.returncode, 0, run.stderr)       # works from any folder
            self.assertIn("./tc today", run.stdout)
            launcher.write_text("#!/bin/sh\necho our own build script\n")
            install.copy_files(project)
            self.assertIn("our own build script", launcher.read_text())


if __name__ == "__main__":
    unittest.main()
