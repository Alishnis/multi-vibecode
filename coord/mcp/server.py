#!/usr/bin/env python3
"""MCP tools for sharing team decisions, reviewing plans, and sharing code.

Claude Code starts this script (see .mcp.json) and talks to it over stdin and
stdout, one JSON message per line. This is the MCP "stdio" protocol.

It uses only Python's built-in libraries, so teammates install nothing.

Important: stdout is reserved for protocol messages. Anything for humans goes
to stderr.
"""

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # the coord folder
try:
    from tc_http import urlopen
except ImportError:  # an older install without coord/tc_http.py
    from urllib.request import urlopen

ME_FILE = Path(__file__).resolve().parent.parent / "me.json"  # coord/me.json
TIMEOUT_SECONDS = 30  # generous: the server asks an AI model to check each decision
CATEGORIES = ["stack", "api", "data", "convention", "other"]
GIT_HELPER = Path(__file__).resolve().parent.parent / "git_sync.py"  # coord/git_sync.py
GIT_TIMEOUT_SECONDS = 150  # a push plus opening a pull request can take a while

INSTRUCTIONS = (
    "This project has a team contract: a shared list of decisions that every "
    "teammate's AI agent reads before it acts. The current contract is added to "
    "your context on every prompt. Before implementing a plan that touches "
    "shared parts of the project (stack, API shapes, shared field names, "
    "ports), call check_plan with a short summary of the plan. "
    "If it reports contradictions, stop and tell the user before writing the "
    "affected code. If it reports missing agreements, those are choices nobody "
    "has made yet. Keep the user moving: when the choice is part of the task "
    "the user gave you, make a sensible choice, record it with record_decision "
    "and continue. The first recorded decision becomes the team's. Call "
    "request_decision only when the user asks to put a question to the team, "
    "or when the choice clearly belongs to a teammate's part of the project. "
    "Open at most two requests for one task, tell the user they are answered "
    "on the dashboard, and carry on with the work that does not depend on "
    "them. Never record your own answer to a question that is already open "
    "for the team. "
    "Whenever you make or accept a project decision that a teammate's agent would "
    "need to know, call record_decision BEFORE writing the code for it. This "
    "includes: choosing a language, framework, library or database; defining an "
    "API endpoint and what it returns; naming a data field or table; choosing a "
    "port; and setting a project convention. Do this without being asked. "
    "Record one decision per call, as one short factual sentence. "
    "If the user asks for something that contradicts the contract, still call "
    "record_decision with what they asked for: the server logs the conflict so "
    "the whole team sees it. Then stop and ask the user how to proceed. "
    "Do not record a decision that is already in the contract, and do not record "
    "small local details such as a helper function's name. "
    "Sharing code: when the room is linked to GitHub, four tools handle Git for "
    "the user, so they never need the terminal. Use them only when the user asks. "
    "start_task: the user wants to begin a new piece of work. share_work: the "
    "user wants teammates to see or review their work; first commit the files "
    "that belong to the task with git, then call it. get_latest: the user wants "
    "the newest code from the team. branch_status: the user asks where their "
    "branch or pull request stands. Tell the user in plain words what happened "
    "and give them the pull request link when there is one. The tools' replies "
    "may mention terminal commands (python3 coord/git_sync.py start, publish, "
    "watch, status); those are the same actions as start_task, share_work, "
    "get_latest and branch_status. Reviewing and merging pull requests, and "
    "linking a room to a repository, are done by people, never by you."
)

TOOL = {
    "name": "record_decision",
    "description": (
        "Record one project decision in the team contract, so every teammate's AI "
        "agent sees it before writing code. Call this BEFORE writing code, each "
        "time you choose a framework, library or database, define an API endpoint "
        "or its response shape, name a data field, pick a port, or set a "
        "convention. One decision per call. The reply says whether it was recorded "
        "or whether it conflicts with an earlier team decision."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "category": {
                "type": "string",
                "enum": CATEGORIES,
                "description": (
                    "stack = language, framework, library, database. "
                    "api = endpoints, request and response shapes, ports. "
                    "data = field, table and variable names shared across files. "
                    "convention = folder layout, naming style, testing rules. "
                    "other = anything else teammates must know."
                ),
            },
            "text": {
                "type": "string",
                "description": (
                    "The decision as one short factual sentence. Examples: "
                    "'Backend is Django with SQLite.' "
                    "'POST /login returns {\"token\": string}.' "
                    "'User IDs are called user_id, not userId.'"
                ),
            },
        },
        "required": ["category", "text"],
    },
}

PLAN_TOOL = {
    "name": "check_plan",
    "description": (
        "Review a coding plan before making changes that affect teammates. Returns "
        "contradictions with the team contract (stop and tell the user) and choices the "
        "team has not made yet (usually: decide, then record_decision). A review does not "
        "change the contract."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {"plan": {"type": "string", "maxLength": 4000}},
        "required": ["plan"],
    },
}

