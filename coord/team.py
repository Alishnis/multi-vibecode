"""One local menu for Team Contract. No shell commands from the website are executed."""
import argparse
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse
import webbrowser

import git_sync

ROOT = Path(__file__).resolve().parent.parent
ACTIONS = {
    "start": "Start a task", "share": "Share committed work", "sync": "Get latest code",
    "watch": "Keep my main branch updated", "status": "Check branch status",
    "claims": "See reserved files", "release": "Release my reservations",
    "doctor": "Check my setup", "room": "Open team dashboard", "claude": "Open Claude Code",
}


def run_git(*args):
    return subprocess.run([sys.executable, str(ROOT / "coord/git_sync.py"), *args], cwd=ROOT).returncode


def doctor(me):
    """Report independent checks, without modifying configuration or requiring Git."""
    checks = []
    for binary in ("git", "gh", "claude"):
        checks.append((bool(shutil.which(binary)), f"{binary} installed"))
    try:
        settings = json.loads((ROOT / ".claude/settings.json").read_text())
        for event, tool in (("PreToolUse", "Write"), ("PostToolUse", "Write"), ("PostToolUse", "Read")):
            found = any(re.search(group.get("matcher", ""), tool) and any(
                "coord/hooks/file_activity.py" in hook.get("command", "")
                for hook in group.get("hooks", [])) for group in settings.get("hooks", {}).get(event, []))
            checks.append((found, f"{event} hook for {tool}"))
        mcp = json.loads((ROOT / ".mcp.json").read_text())
        checks.append(("team-contract" in mcp.get("mcpServers", {}), "Team Contract agent connection configured"))
    except (OSError, ValueError, TypeError, re.error):
        checks.append((False, "Agent configuration readable — rerun the installer"))
    for file in ("coord/hooks/file_activity.py", "coord/hooks/contract_hook.py", "coord/mcp/server.py", "coord/tc_http.py"):
        checks.append(((ROOT / file).is_file(), f"Client file {file}"))
    try:
        git_sync.api(me, "GET", "/health")
        checks.append((True, "Team server reachable"))
    except (OSError, ValueError):
        checks.append((False, "Team server reachable — check the address or wake the hosted service"))
    if shutil.which("gh"):
        status = subprocess.run(["gh", "auth", "status"], capture_output=True, timeout=15)
        checks.append((status.returncode == 0, "GitHub signed in (needed for sharing and syncing)"))
    for ok, label in checks:
        print(f"{'OK' if ok else 'CHECK'}  {label}")
    print("Agent approval and a real hook run must still be checked inside a fresh Claude session.")
    return 0 if all(ok for ok, _ in checks) else 1


def perform(action, me):
    if action == "start":
        branch = input("Task branch (for example ali/welcome-message): ").strip()
        return run_git("start", branch) if branch else 0
    commands = {"share": ("publish", "--ready"), "sync": ("watch", "--once"),
                "watch": ("watch",), "status": ("status",)}
    if action in commands:
        if action == "share":
            print("This shares saved Git commits. Uncommitted edits are not included.")
        return run_git(*commands[action])
    if action == "doctor":
        return doctor(me)
    if action == "room":
        url = me["server"].rstrip("/") + "/?" + urllib.parse.urlencode({"room": me["room"]})
        webbrowser.open(url)
        print(url)
    elif action == "claims":
        claims = git_sync.api(me, "GET", "/claims?" + urllib.parse.urlencode({"room": me["room"]}))["claims"]
        for claim in claims:
            # Escaped JSON prevents remote task names from controlling the terminal.
            print(json.dumps({k: claim.get(k) for k in ("id", "author", "paths", "task", "minutes_left")}, ensure_ascii=True))
        if not claims:
            print("No files are reserved. You can start work.")
    elif action == "release":
        if input("Release all YOUR reservations? Type yes: ").strip().lower() == "yes":
            result = git_sync.api(me, "POST", "/claims/release", {"author": me["name"]})
            print(f"Released {result['released']} reservation(s).")
    elif action == "claude":
        if not shutil.which("claude"):
            print("Claude Code is not installed.")
            return 1
        return subprocess.run(["claude", "--permission-mode", "default"], cwd=ROOT).returncode
    return 0


def main():
    parser = argparse.ArgumentParser(description="Team Contract action menu")
    parser.add_argument("--action", choices=ACTIONS)
    args = parser.parse_args()
    try:
        me = json.loads((ROOT / "coord/me.json").read_text())
        if not all(isinstance(me.get(key), str) and me[key] for key in ("name", "room", "server")):
            raise ValueError("Incomplete client settings")
        if args.action:
            return perform(args.action, me)
        if not sys.stdin.isatty():
            print("Open this menu in Terminal, or pass --action doctor to check your setup.")
            return 1
        actions = list(ACTIONS)
        while True:
            print("\nTeam Contract — choose an action")
            for number, action in enumerate(actions, 1):
                print(f"  {number}. {ACTIONS[action]}")
            choice = input("  0. Exit\nChoice: ").strip()
            if choice == "0":
                return 0
            if not choice.isdigit() or not 1 <= int(choice) <= len(actions):
                print("Choose one of the numbers above.")
                continue
            try:
                perform(actions[int(choice) - 1], me)
            except KeyboardInterrupt:
                print("\nStopped. Returning to menu.")
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                print(f"Action could not finish ({type(error).__name__}). Run Check my setup.")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Setup or action could not finish ({type(error).__name__}). Run the installer or Check my setup.")
        return 1
    except (KeyboardInterrupt, EOFError):
        return 0


if __name__ == "__main__":
    sys.exit(main())
