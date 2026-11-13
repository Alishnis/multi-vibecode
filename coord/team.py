"""One local menu for Team Contract. No shell commands from the website are executed."""
import argparse
import json
import os
import tempfile
import re
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.parse
import webbrowser

import git_sync

ROOT = Path(__file__).resolve().parent.parent
# The word you type after ./tc, and what it does. The menu shows them in this order.
ACTIONS = {
    "today": "What's happening, and what to do next",
    "work": "Open my workspace (Claude, plus syncing if I turned it on)",
    "start": "Start a new task",
    "share": "Share my saved work for review",
    "sync": "Get the team's latest code",
    "status": "Where my branch and pull request stand",
    "claims": "Which files are claimed",
    "release": "Release my claims",
    "room": "Open the team dashboard",
    "watch": "Keep my shared branch updated while this window is open",
    "claude": "Open Claude Code",
    "setup": "Run guided setup again",
    "doctor": "Check my setup",
}
SHORTCUT = "./tc"  # the launcher the installer puts in the project folder


def usage() -> str:
    width = max(map(len, ACTIONS))
    return "Type ./tc and a word:\n" + "\n".join(f"  {SHORTCUT} {word.ljust(width)}  {text}" for word, text in ACTIONS.items())


def today(me):
    """Print the room in plain words, ending with one next step."""
    from summary import describe
    try:
        state = git_sync.api(me, "GET", "/state?" + urllib.parse.urlencode({"room": me["room"]}))
    except ValueError as error:
        print(f"Could not reach the team server at {me['server']}. {error}\n"
              "Check your internet connection. A free hosted server sleeps when idle: "
              "open the dashboard in a browser to wake it, then try again.")
        return 1
    dashboard = me["server"].rstrip("/") + "/app?" + urllib.parse.urlencode({"room": me["room"]})
    print(describe(state, me["name"], dashboard))
    return 0


def confirm(question, default=False):
    suffix = " [Y/n]: " if default else " [y/N]: "
    answer = input(question + suffix).strip().lower()
    return answer in {"yes", "y"} or (not answer and default)


def claude_binary():
    installed = shutil.which("claude")
    native = Path.home() / ".local/bin/claude"
    return installed or (str(native) if native.is_file() and os.access(native, os.X_OK) else None)


def setup(me):
    print("\nLet’s connect your workspace. Your existing files and permissions stay yours.")
    if not sys.stdin.isatty():
        print("Open guided setup in an interactive terminal.")
        return 1
    if not claude_binary():
        if confirm("Install Claude Code using Anthropic’s official installer?"):
            with tempfile.TemporaryDirectory() as directory:
                script = str(Path(directory) / "claude-install.sh")
                subprocess.run(["curl", "-fsSL", "--connect-timeout", "15", "--max-time", "120",
                                "https://claude.ai/install.sh", "-o", script], check=True)
                subprocess.run(["bash", script], check=True)
        else:
            print("You can install Claude later: https://code.claude.com/docs/en/setup")
    if confirm("Connect GitHub for sharing and syncing?"):
        if not shutil.which("gh") and shutil.which("brew") and confirm("Install GitHub CLI with Homebrew?"):
            subprocess.run(["brew", "install", "gh"], check=True)
        if shutil.which("gh"):
            logged_in = subprocess.run(["gh", "auth", "status"], capture_output=True).returncode == 0
            if not logged_in:
                subprocess.run(["gh", "auth", "login"], check=True)
            try:
                git_sync.PROJECT = ROOT
                repo = git_sync.origin_repository()
                linked = git_sync.linked_repository(me)
                if not linked and confirm("Link this project to your team room? You will enter the team key.", True):
                    if run_git("link"):
                        print("Linking did not finish. You can try again from the menu.")
                elif linked and linked["repository"].lower() != repo.lower():
                    print("This room is linked to a different repository. Check the room before syncing.")
            except (OSError, ValueError):
                print("No matching GitHub project found. You can still use shared decisions and file warnings.")
        else:
            print("Install GitHub CLI to enable Git features: https://cli.github.com/")
    me["auto_sync"] = confirm("Keep merged code up to date while your workspace is open?", me.get("auto_sync") is True)
    (ROOT / "coord/me.json").write_text(json.dumps(me, indent=2) + "\n")
    doctor(me)
    if confirm("Open your workspace now?", True):
        return workspace(me)
    print("Ready. Next time, in this folder, run: ./tc work   (or ./tc for everything else)")
    return 0