REQUEST_TOOL = {
    "name": "request_decision",
    "description": (
        "Put one question to the whole team, to be answered by a person on the dashboard. "
        "Use it sparingly: only when the user asks for it, or when the choice belongs to a "
        "teammate's part of the project. For choices inside your own task, decide and use "
        "record_decision instead. Reuse the review's topic so teammates share one request. "
        "Options are complete decision statements."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "topic": {"type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$", "maxLength": 80},
            "category": {"type": "string", "enum": CATEGORIES},
            "question": {"type": "string", "maxLength": 240},
            "options": {"type": "array", "items": {"type": "string", "maxLength": 500}, "maxItems": 4},
        },
        "required": ["topic", "category", "question", "options"],
    },
}


START_TOOL = {
    "name": "start_task",
    "description": (
        "Begin a new task for the user: creates a task branch from the team's latest "
        "shared code and switches to it. Call it when the user says they want to start "
        "working on something new. Unsaved edits and commits already made on the shared "
        "branch come along to the new branch, so it is safe to call after work has begun. "
        "Nothing is sent to GitHub."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": (
                    "A short, unique branch name: the user's name, a slash, and the topic "
                    "in lowercase with dashes. Example: 'ali/todo-delete'."
                ),
            },
        },
        "required": ["name"],
    },
}

SHARE_TOOL = {
    "name": "share_work",
    "description": (
        "Share the user's committed work with the team: pushes the task branch to GitHub "
        "and opens a pull request, or updates the one that is already open. Call it when "
        "the user asks to share, publish or send their work for review. Only commits are "
        "shared, so first commit the files that belong to this task with git (stage the "
        "specific files; leave out secrets and unrelated files). If the reply says the "
        "current branch is the shared branch, call start_task and then share_work again. "
        "Before pushing, the changed code is checked against the team contract. If the "
        "reply says the code breaks a team decision, nothing was shared: tell the user "
        "which decision and where, and either fix the code or ask the user. "
        "The reply includes the pull request link: give it to the user."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "maxLength": 120,
                "description": "Title for a new pull request, in plain words. Default: the last commit message.",
            },
            "draft": {
                "type": "boolean",
                "description": "true = open it as a draft because the work is not ready for review. Default false.",
            },
            "share_anyway": {
                "type": "boolean",
                "description": (
                    "true = share even though the code breaks a team decision. Use it only "
                    "after the user has been told about the broken decision and said to share anyway."
                ),
            },
        },
    },
}

LATEST_TOOL = {
    "name": "get_latest",
    "description": (
        "Bring the team's newest merged work into the user's copy of the shared branch. "
        "Call it when the user asks for the latest code or to sync. It checks GitHub once "
        "and updates only when that is safe: the user is on the shared branch and has no "
        "unsaved edits to tracked files. It never overwrites the user's work; the reply "
        "says what was applied or why nothing was."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "include_unapproved": {
                "type": "boolean",
                "description": (
                    "false (default) = only pull requests that a teammate approved. "
                    "true = every merged pull request. Use true when the reply says newer "
                    "commits were left alone and the user confirms they want them."
                ),
            },
        },
    },
}

STATUS_TOOL = {
    "name": "branch_status",
    "description": (
        "Report where the user's current branch stands: how many commits it is ahead of "
        "and behind the shared branch, and its pull request and review status. Also "
        "updates the team dashboard. Call it when the user asks about their branch or "
        "pull request. Changes no files."
    ),
    "inputSchema": {"type": "object", "properties": {}},
}


def log(message: str) -> None:
    print(f"team-contract: {message}", file=sys.stderr, flush=True)


class ContractChanged(ValueError):
    """A teammate changed the contract while the server was checking. Safe to retry."""


def post(path: str, arguments: dict) -> dict:
    try:
        me = json.loads(ME_FILE.read_text())
        name, room, server = me["name"], me["room"], me["server"].rstrip("/")
    except Exception as error:
        raise ValueError("Run the installer to configure coord/me.json.") from error

    body = {**arguments, "room": room, "author": name}
    request = urllib.request.Request(
        f"{server}{path}",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:300]
        if error.code == 409 and "changed during the check" in detail:
            raise ContractChanged(detail) from error
        raise ValueError(f"The server rejected the request ({error.code}): {detail}") from error
    except Exception as error:
        raise ValueError(f"Could not reach the team contract server at {server} ({error!r}).") from error


