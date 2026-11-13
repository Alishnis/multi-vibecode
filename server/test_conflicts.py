"""Test set for the conflict checker: 15 hand-written cases.

Each case is one new decision, checked against the same small contract.
Run from the project root (uses real API calls, costs a fraction of a cent):

    .venv/bin/python -m server.test_conflicts

The target is at least 13 of 15 correct.
"""

import sys
import time

from .server import load_env_file

load_env_file()

from . import conflicts  # noqa: E402

CONTRACT = [
    {"id": 1, "category": "stack", "text": "Backend is Django with SQLite."},
    {"id": 2, "category": "api", "text": 'POST /login returns {"token": string}.'},
    {"id": 3, "category": "api", "text": "The backend API runs on port 8001."},
    {"id": 4, "category": "data", "text": "User IDs are called user_id, not userId."},
    {"id": 5, "category": "convention", "text": "All API JSON fields use snake_case."},
]

# (category, new decision, expected verdict, id of the decision it should point at)
CASES = [
    # --- conflicts ---
    ("stack", "Backend is Express on Node.js.", "conflict", 1),
    ("stack", "The database is PostgreSQL.", "conflict", 1),
    ("stack", "Add an Express server that serves the /todos endpoint.", "conflict", 1),
    ("api", 'POST /login returns {"access_token": string, "user": object}.', "conflict", 2),
    ("api", "The backend API server listens on port 3000.", "conflict", 3),
    ("data", "The user identifier field is named userId in all JSON.", "conflict", 4),
    ("convention", "API JSON fields use camelCase.", "conflict", 5),
    # --- fine to add ---
    ("stack", "Frontend is React with Vite.", "ok", 0),
    ("stack", "The API is built with Django REST Framework.", "ok", 0),
    ("api", 'GET /todos returns a JSON array of {"id": int, "title": string, "done": bool}.', "ok", 0),
    ("data", "Todo items have an owner_id field that stores the user_id of their creator.", "ok", 0),
    ("api", "The frontend dev server runs on port 5173.", "ok", 0),
    ("convention", "Tests are written with pytest.", "ok", 0),
    # --- already in the contract ---
    ("stack", "The backend framework is Django, with a SQLite database.", "duplicate", 1),
    ("data", "Use user_id as the name for user identifiers.", "duplicate", 4),
]


def main() -> None:
    if not conflicts.is_configured():
        sys.exit("No OPENROUTER_API_KEY found. Copy .env.example to .env and add your key.")

    correct = 0
    total_seconds = 0.0
    for number, (category, text, expected, expected_id) in enumerate(CASES, start=1):
        started = time.time()
        try:
            verdict = conflicts.check_decision(category, text, CONTRACT)
        except conflicts.CheckerUnavailable as error:
            sys.exit(f"Checker unavailable: {error}")
        seconds = time.time() - started
        total_seconds += seconds

        passed = verdict.verdict == expected and (
            expected == "ok" or verdict.existing_id == expected_id
        )
        correct += passed
        mark = "PASS" if passed else "FAIL"
        print(f"{number:2}. {mark}  expected {expected:9} got {verdict.verdict:9} "
              f"({seconds:.1f}s)  {text[:60]}")
        if verdict.explanation:
            print(f"          -> id {verdict.existing_id}: {verdict.explanation}")

    print(f"\nModel: {conflicts.model_name()}")
    print(f"{correct} of {len(CASES)} correct. "
          f"Average {total_seconds / len(CASES):.1f}s per check.")
    sys.exit(0 if correct >= 13 else 1)


if __name__ == "__main__":
    main()
