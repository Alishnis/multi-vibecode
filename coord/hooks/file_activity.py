"""Report successful Claude Code edits and pause before an overlapping edit.

Before an edit, the server is asked whether a teammate changed the same file in
the last 30 minutes. If so, Claude Code stops and asks the person at the
keyboard whether to go ahead. After they allow it once, further edits to that
file go through until a teammate changes it again.

Set "overlap": "note" in coord/me.json to get a note for the agent instead of
a question for the person.
"""

import json
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "coord"))

TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
ENDPOINTS = {"PreToolUse": "/files/check", "PostToolUse": "/files/edits"}


def git(*args: str) -> str:
    try:
        result = subprocess.run(
            ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=0.6,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def edited_path(event: dict) -> str | None:
    tool = event.get("tool_name")
    if tool not in TOOLS:
        return None
    name = "notebook_path" if tool == "NotebookEdit" else "file_path"
    value = event.get("tool_input", {}).get(name)
    if not isinstance(value, str) or not value:
        return None
    path = Path(event.get("cwd") or ROOT) / value
    try:
        relative = path.resolve().relative_to(ROOT)
    except ValueError:
        return None
    if relative == Path(".") or ".git" in relative.parts:
        return None
    return relative.as_posix()


def message(path: str, edits: list[dict]) -> str:
    # Keep remote names and branch names from injecting terminal control codes.
    def label(value: str) -> str:
        return "".join(char if char.isprintable() else "?" for char in value)

    descriptions = []
    for edit in edits:
        author = label(edit["author"])
        if edit.get("branch"):
            author += f" on {label(edit['branch'])}"
        age = datetime.now(timezone.utc) - datetime.fromisoformat(edit["edited_at"])
        minutes = max(0, int(age.total_seconds()) // 60)
        descriptions.append(f"{author} ({f'{minutes} min ago' if minutes else 'just now'})")
    return (
        f"[Team Contract · FILE OVERLAP] {', '.join(descriptions)} recently edited {label(path)}. "
        "Edit it only if you have their latest changes or have agreed with them. "
        "Otherwise review their changes or ask them first."
    )


def run(event: dict) -> dict | None:
    endpoint = ENDPOINTS.get(event.get("hook_event_name"))
    path = edited_path(event)
    if not endpoint or not path:
        return None
    # Imported here so that a missing helper file is reported like any other
    # failure (a quiet note) instead of crashing the hook.
    from git_sync import github_repository
    from tc_http import urlopen

    me = json.loads((ROOT / "coord/me.json").read_text())
    remote = git("remote", "get-url", "origin")
    try:
        repository = github_repository(remote) if remote else None
    except ValueError:
        repository = None
    payload = {
        "room": me["room"], "author": me["name"], "path": path,
        "repository": repository, "branch": git("branch", "--show-current") or None,
    }
    request = urllib.request.Request(
        me["server"].rstrip("/") + endpoint, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=2) as response:
        result = json.load(response)
    if event["hook_event_name"] == "PreToolUse" and result["edits"]:
        warning = message(path, result["edits"])
        if me.get("overlap") == "note":
            # Advisory only: the agent reads the note next to the tool result.
            return {
                "systemMessage": warning,
                "hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": warning},
            }
        # Pause: Claude Code shows the reason and asks the person to allow or deny the edit.
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "ask",
                "permissionDecisionReason": warning,
            },
        }
    return None


if __name__ == "__main__":
    try:
        output = run(json.load(sys.stdin))
        if output:
            print(json.dumps(output))
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, ImportError) as error:
        print(f"Team Contract file check unavailable ({type(error).__name__}).", file=sys.stderr)
