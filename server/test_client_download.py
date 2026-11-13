"""Run with python -m unittest server.test_client_download. No API key needed."""

import io
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
