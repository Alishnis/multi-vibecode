"""Coordination server: stores the team contract (a list of decisions per room).

Run from the project root:
    .venv/bin/uvicorn server.server:app --port 8000

A page listing every request is generated at http://localhost:8000/docs
"""

import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = Path(__file__).parent / "contract.db"

log = logging.getLogger("uvicorn.error")

Category = Literal["stack", "api", "data", "convention", "other"]


def load_env_file() -> None:
    """Read KEY=VALUE lines from .env in the project root into the environment."""
    env_file = PROJECT_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:  # an empty placeholder counts as "not set"
            os.environ.setdefault(key.strip(), value)


load_env_file()

from . import conflicts  # noqa: E402  (imported after .env is loaded)


def connect() -> sqlite3.Connection:
    """Open the database file. Each request opens and closes its own connection."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # rows behave like dictionaries
    return conn


def create_tables() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                room       TEXT NOT NULL,
                author     TEXT NOT NULL,
                category   TEXT NOT NULL,
                text       TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        # A conflict is a decision that was NOT added, and the one it contradicts.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS conflicts (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                room            TEXT NOT NULL,
                new_author      TEXT NOT NULL,
                new_category    TEXT NOT NULL,
                new_text        TEXT NOT NULL,
                existing_id     INTEGER,
                existing_author TEXT NOT NULL,
                existing_text   TEXT NOT NULL,
                explanation     TEXT NOT NULL,
                created_at      TEXT NOT NULL
            )
            """
        )


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_decisions(room: str) -> list[dict]:
    """All decisions for one room, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, room, author, category, text, created_at "
            "FROM decisions WHERE room = ? ORDER BY id",
            (room,),
        ).fetchall()
    return [dict(row) for row in rows]


def load_conflicts(room: str) -> list[dict]:
    """All conflicts for one room, newest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM conflicts WHERE room = ? ORDER BY id DESC", (room,)
        ).fetchall()
    return [dict(row) for row in rows]


def contract_as_text(decisions: list[dict]) -> str:
    """The contract as plain lines, ready for a hook to print into an agent's context."""
    if not decisions:
        return "The team contract is empty. No decisions have been recorded yet."
    lines = ["Team contract (decisions already made by the team):"]
    for d in decisions:
        lines.append(f"- [{d['category']}] {d['text']} (by {d['author']})")
    return "\n".join(lines)


class NewDecision(BaseModel):
    """What a client sends to record a decision."""

    room: str = Field(min_length=1, max_length=50)
    author: str = Field(min_length=1, max_length=50)
    category: Category
    text: str = Field(min_length=1, max_length=500)


def save_decision(decision: NewDecision) -> dict:
    created_at = now()
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO decisions (room, author, category, text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (decision.room, decision.author, decision.category, decision.text, created_at),
        )
    return {"id": cursor.lastrowid, **decision.model_dump(), "created_at": created_at}


def save_conflict(decision: NewDecision, existing: dict | None, explanation: str) -> dict:
    conflict = {
        "room": decision.room,
        "new_author": decision.author,
        "new_category": decision.category,
        "new_text": decision.text,
        "existing_id": existing["id"] if existing else None,
        "existing_author": existing["author"] if existing else "a teammate",
        "existing_text": existing["text"] if existing else "",
        "explanation": explanation,
        "created_at": now(),
    }
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO conflicts (room, new_author, new_category, new_text, existing_id, "
            "existing_author, existing_text, explanation, created_at) "
            "VALUES (:room, :new_author, :new_category, :new_text, :existing_id, "
            ":existing_author, :existing_text, :explanation, :created_at)",
            conflict,
        )
    return {"id": cursor.lastrowid, **conflict}


app = FastAPI(title="Team contract server")
create_tables()
if not conflicts.is_configured():
    log.warning("No OPENROUTER_API_KEY in .env: decisions are saved WITHOUT a conflict check.")


@app.post("/decisions")
def add_decision(decision: NewDecision) -> dict:
    """Check one decision against the contract, then save it if it fits.

    The reply always has the same four fields:
      decision  - the saved decision, or null if it was not added
      conflict  - set when it contradicts the contract (not added)
      duplicate - set when the contract already says this (not added)
      check     - "checked", "not needed" (empty contract) or "skipped: <why>"
    """
    reply = {"decision": None, "conflict": None, "duplicate": None, "check": "checked"}
    existing = load_decisions(decision.room)

    verdict = None
    if not existing:
        reply["check"] = "not needed"
    else:
        try:
            verdict = conflicts.check_decision(decision.category, decision.text, existing)
        except conflicts.CheckerUnavailable as error:
            # Fail open: a broken checker must not stop the team from working.
            log.warning("Conflict check skipped: %s", error)
            reply["check"] = f"skipped: {error}"

    if verdict and verdict.verdict != "ok":
        matched = next((d for d in existing if d["id"] == verdict.existing_id), None)
        if verdict.verdict == "conflict":
            reply["conflict"] = save_conflict(decision, matched, verdict.explanation)
            return reply
        if matched:  # a duplicate only counts if it points at a real decision
            reply["duplicate"] = matched
            return reply

    reply["decision"] = save_decision(decision)
    return reply


@app.get("/contract")
def get_contract(room: str) -> dict:
    """The contract for one room: as a list, and as ready-to-print text."""
    decisions = load_decisions(room)
    return {"room": room, "decisions": decisions, "text": contract_as_text(decisions)}


@app.get("/state")
def get_state(room: str) -> dict:
    """Everything the dashboard shows."""
    return {
        "room": room,
        "decisions": load_decisions(room),
        "conflicts": load_conflicts(room),
        "checker": "on" if conflicts.is_configured() else "off",
    }
