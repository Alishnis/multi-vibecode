"""Run with python -m unittest server.test_agent_git_tools. No API key needed."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from coord.mcp import server as tools
from . import server


def call(name, arguments):
    reply = tools.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                          "params": {"name": name, "arguments": arguments}})
    return reply["result"]["content"][0]["text"], reply["result"]["isError"]


class AgentGitToolsTest(unittest.TestCase):
    def run_tool(self, name, arguments, returncode=0, stdout="[CoopDev] ok", stderr=""):
        finished = subprocess.CompletedProcess([], returncode, stdout, stderr)
        with patch.object(tools.subprocess, "run", return_value=finished) as run:
            text, is_error = call(name, arguments)
        helper_args = run.call_args.args[0][2:] if run.called else None  # after python and the script path
        return text, is_error, helper_args, run

    def test_each_tool_runs_the_matching_terminal_command(self):
        cases = [
            ("start_task", {"name": " ali/todo-delete "}, ["start", "ali/todo-delete"]),
            ("share_work", {}, ["publish", "--ready"]),
            ("share_work", {"draft": True, "title": "Add  delete\nendpoint"}, ["publish", "--title=Add delete endpoint"]),
            ("get_latest", {}, ["watch", "--once", "--any-merge"]),
            ("get_latest", {"include_unapproved": False}, ["watch", "--once", "--approved-only"]),
            ("get_latest", {"include_unapproved": True}, ["watch", "--once", "--any-merge"]),
            ("branch_status", {}, ["status"]),
        ]
        for name, arguments, expected in cases:
            text, is_error, helper_args, run = self.run_tool(name, arguments)
            self.assertEqual((helper_args, is_error, text), (expected, False, "[CoopDev] ok"), name)
            # The helper must never wait for typed input or write to the protocol stream.
            self.assertIs(run.call_args.kwargs["stdin"], subprocess.DEVNULL)
            self.assertTrue(run.call_args.kwargs["capture_output"])
            self.assertEqual(Path(run.call_args.args[0][1]).name, "git_sync.py")

    def test_a_failed_git_step_reaches_the_agent_as_an_error_with_the_reason(self):
        reason = "[CoopDev] main is the shared branch. Run python3 coord/git_sync.py start my-task first."
        text, is_error, _, _ = self.run_tool("share_work", {}, returncode=1, stdout="", stderr=reason)
        self.assertTrue(is_error)
        self.assertEqual(text, reason)
        slow = subprocess.TimeoutExpired("git_sync", 150)
        with patch.object(tools.subprocess, "run", side_effect=slow):
            text, is_error = call("get_latest", {})
        self.assertTrue(is_error)
        self.assertIn("took too long", text)

    def test_a_task_name_cannot_smuggle_in_an_option(self):
        for name in ("", "--help", "-x"):
            text, is_error, _, run = self.run_tool("start_task", {"name": name})
            self.assertTrue(is_error)
            run.assert_not_called()

    def test_tool_list_and_instructions_describe_the_git_tools(self):
        listed = tools.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})["result"]["tools"]
        names = [tool["name"] for tool in listed]
        self.assertEqual(names[3:7], ["start_task", "share_work", "get_latest", "branch_status"])
        self.assertIn("Use them only when the user asks", tools.INSTRUCTIONS)
        # People keep the team key, so linking a room is not offered to agents.
        self.assertFalse({"link", "create", "link_repository"} & set(names))

    def test_prompt_text_mentions_git_only_for_linked_rooms(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        self.enterContext(patch.dict(os.environ, {"CONTRACT_APPROVAL_TOKEN": "local-test"}))
        server.create_tables()
        client = TestClient(server.app)
        self.assertNotIn("start_task", client.get("/contract?room=demo").json()["text"])
        link = {"room": "demo", "repository": "example/todos", "base_branch": "main"}
        self.assertEqual(client.put("/git", json=link, headers={"X-Contract-Token": "local-test"}).status_code, 200)
        text = client.get("/contract?room=demo").json()["text"]
        self.assertIn("example/todos, shared branch main", text)
        self.assertIn("Only when the user asks", text)
