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

    def test_guided_setup_saves_preference_without_running_declined_installs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'coord').mkdir()
            me = {**self.me, 'ai_summary': False}
            with patch.object(menu, 'ROOT', root), patch.object(menu.sys.stdin, 'isatty', return_value=True), \
                    patch.object(menu, 'claude_binary', return_value=None), \
                    patch('builtins.input', side_effect=['n', 'n', 'y', 'n']), \
                    patch.object(menu, 'doctor'), patch.object(menu.subprocess, 'run') as run:
                self.assertEqual(menu.setup(me), 0)
                run.assert_not_called()
            saved = json.loads((root / 'coord/me.json').read_text())
            self.assertTrue(saved['auto_sync'])
            self.assertFalse(saved['ai_summary'])
            self.assertEqual(saved['room'], self.me['room'])

    def test_workspace_stops_sync_even_if_claude_cannot_start(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(menu, 'ROOT', Path(directory)), \
                patch.object(menu, 'claude_binary', return_value='/bin/claude'), \
                patch.object(menu.webbrowser, 'open'), \
                patch.object(menu.git_sync, 'origin_repository', return_value='owner/repo'), \
                patch.object(menu.git_sync, 'linked_base', return_value='main'), \
                patch.object(menu.subprocess, 'Popen') as spawn, \
                patch.object(menu.subprocess, 'run', side_effect=OSError('missing')):
            with self.assertRaises(OSError):
                menu.workspace({**self.me, 'auto_sync': True})
            spawn.return_value.terminate.assert_called_once()
            spawn.return_value.wait.assert_called_once_with(timeout=5)
            self.assertTrue(spawn.call_args.kwargs['stdout'].closed)

    def test_workspace_without_auto_sync_never_starts_watcher(self):
        with patch.object(menu, 'claude_binary', return_value='/bin/claude'), \
                patch.object(menu.webbrowser, 'open'), patch.object(menu.subprocess, 'Popen') as spawn, \
                patch.object(menu.subprocess, 'run') as run:
            run.return_value.returncode = 0
            self.assertEqual(menu.workspace(self.me), 0)
            spawn.assert_not_called()
            run.assert_called_once_with(['/bin/claude', '--permission-mode', 'default'], cwd=menu.ROOT)

    def test_setup_does_not_prompt_without_terminal(self):
        with patch.object(menu.sys.stdin, 'isatty', return_value=False), patch('builtins.input') as prompt:
            self.assertEqual(menu.setup(self.me), 1)
            prompt.assert_not_called()

    def test_failed_claude_download_does_not_execute_installer(self):
        with patch.object(menu.sys.stdin, 'isatty', return_value=True), \
                patch.object(menu, 'claude_binary', return_value=None), \
                patch('builtins.input', return_value='y'), \
                patch.object(menu.subprocess, 'run', side_effect=menu.subprocess.CalledProcessError(22, 'curl')) as run:
            with self.assertRaises(menu.subprocess.CalledProcessError):
                menu.setup(self.me)
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.args[0][0], 'curl')
            self.assertIn('https://claude.ai/install.sh', run.call_args.args[0])