def record_decision(arguments: dict) -> str:
    text = str(arguments.get("text", "")).strip()
    body = {"category": arguments.get("category"), "text": text}
    try:
        reply = post("/decisions", body)
    except ContractChanged:
        # Two agents recorded at the same moment. The second try is checked
        # against the contract that now includes the teammate's decision.
        reply = post("/decisions", body)

    conflict = reply.get("conflict")
    if conflict:
        return (
            "CONFLICT with the team contract. "
            f"{conflict.get('explanation', '')} "
            f"Existing decision: \"{conflict.get('existing_text', '')}\" "
            f"(by {conflict.get('existing_author', 'a teammate')}). "
            "Stop. Do not write code for this decision. Tell the user about the "
            "conflict. A human settles it on the team dashboard: keep the team's "
            "decision, or switch to the new one. If they switch, the contract in "
            "your next prompt shows it. Until then, follow the existing decision."
        )

    duplicate = reply.get("duplicate")
    if duplicate:
        return (
            f"Already in the team contract: \"{duplicate.get('text', '')}\" "
            f"(by {duplicate.get('author', 'a teammate')}). Nothing new was recorded. "
            "Follow the existing decision."
        )

    note = ""
    check = str(reply.get("check", ""))
    if check.startswith("skipped"):
        note = (
            f" Note: the conflict check did not run ({check}), so this decision "
            "was not compared with the rest of the contract."
        )
    decision = reply["decision"]
    return f"Recorded in the team contract: [{decision['category']}] {decision['text']} (by {decision['author']}).{note}"


def check_plan(arguments: dict) -> str:
    review = post("/plans/check", arguments)
    return json.dumps(review, ensure_ascii=False)


def request_decision(arguments: dict) -> str:
    reply = post("/decision-requests", arguments)
    request = reply["request"]
    if reply["decision"]:
        return f"Request #{request['id']} was answered: {reply['decision']['text']}"
    state = "Opened" if reply["created"] else "Already open"
    return f"{state}: request #{request['id']}, {request['question']} Wait for a human to answer on the dashboard."


def run_git_helper(*args: str) -> str:
    """Run coord/git_sync.py and return what it printed.

    The helper is the same program people run in a terminal, so the agent and
    the terminal can never behave differently. Its output is captured: this
    script's own stdout is reserved for protocol messages.
    """
    if not GIT_HELPER.is_file():
        raise ValueError("coord/git_sync.py is missing. Rerun the Team Contract installer.")
    try:
        run = subprocess.run(
            [sys.executable, str(GIT_HELPER), *args],
            capture_output=True, text=True, timeout=GIT_TIMEOUT_SECONDS, stdin=subprocess.DEVNULL,
        )
    except subprocess.TimeoutExpired:
        raise ValueError("The Git step took too long and was stopped. Check the network, then try again.") from None
    output = "\n".join(part.strip() for part in (run.stdout, run.stderr) if part.strip())
    if run.returncode:
        raise ValueError(output or "The Git step failed.")
    return output or "Done."


def start_task(arguments: dict) -> str:
    name = str(arguments.get("name", "")).strip()
    if not name or name.startswith("-"):
        raise ValueError("Give the task a short name, for example ali/todo-delete.")
    return run_git_helper("start", name)


def share_work(arguments: dict) -> str:
    args = ["publish"]
    if not arguments.get("draft"):
        args.append("--ready")
    title = " ".join(str(arguments.get("title") or "").split())
    if title:
        args.append(f"--title={title}")
    if arguments.get("share_anyway"):
        args.append("--anyway")
    return run_git_helper(*args)


def get_latest(arguments: dict) -> str:
    args = ["watch", "--once"]
    if arguments.get("include_unapproved"):
        args.append("--any-merge")
    return run_git_helper(*args)


def branch_status(arguments: dict) -> str:
    return run_git_helper("status")


TOOLS = {
    "record_decision": (TOOL, record_decision),
    "check_plan": (PLAN_TOOL, check_plan),
    "request_decision": (REQUEST_TOOL, request_decision),
    "start_task": (START_TOOL, start_task),
    "share_work": (SHARE_TOOL, share_work),
    "get_latest": (LATEST_TOOL, get_latest),
    "branch_status": (STATUS_TOOL, branch_status),
}


def handle(message: dict) -> dict | None:
    """Answer one protocol message. Returns None when no reply is expected."""
    method = message.get("method")
    message_id = message.get("id")
    if message_id is None:
        return None  # a notification, e.g. notifications/initialized

    def result(payload: dict) -> dict:
        return {"jsonrpc": "2.0", "id": message_id, "result": payload}

    if method == "initialize":
        params = message.get("params") or {}
        return result(
            {
                "protocolVersion": params.get("protocolVersion", "2024-11-05"),
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "team-contract", "version": "0.2.0"},
                "instructions": INSTRUCTIONS,
            }
        )
    if method == "ping":
        return result({})
    if method == "tools/list":
        return result({"tools": [tool for tool, _ in TOOLS.values()]})
    if method == "tools/call":
        params = message.get("params") or {}
        tool = TOOLS.get(params.get("name"))
        if tool is None:
            text, is_error = f"Unknown tool: {params.get('name')}", True
        else:
            try:
                text, is_error = tool[1](params.get("arguments") or {}), False
            except ValueError as error:
                text, is_error = str(error), True
        return result({"content": [{"type": "text", "text": text}], "isError": is_error})
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": -32601, "message": f"Method not found: {method}"},
    }


def main() -> None:
    log("started")
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            reply = handle(json.loads(line))
        except Exception as error:  # never crash on one bad message
            log(f"could not handle message: {error!r}")
            continue
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
