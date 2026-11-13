"""Run with python -m unittest server.test_pages. No API key needed."""

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from . import server

INSTALL_SH = server.PROJECT_ROOT / "server/install.sh"


class PagesTest(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        self.enterContext(patch.object(server, "DB_PATH", Path(directory) / "test.db"))
        server.create_tables()
        self.client = TestClient(server.app)

    def test_the_home_page_and_the_workspace_have_their_own_addresses(self):
        home = self.client.get("/")
        self.assertIn("coding agents", home.text)
        self.assertNotIn('id="conflict-list"', home.text)
        for address in ("/?room=demo", "/app", "/app?room=demo"):  # old shared links keep working
            self.assertIn('id="conflict-list"', self.client.get(address).text, address)
        self.assertEqual(home.headers["cache-control"], "no-store")

    def test_both_pages_use_the_shared_stylesheet_and_it_is_always_revalidated(self):
        for address in ("/", "/app"):
            self.assertIn('href="/design.css"', self.client.get(address).text)
        css = self.client.get("/design.css")
        self.assertEqual(css.headers["content-type"].split(";")[0], "text/css")
        self.assertIn("--am-blue", css.text)
        # Without this header a deploy leaves visitors on the old styles.
        self.assertEqual(css.headers["cache-control"], "no-cache")

    def test_the_dashboard_redraws_claims_when_only_claims_change(self):
        page = self.client.get("/app").text
        # Claims were once redrawn only together with decisions and files.
        self.assertIn('JSON.stringify(state.claims ?? [])', page)
        self.assertNotIn("renderFiles(state.files);\n      renderClaims(state.claims);", page)


class InstallScriptTest(unittest.TestCase):
    """Run install.sh with a stand-in for curl that records the address it was asked for."""

    def run_script(self, *args):
        folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        record = folder / "asked.txt"
        stub = folder / "curl"
        stub.write_text(f'#!/bin/sh\nfor a in "$@"; do case "$a" in http*) echo "$a" >> "{record}";; esac; done\nexit 22\n')
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
        # Mac's own bash is version 3.2, the oldest one people run this with.
        shell = "/bin/bash" if Path("/bin/bash").exists() else "bash"
        run = subprocess.run([shell, str(INSTALL_SH), *args], capture_output=True, text=True, timeout=30,
                             env={**os.environ, "PATH": f"{folder}:{os.environ['PATH']}"}, stdin=subprocess.DEVNULL)
        return run, record.read_text().split() if record.exists() else []

    def test_the_server_can_be_given_in_either_form(self):
        for args in (("--server", "http://one.test/"), ("--server=http://one.test/", "--room", "x")):
            run, asked = self.run_script(*args)
            self.assertEqual(asked, ["http://one.test/client.zip"], args)

    def test_no_arguments_do_not_crash_the_old_mac_shell(self):
        run, asked = self.run_script()
        self.assertNotIn("unbound variable", run.stderr)
        self.assertEqual(asked, ["https://team-contract.onrender.com/client.zip"])

    def test_the_script_has_no_syntax_errors(self):
        self.assertEqual(subprocess.run(["bash", "-n", str(INSTALL_SH)]).returncode, 0)


if __name__ == "__main__":
    unittest.main()
