#!/usr/bin/env python3
"""MCP server that gives the agent one tool: record_decision.

Claude Code starts this script (see .mcp.json) and talks to it over stdin and
stdout, one JSON message per line. This is the MCP "stdio" protocol.

It uses only Python's built-in libraries, so teammates install nothing.

Important: stdout is reserved for protocol messages. Anything for humans goes
to stderr.
"""

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ME_FILE = Path(__file__).resolve().parent.parent / "me.json"  # coord/me.json
TIMEOUT_SECONDS = 30  # generous: slice 4 adds an AI conflict check on the server
CATEGORIES = ["stack", "api", "data", "convention", "other"]

INSTRUCTIONS = (
    "This project has a team contract: a shared list of decisions that every "
    "teammate's AI agent reads before it acts. The current contract is added to "
    "your context on every prompt. "
    "Whenever you make or accept a project decision that a teammate's agent would "
    "need to know, call record_decision BEFORE writing the code for it. This "
    "includes: choosing a language, framework, library or database; defining an "
    "API endpoint and what it returns; naming a data field or table; choosing a "
    "port; and setting a project convention. Do this without being asked. "
    "Record one decision per call, as one short factual sentence. "
    "Do not record a decision that is already in the contract, and do not record "
    "small local details such as a helper function's name."
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


def log(message: str) -> None:
    print(f"team-contract: {message}", file=sys.stderr, flush=True)


def record_decision(arguments: dict) -> tuple[str, bool]:
    """Send one decision to the coordination server. Returns (reply text, is_error)."""
    category = arguments.get("category")
    text = str(arguments.get("text", "")).strip()
    if category not in CATEGORIES:
        return f"Not recorded: category must be one of {', '.join(CATEGORIES)}.", True
    if not text:
        return "Not recorded: text is empty.", True

    try:
        me = json.loads(ME_FILE.read_text())
        name, room, server = me["name"], me["room"], me["server"].rstrip("/")
    except Exception as error:
        return (
            f"Not recorded: could not read {ME_FILE} ({error!r}). Tell the user to "
            "copy coord/me.example.json to coord/me.json and fill it in.",
            True,
        )

    body = {"room": room, "author": name, "category": category, "text": text}
    request = urllib.request.Request(
        f"{server}/decisions",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            reply = json.load(response)
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")[:300]
        return f"Not recorded: the server rejected it ({error.code}): {detail}", True
    except Exception as error:
        return (
            f"Not recorded: could not reach the team contract server at {server} "
            f"({error!r}). Tell the user the decision was NOT shared with the team.",
            True,
        )

    conflict = reply.get("conflict")
    if conflict:  # filled in by the server from slice 4 onward
        return (
            "CONFLICT with the team contract. "
            f"{conflict.get('explanation', '')} "
            f"Existing decision: \"{conflict.get('existing_text', '')}\" "
            f"(by {conflict.get('existing_author', 'a teammate')}). "
            "Stop. Do not write code for this decision. Tell the user about the "
            "conflict and ask whether to follow the team's decision or change it."
        ), False
    return f"Recorded in the team contract: [{category}] {text} (by {name}).", False


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
                "serverInfo": {"name": "team-contract", "version": "0.1.0"},
                "instructions": INSTRUCTIONS,
            }
        )
    if method == "ping":
        return result({})
    if method == "tools/list":
        return result({"tools": [TOOL]})
    if method == "tools/call":
        params = message.get("params") or {}
        if params.get("name") != TOOL["name"]:
            text, is_error = f"Unknown tool: {params.get('name')}", True
        else:
            text, is_error = record_decision(params.get("arguments") or {})
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
