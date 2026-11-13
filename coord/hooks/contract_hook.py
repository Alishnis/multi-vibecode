#!/usr/bin/env python3
"""UserPromptSubmit hook: adds the team contract to the agent's context.

Claude Code runs this script every time the user sends a prompt. Whatever the
script prints is added to what the agent sees, next to the prompt.

It uses only Python's built-in libraries, so teammates install nothing.

Rule: this script must never stop the user's prompt. If anything goes wrong
(no me.json, server down), it prints nothing and exits with code 0. The reason
is written to stderr, which Claude Code shows only in debug mode.
"""

import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ME_FILE = Path(__file__).resolve().parent.parent / "me.json"  # coord/me.json
TIMEOUT_SECONDS = 3


def give_up(reason: str) -> None:
    print(f"contract hook skipped: {reason}", file=sys.stderr)
    sys.exit(0)


def main() -> None:
    try:
        me = json.loads(ME_FILE.read_text())
        room, server = me["room"], me["server"].rstrip("/")
    except FileNotFoundError:
        give_up(f"{ME_FILE} not found (copy coord/me.example.json to coord/me.json)")
    except (json.JSONDecodeError, KeyError, AttributeError) as error:
        give_up(f"{ME_FILE} is not valid: {error!r}")

    query = {"room": room, "name": me.get("name", "")}  # the name marks this person as active
    url = f"{server}/contract?" + urllib.parse.urlencode(query)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            contract = json.load(response)
    except Exception as error:  # server down, wrong address, bad reply
        give_up(f"could not reach {url}: {error!r}")

    print(contract["text"])
    if contract["decisions"]:
        print(
            "These decisions apply to this project. When a request contradicts one "
            "of them, the requested decision is first submitted with the "
            "team-contract record_decision tool, so that the conflict is logged for "
            "the whole team, and then the conflict is raised with the user before "
            "any code is written."
        )
    # Repeated on every prompt, because agents forget instructions given once.
    print(
        "New project decisions made in this session (framework, library, database, "
        "API endpoint, data field name, port, convention) are recorded with the "
        "team-contract record_decision tool before the code for them is written, "
        "one call per decision, so that teammates' agents see them."
    )


if __name__ == "__main__":
    main()
