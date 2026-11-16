"""Run with python -m unittest server.test_remote_mcp. No API key needed."""

import os
import tempfile
import unittest

os.environ.setdefault("CONTRACT_DB_PATH", os.path.join(tempfile.mkdtemp(), "contract.db"))

from fastapi.testclient import TestClient  # noqa: E402

from server import server  # noqa: E402

KEY = "remote-key-123"


class RemoteMcpTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(server.app)
        self.room = f"remote-{self.id().rsplit('.', 1)[1]}"
        self.client.post("/rooms/key", json={"room": self.room, "author": "Ali", "key": KEY})

    def link(self, name="Ali", key=KEY):
        return self.client.post("/connectors", json={"room": self.room, "author": name},
                                headers={"X-Contract-Token": key})

    def path(self, name="Ali"):
        reply = self.link(name)
        self.assertEqual(reply.status_code, 200, reply.text)
        return "/mcp/" + reply.json()["url"].rsplit("/mcp/", 1)[1]

    def rpc(self, path, method, params=None, message_id=1):
        reply = self.client.post(path, json={"jsonrpc": "2.0", "id": message_id, "method": method,
                                             "params": params or {}})
        self.assertEqual(reply.status_code, 200, reply.text)
        return reply.json()

    def call(self, path, tool, arguments=None):
        result = self.rpc(path, "tools/call", {"name": tool, "arguments": arguments or {}})["result"]
        return result["content"][0]["text"], result["isError"]

    def test_link_needs_the_team_key(self):
        self.assertEqual(self.link(key="wrong-key").status_code, 403)
        reply = self.link()
        self.assertEqual(reply.status_code, 200)
        self.assertIn("/mcp/", reply.json()["url"])
        self.assertEqual(reply.json()["name"], "Ali")

    def test_room_without_key_cannot_make_links(self):
        reply = self.client.post("/connectors", json={"room": "no-key-room", "author": "Ali"})
        self.assertEqual(reply.status_code, 503)

    def test_initialize_and_tool_list(self):
        path = self.path()
        init = self.rpc(path, "initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(init["protocolVersion"], "2025-06-18")
        self.assertEqual(init["serverInfo"]["name"], "coopdev")
        self.assertIn('"Ali"', init["instructions"])
        self.assertEqual(self.rpc(path, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"],
                         "2025-06-18")
        names = {tool["name"] for tool in self.rpc(path, "tools/list")["result"]["tools"]}
        self.assertIn("get_contract", names)
        self.assertIn("claim_work", names)
        self.assertIn("ask_teammate", names)
        self.assertFalse(names & {"start_task", "share_work", "get_latest", "branch_status"})

    def test_tools_act_as_the_link_owner(self):
        ali, mei = self.path("Ali"), self.path("Mei")
        text, error = self.call(ali, "record_decision", {"category": "stack", "text": "Backend is FastAPI."})
        self.assertFalse(error, text)
        self.assertIn("(by Ali)", text)

        text, error = self.call(mei, "get_contract")
        self.assertFalse(error, text)
        self.assertIn("Backend is FastAPI.", text)
        self.assertIn("no hooks", text)

        text, _ = self.call(ali, "claim_work", {"task": "Build translate.", "paths": ["src/translate.py"]})
        self.assertIn("Claimed", text)
        text, _ = self.call(mei, "claim_work", {"task": "Also translate.", "paths": ["src/translate.py"]})
        self.assertIn("NOT CLAIMED", text)

        text, error = self.call(ali, "send_message", {"text": "Demo at 3pm."})
        self.assertFalse(error, text)
        text, error = self.call(ali, "ask_teammate", {"to": "Mei", "prompt": "List your files."})
        self.assertFalse(error, text)
        text, error = self.call(mei, "team_status")
        self.assertFalse(error, text)
        self.assertIn("as Mei", text)
        self.assertIn("Request #", text)
        self.assertIn("/app?room=", text)

    def test_tool_errors_come_back_as_tool_errors(self):
        path = self.path()
        text, error = self.call(path, "no_such_tool")
        self.assertTrue(error)
        text, error = self.call(path, "record_decision", {"category": "nonsense", "text": "x"})
        self.assertTrue(error)
        self.assertIn("rejected", text)

    def test_new_link_replaces_old_and_revoke_works(self):
        old = self.path()
        new = self.path()
        self.assertEqual(self.client.post(old, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code, 404)
        self.rpc(new, "ping")
        reply = self.client.post("/connectors/revoke", json={"room": self.room, "author": "ali"},
                                 headers={"X-Contract-Token": KEY})
        self.assertEqual(reply.json()["revoked"], 1)
        self.assertEqual(self.client.post(new, json={"jsonrpc": "2.0", "id": 1, "method": "ping"}).status_code, 404)

    def test_transport_details(self):
        path = self.path()
        note = self.client.post(path, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(note.status_code, 202)
        self.assertEqual(self.client.get(path).status_code, 405)
        bad = self.client.post(path, content=b"{not json", headers={"Content-Type": "application/json"})
        self.assertEqual(bad.json()["error"]["code"], -32700)
        batch = self.client.post(path, json=[{"jsonrpc": "2.0", "id": 1, "method": "ping"},
                                             {"jsonrpc": "2.0", "method": "notifications/initialized"},
                                             {"jsonrpc": "2.0", "id": 2, "method": "nope"}]).json()
        self.assertEqual([reply["id"] for reply in batch], [1, 2])
        self.assertEqual(batch[1]["error"]["code"], -32601)
        self.assertEqual(self.client.post("/mcp/not-a-real-token", json={}).status_code, 404)


class HideTokensTest(unittest.TestCase):
    def test_access_log_masks_the_token(self):
        import logging
        from server.remote_mcp import HideTokens
        record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                                   ("127.0.0.1:1", "POST", "/mcp/SECRET123", "1.1", 200), None)
        HideTokens().filter(record)
        self.assertNotIn("SECRET123", record.getMessage())
        self.assertIn("/mcp/<link>", record.getMessage())


if __name__ == "__main__":
    unittest.main()
