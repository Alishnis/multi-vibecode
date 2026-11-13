#!/usr/bin/env python3
"""MCP tools for reviewing plans and sharing team decisions.

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

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # the coord folder
try:
    from tc_http import urlopen
except ImportError:  # an older install without coord/tc_http.py
    from urllib.request import urlopen

ME_FILE = Path(__file__).resolve().parent.parent / "me.json"  # coord/me.json
TIMEOUT_SECONDS = 30  # generous: the server asks an AI model to check each decision
CATEGORIES = ["stack", "api", "data", "convention", "other"]

INSTRUCTIONS = (
    "This project has a team contract: a shared list of decisions that every "
    "teammate's AI agent reads before it acts. The current contract is added to "
    "your context on every prompt. Before implementing a plan that affects "
    "teammates, call check_plan with a short summary of shared assumptions. "
    "Report contradictions before writing affected code. For a missing team "
    "agreement, call request_decision using the topic from the review. Tell "
    "the user to answer it on the dashboard and wait before relying on it. "
    "Never record your own answer to a pending team decision. "
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

PLAN_TOOL = {
    "name": "check_plan",
    "description": (
        "Review a coding plan before making changes that affect teammates. "
        "Returns contradictions and missing agreements. A review does not change the contract."
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
        "Ask a human to decide a missing shared agreement on the dashboard. "
        "Reuse the review's topic so teammates share one request. Options are complete decision statements."
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


TOOLS = {
    "record_decision": (TOOL, record_decision),
    "check_plan": (PLAN_TOOL, check_plan),
    "request_decision": (REQUEST_TOOL, request_decision),
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
                "serverInfo": {"name": "team-contract", "version": "0.1.0"},
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