def workspace(me):
    if not claude_binary():
        print("Install Claude Code first: https://code.claude.com/docs/en/setup")
        return 1
    perform("room", me)
    watcher = None
    log = None
    try:
        if me.get("auto_sync") is True:
            git_sync.PROJECT = ROOT
            try:
                repo = git_sync.origin_repository()
                git_sync.linked_base(me, repo)
                state = ROOT / "coord/.state"
                state.mkdir(parents=True, exist_ok=True)
                log = (state / "sync.log").open("w")
                watcher = subprocess.Popen([sys.executable, "-u", str(ROOT / "coord/git_sync.py"), "watch"],
                                           cwd=ROOT, stdout=log, stderr=log)
                print("Sync is running for this workspace. Status: coord/.state/sync.log")
                print("Only clean shared branches update. Your task branches and unsaved work stay protected.")
            except (OSError, ValueError):
                print("Sync is not connected yet. Run guided setup to link this repository.")
        return subprocess.run([claude_binary(), "--permission-mode", "default"], cwd=ROOT).returncode
    finally:
        if watcher is not None:
            watcher.terminate()
            try:
                watcher.wait(timeout=5)
            except subprocess.TimeoutExpired:
                watcher.kill()
                watcher.wait()
        if log is not None:
            log.close()


def run_git(*args):
    return subprocess.run([sys.executable, str(ROOT / "coord/git_sync.py"), *args], cwd=ROOT).returncode


def doctor(me):
    """Report independent checks, without modifying configuration or requiring Git."""
    checks = []
    for binary in ("git", "gh", "claude"):
        checks.append((bool(claude_binary() if binary == "claude" else shutil.which(binary)), f"{binary} installed"))
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
    if action == "today":
        return today(me)
    if action == "setup":
        return setup(me)
    if action == "work":
        return workspace(me)
    if action == "start":
        topic = input("What is the task, in a few words? (for example: welcome message) ").strip()
        if not topic:
            return 0
        # A branch name from the person's name and the topic: "Ali", "welcome message" -> ali/welcome-message
        slug = "-".join(re.findall(r"[a-z0-9]+", topic.lower()))[:40] or "task"
        owner = "-".join(re.findall(r"[a-z0-9]+", me["name"].lower())) or "me"
        return run_git("start", f"{owner}/{slug}")
    commands = {"share": ("publish", "--ready"), "sync": ("watch", "--once"),
                "watch": ("watch",), "status": ("status",)}
    if action in commands:
        if action == "share":
            print("This shares saved Git commits. Uncommitted edits are not included.")
        return run_git(*commands[action])
    if action == "doctor":
        return doctor(me)
    if action == "room":
        url = me["server"].rstrip("/") + "/app?" + urllib.parse.urlencode({"room": me["room"]})
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
        if not claude_binary():
            print("Claude Code is not installed.")
            return 1
        return subprocess.run([claude_binary(), "--permission-mode", "default"], cwd=ROOT).returncode
    return 0


def main():
    parser = argparse.ArgumentParser(description="Team Contract action menu", add_help=False)
    parser.add_argument("word", nargs="?", help="what to do, for example today, start, share or sync")
    parser.add_argument("--action", choices=ACTIONS)
    parser.add_argument("-h", "--help", action="store_true")
    args = parser.parse_args()
    word = args.action or args.word
    if args.help or word == "help":
        print(usage())
        return 0
    if word and word not in ACTIONS:
        print(f"I don't know \"{word}\".\n" + usage())
        return 2
    args.action = word
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
            print("\nTeam Contract — what would you like to do?")
            for number, action in enumerate(actions, 1):
                print(f"  {number:>2}. {ACTIONS[action]}   ({SHORTCUT} {action})")
            choice = input("   0. Exit\nType a number or a word: ").strip().lower()
            if choice in {"0", "exit", "quit", "q"}:
                return 0
            if choice.isdigit() and 1 <= int(choice) <= len(actions):
                choice = actions[int(choice) - 1]
            if choice not in ACTIONS:
                print("Type one of the numbers or words above.")
                continue
            try:
                perform(choice, me)
            except KeyboardInterrupt:
                print("\nStopped. Returning to menu.")
            except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
                print(f"Action could not finish ({type(error).__name__}). Run ./tc doctor to check your setup.")
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"Setup or action could not finish ({type(error).__name__}). Run the installer or Check my setup.")
        return 1
    except (KeyboardInterrupt, EOFError):
        return 0


if __name__ == "__main__":
    sys.exit(main())
