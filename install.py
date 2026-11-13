#!/usr/bin/env python3
"""Add the team contract tool to a project folder.

    python3 install.py /path/to/your/project

It asks for your name, the room code and the server address, or takes them
from --name, --room and --server.

What it does, in order:
  1. copies the hook and the tool into <project>/coord/
  2. adds the hook to <project>/.claude/settings.json
  3. adds the tool to <project>/.mcp.json
  4. writes <project>/coord/me.json (personal, kept out of git)

Existing settings are merged, never overwritten. Running it again is safe:
the first teammate uses it to install, the others use it to join.

Uses only Python's built-in libraries.
"""

import argparse
import json
import shutil
import sys
import urllib.parse
import urllib.request
from pathlib import Path

SOURCE = Path(__file__).resolve().parent
FILES_TO_COPY = [
    "coord/hooks/contract_hook.py",
    "coord/mcp/server.py",
    "coord/me.example.json",
]
HOOK_MARKER = "coord/hooks/contract_hook.py"  # how we recognise our own hook
TOOL_NAME = "team-contract"
IGNORE_LINES = ["coord/me.json", ".claude/settings.local.json"]


def stop(message: str) -> None:
    sys.exit(f"Stopped: {message}")


def read_json(path: Path) -> dict:
    """Read a JSON file. A missing file is an empty object; a broken one stops the install."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as error:
        stop(f"{path} is not valid JSON ({error}). Fix it first; nothing in it was changed.")
    if not isinstance(data, dict):
        stop(f"{path} does not contain a JSON object. Nothing in it was changed.")
    return data


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def copy_files(target: Path) -> None:
    for relative in FILES_TO_COPY:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, destination)
    print(f"  copied {len(FILES_TO_COPY)} files into coord/")


def add_hook(target: Path) -> None:
    """Merge our UserPromptSubmit hook into the project's Claude Code settings."""
    our_groups = [
        group
        for group in read_json(SOURCE / ".claude/settings.json")["hooks"]["UserPromptSubmit"]
        if any(HOOK_MARKER in hook.get("command", "") for hook in group.get("hooks", []))
    ]
    path = target / ".claude/settings.json"
    settings = read_json(path)
    groups = settings.setdefault("hooks", {}).setdefault("UserPromptSubmit", [])
    already = any(
        HOOK_MARKER in hook.get("command", "")
        for group in groups
        for hook in group.get("hooks", [])
    )
    if already:
        print("  hook already in .claude/settings.json")
        return
    groups.extend(our_groups)
    write_json(path, settings)
    print("  added the hook to .claude/settings.json")


def add_tool(target: Path) -> None:
    """Merge our MCP server into the project's .mcp.json."""
    our_server = read_json(SOURCE / ".mcp.json")["mcpServers"][TOOL_NAME]
    path = target / ".mcp.json"
    config = read_json(path)
    servers = config.setdefault("mcpServers", {})
    if servers.get(TOOL_NAME) == our_server:
        print("  tool already in .mcp.json")
        return
    servers[TOOL_NAME] = our_server
    write_json(path, config)
    print("  added the tool to .mcp.json")


def ask(label: str, given: str | None, default: str | None) -> str:
    """Use the command-line value, or ask, or fall back to the default."""
    if given:
        return given.strip()
    if not sys.stdin.isatty():
        if default:
            return default
        stop(f"no {label} given. Pass --{label} when running without a terminal.")
    hint = f" [{default}]" if default else ""
    answer = input(f"  {label.capitalize()}{hint}: ").strip() or (default or "")
    if not answer:
        stop(f"a {label} is required.")
    return answer


def gather_me(target: Path, args: argparse.Namespace) -> dict:
    """Who is installing. On a rerun, the earlier answers become the defaults."""
    old = read_json(target / "coord/me.json")
    return {
        "name": ask("name", args.name, old.get("name")),
        "room": ask("room", args.room, old.get("room") or "demo"),
        "server": ask("server", args.server, old.get("server") or "http://127.0.0.1:8000").rstrip("/"),
    }


def update_gitignore(target: Path) -> None:
    """Keep personal files out of git. Only touches projects that use git."""
    if not (target / ".git").exists():
        return
    path = target / ".gitignore"
    existing = path.read_text().splitlines() if path.exists() else []
    missing = [line for line in IGNORE_LINES if line not in existing]
    if missing:
        text = "\n".join(existing + missing) + "\n"
        path.write_text(text)
        print(f"  added {len(missing)} line(s) to .gitignore")


def check_server(me: dict) -> None:
    query = urllib.parse.urlencode({"room": me["room"]})
    try:
        with urllib.request.urlopen(f"{me['server']}/contract?{query}", timeout=5) as response:
            count = len(json.load(response)["decisions"])
        print(f"  server reached: room {me['room']} has {count} decision(s)")
    except Exception as error:
        print(f"  WARNING: could not reach {me['server']} ({type(error).__name__}).")
        print("  The files are installed. Check the address, or start the server, then try a prompt.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Add the team contract tool to a project folder.")
    parser.add_argument("project", nargs="?", default=".", help="the project folder (default: current folder)")
    parser.add_argument("--name", help="your name, shown to teammates")
    parser.add_argument("--room", help="the room code your team shares")
    parser.add_argument("--server", help="the coordination server address")
    args = parser.parse_args()

    target = Path(args.project).expanduser().resolve()
    if not target.is_dir():
        stop(f"{target} is not a folder.")

    print(f"Installing the team contract tool into {target}")
    # Read every settings file and collect every answer before changing
    # anything, so a broken file or a missing answer stops the install before
    # a single file is written.
    read_json(target / ".claude/settings.json")
    read_json(target / ".mcp.json")
    me = gather_me(target, args)

    if target == SOURCE:
        print("  this is the tool's own folder, so files and settings are already in place")
    else:
        copy_files(target)
        add_hook(target)
        add_tool(target)
    write_json(target / "coord/me.json", me)
    print(f"  wrote coord/me.json for {me['name']} in room {me['room']}")
    update_gitignore(target)
    check_server(me)

    print(
        "\nDone. Two things left, both yours to do:\n"
        "  1. Open a NEW Claude Code session in this folder. If it asks whether to\n"
        f"     allow the '{TOOL_NAME}' tool, say yes.\n"
        "  2. If it does not ask, approve the tool by creating this file:\n"
        f"       {target / '.claude/settings.local.json'}\n"
        f'     with this content:  {{"enabledMcpjsonServers": ["{TOOL_NAME}"]}}\n'
        "\nCommit coord/, .claude/settings.json and .mcp.json so teammates get them.\n"
        "Each teammate then runs this installer once to write their own coord/me.json."
    )


if __name__ == "__main__":
    main()
