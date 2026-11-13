import importlib.util
import io
import json
import tempfile
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from . import server

sys.path.insert(0, str(server.PROJECT_ROOT / "coord"))

spec = importlib.util.spec_from_file_location("team_menu", server.PROJECT_ROOT / "coord/team.py")
menu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(menu)


class MenuTest(unittest.TestCase):
    me = {"name": "Mei", "room": "demo", "server": "http://localhost"}

    def test_actions_use_fixed_argument_lists(self):
        for action, expected in (("share", ("publish", "--ready")), ("sync", ("watch", "--once")),
                                 ("watch", ("watch",)), ("status", ("status",))):
            with self.subTest(action=action), patch.object(menu, "run_git", return_value=0) as run:
                menu.perform(action, self.me)
                run.assert_called_once_with(*expected)

    def test_release_requires_explicit_yes_and_only_names_current_person(self):
        with patch("builtins.input", return_value="no"), patch.object(menu.git_sync, "api") as api:
            menu.perform("release", self.me)
            api.assert_not_called()
        with patch("builtins.input", return_value="yes"), patch.object(menu.git_sync, "api", return_value={"released": 1}) as api:
            menu.perform("release", self.me)
            api.assert_called_once_with(self.me, "POST", "/claims/release", {"author": "Mei"})

    def test_doctor_reports_missing_settings_without_crashing(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(menu, "ROOT", Path(directory)), \
                patch.object(menu.shutil, "which", return_value=None), \
                patch.object(menu.git_sync, "api", side_effect=ValueError("offline")), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(menu.doctor(self.me), 1)
            self.assertIn("rerun the installer", out.getvalue())
            self.assertIn("Team server reachable", out.getvalue())

    def test_missing_configuration_has_clear_exit(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(menu, "ROOT", Path(directory)), \
                patch.object(menu.sys, "argv", ["team.py", "--action", "doctor"]), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(menu.main(), 1)
            self.assertIn("installer", out.getvalue())
