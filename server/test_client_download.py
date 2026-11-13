"""Run with python -m unittest server.test_client_download. No API key needed."""

import io
import argparse
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient

from . import server

sys.path.insert(0, str(server.PROJECT_ROOT))
import install  # noqa: E402


class ClientDownloadTest(unittest.TestCase):
    def test_pasted_dashboard_link_is_saved_as_api_base_and_room_stays_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(name="Ali", room="team-test-1794575848",
                                      server="https://team-contract.onrender.com/?room=another-room#files")
            me = install.gather_me(Path(directory), args)
            self.assertEqual(me["server"], "https://team-contract.onrender.com")
            self.assertEqual(me["room"], "team-test-1794575848")
            self.assertEqual(install.server_address("http://localhost:8000/team/?room=test"),
                             "http://localhost:8000/team")

    def test_reinstall_repairs_saved_dashboard_url(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / "coord").mkdir()
            (project / "coord/me.json").write_text(json.dumps({
                "name": "Mei", "room": "same-room", "overlap": "note",
                "server": "https://team-contract.onrender.com/?room=same-room",
            }))
            me = install.gather_me(project, argparse.Namespace(name=None, room=None, server=None))
            self.assertEqual(me["server"], "https://team-contract.onrender.com")
            self.assertEqual(me["overlap"], "note")

    def test_invalid_server_address_stops_installation(self):
        for value in ("team-contract.onrender.com", "file:///tmp/project", "https://"):
            with self.subTest(value=value), self.assertRaises(SystemExit):
                install.server_address(value)

    def test_download_holds_everything_the_installer_needs(self):
        needed = {"install.py", ".claude/settings.json", ".mcp.json", *install.FILES_TO_COPY}
        self.assertEqual(set(server.CLIENT_FILES), needed)

    def test_downloaded_installer_sets_up_a_project(self):
        response = TestClient(server.app).get("/client.zip")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "application/zip")
        with tempfile.TemporaryDirectory() as directory:
            unpacked, project = Path(directory) / "download", Path(directory) / "project"
            project.mkdir()
            zipfile.ZipFile(io.BytesIO(response.content)).extractall(unpacked)
            # Port 9 is closed, so the installer warns about the server and still finishes.
            run = subprocess.run(
                [sys.executable, str(unpacked / "install.py"), ".", "--name", "Mei",
                 "--room", "demo", "--server", "http://127.0.0.1:9"],
                cwd=project, capture_output=True, text=True, timeout=60,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            me = json.loads((project / "coord/me.json").read_text())
            self.assertEqual((me["name"], me["room"]), ("Mei", "demo"))
            for relative in install.FILES_TO_COPY:
                self.assertTrue((project / relative).is_file(), relative)
            hooks = json.loads((project / ".claude/settings.json").read_text())["hooks"]
            self.assertIn("UserPromptSubmit", hooks)
            self.assertIn("team-contract", json.loads((project / ".mcp.json").read_text())["mcpServers"])

    def test_public_homepage_and_legacy_room_links(self):
        client = TestClient(server.app)
        self.assertIn('id="setup-command"', client.get('/').text)  # the homepage has the one-paste setup
        for route in ('/app?room=demo', '/?room=demo'):
            self.assertIn('id="workspace-title"', client.get(route).text)
        self.assertIn('--guided', client.get('/install.sh').text)
        self.assertIn('--am-blue', client.get('/design.css').text)

    def test_reinstall_preserves_sync_preference_and_other_agent_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / 'coord').mkdir()
            (project / '.claude').mkdir()
            (project / 'coord/me.json').write_text(json.dumps({'name': 'Mei', 'room': 'demo',
                'server': 'http://127.0.0.1:9', 'auto_sync': True, 'ai_summary': False}))
            (project / '.claude/settings.json').write_text(json.dumps({'permissions': {'deny': ['Bash(rm:*)']}}))
            run = subprocess.run([sys.executable, str(server.PROJECT_ROOT / 'install.py'), str(project)],
                                 capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, run.stderr)
            saved = json.loads((project / 'coord/me.json').read_text())
            self.assertTrue(saved['auto_sync'])
            self.assertFalse(saved['ai_summary'])
            settings = json.loads((project / '.claude/settings.json').read_text())
            self.assertEqual(settings['permissions'], {'deny': ['Bash(rm:*)']})
            self.assertFalse((project / '.claude/settings.local.json').exists())
