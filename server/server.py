"""Coordination server: stores the team contract (a list of decisions per room).

Run from the project root:
    .venv/bin/uvicorn server.server:app --port 8000

A page listing every request is generated at http://localhost:8000/docs
"""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).parent / "contract.db"

Category = Literal["stack", "api", "data", "convention", "other"]


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


def load_decisions(room: str) -> list[dict]:
    """All decisions for one room, oldest first."""
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, room, author, category, text, created_at "
            "FROM decisions WHERE room = ? ORDER BY id",
            (room,),
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


app = FastAPI(title="Team contract server")
create_tables()


@app.post("/decisions")
def add_decision(decision: NewDecision) -> dict:
    """Save one decision. Slice 4 will fill in `conflict` when it contradicts the contract."""
    created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with connect() as conn:
        cursor = conn.execute(
            "INSERT INTO decisions (room, author, category, text, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (decision.room, decision.author, decision.category, decision.text, created_at),
        )
        new_id = cursor.lastrowid
    return {
        "decision": {"id": new_id, **decision.model_dump(), "created_at": created_at},
        "conflict": None,
    }


@app.get("/contract")
def get_contract(room: str) -> dict:
    """The contract for one room: as a list, and as ready-to-print text."""
    decisions = load_decisions(room)
    return {"room": room, "decisions": decisions, "text": contract_as_text(decisions)}


@app.get("/state")
def get_state(room: str) -> dict:
    """Everything the dashboard shows. `conflicts` stays empty until slice 4."""
    return {"room": room, "decisions": load_decisions(room), "conflicts": []}
