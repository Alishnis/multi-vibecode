"""Send this project's files to the room's read-only code view.

    python3 coord/live_sync.py        (or: ./coopdev live)

The code view (the "Code" page of the dashboard) shows each teammate's copy of
the project, for reading only. This script sends the files Git knows about,
plus new files Git does not ignore. Only files that changed since the last run
are sent again.

Never sent: files that usually hold secrets (.env, keys), files larger than
200 KB, binary files, and the CoopDev tool itself. They are listed by name
only. The server keeps files only in a room with a team key, and shows them
only to people who type that key.

Set "live": false in coord/me.json to send nothing. The edit hook starts this
script by itself when the server asks for a fresh copy. Built-in libraries only.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "coord"))

STATE = ROOT / "coord/.state/live-sync.json"
FILE_LIMIT = 200_000          # bytes of one file
MAX_FILES = 1500
BATCH_FILES = 40
BATCH_BYTES = 600_000
SECRET_NAMES = re.compile(r"(^\.env|secret|credential|password|\.pem$|\.key$|id_rsa|\.p12$)", re.IGNORECASE)
TOOL_PATHS = ("coord/", ".claude/", ".git/")
TOOL_FILES = {".mcp.json", "tc", "coopdev"}
SKIP_FOLDERS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build", ".next", ".idea"}


def project_files() -> list[str]:
    """Project-relative paths: what Git tracks plus new files it does not ignore."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=ROOT, capture_output=True, timeout=8,
        )
        paths = listed.stdout.decode(errors="replace").split("\0") if listed.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        paths = None
    if paths is None:  # not a Git project: walk the folder
        paths = []
        for folder, folders, names in os.walk(ROOT):
            folders[:] = [name for name in folders if name not in SKIP_FOLDERS and not name.startswith(".")]
            paths += [(Path(folder) / name).relative_to(ROOT).as_posix() for name in names]
    kept = [path for path in paths
            if path and not path.startswith(TOOL_PATHS) and path not in TOOL_FILES
            and path.isprintable() and "\\" not in path and ":" not in path and len(path) <= 500
            and (ROOT / path).is_file()]
    return sorted(set(kept))[:MAX_FILES]


def read_file(path: str) -> tuple[str | None, str | None]:
    """(text, None) for a file that can be shown, or (None, why not)."""
    if SECRET_NAMES.search(Path(path).name):
        return None, "secret file, not shared"
    file = ROOT / path
    try:
        if file.stat().st_size > FILE_LIMIT:
            return None, "larger than 200 KB"
        data = file.read_bytes()
    except OSError:
        return None, "could not be read"
    if b"\0" in data:
        return None, "binary file"
    try:
        return data.decode("utf-8"), None
    except UnicodeDecodeError:
        return None, "binary file"


def post(me: dict, body: dict) -> dict:
    from tc_http import urlopen
    request = urllib.request.Request(
        me["server"].rstrip("/") + "/code/files", data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST",
    )
    with urlopen(request, timeout=20) as response:
        return json.load(response)


def branch() -> str | None:
    try:
        result = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None


def sync(me: dict) -> str:
    """Send what changed. Returns one line to show the person."""
    if me.get("live") is False or me.get("ai_summary") is False:
        return 'Nothing sent: "live" or "ai_summary" is false in coord/me.json.'
    try:
        sent = json.loads(STATE.read_text())
        sent = sent if isinstance(sent, dict) else {}
    except (OSError, ValueError):
        sent = {}
    paths = project_files()
    base = {"room": me["room"], "author": me["name"], "branch": branch()}
    batch, size, new_state, changed = [], 0, {}, 0

    def flush(last: bool = False) -> dict:
        nonlocal batch, size
        reply = post(me, {**base, "files": batch, **({"paths": paths} if last else {})})
        batch, size = [], 0
        return reply

    for path in paths:
        text, note = read_file(path)
        mark = hashlib.sha1((text if text is not None else "\0" + note).encode()).hexdigest()
        new_state[path] = mark
        if sent.get(path) == mark:
            continue
        changed += 1
        batch.append({"path": path, "content": text, "note": note})
        size += len(text or "")
        if len(batch) >= BATCH_FILES or size >= BATCH_BYTES:
            if not flush().get("stored"):
                return "Nothing kept: this room has no team key. Set one on the dashboard to turn on the code view."
    reply = flush(last=True)
    if not reply.get("stored"):
        return "Nothing kept: this room has no team key. Set one on the dashboard to turn on the code view."
    try:
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(new_state))
    except OSError:
        pass
    return f"Code view updated: {len(paths)} files, {changed} sent, {reply.get('removed', 0)} removed."


if __name__ == "__main__":
    try:
        print(sync(json.loads((ROOT / "coord/me.json").read_text())))
    except (OSError, ValueError, KeyError, TypeError, urllib.error.URLError) as error:
        print(f"Code view not updated ({type(error).__name__}: {error}).", file=sys.stderr)
        sys.exit(1)
