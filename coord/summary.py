"""The room in plain words, and the one thing to do next.

./coopdev today prints this in the terminal, and the team_status agent tool gives
it to Claude, so nobody has to read raw data. Built-in libraries only.

describe() takes the dashboard's /state reply and the reader's own name.
Teammates' text (tasks, messages, requests) is shown as quoted data.
"""

ACTIVE_SECONDS = 600   # active in the last 10 minutes counts as "active now"
SHOW = 3               # list at most this many items per section


def clean(value, limit: int = 120) -> str:
    """One printable line, so remote text cannot move the cursor or fake a new line."""
    text = " ".join(str(value or "").split())
    text = "".join(char if char.isprintable() else "?" for char in text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def quoted(value, limit: int = 120) -> str:
    return "“" + clean(value, limit) + "”"


def when(seconds) -> str:
    if not isinstance(seconds, (int, float)):
        return "time unknown"
    if seconds < ACTIVE_SECONDS:
        return "active now"
    if seconds < 3600:
        return f"{int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"{int(seconds // 3600)} h ago"
    return f"{int(seconds // 86400)} d ago"


def more(items: list, shown: int) -> list[str]:
    return [f"  …and {len(items) - shown} more on the dashboard"] if len(items) > shown else []


def same(a, b) -> bool:
    return str(a or "").lower() == str(b or "").lower()


def describe(state: dict, name: str, dashboard: str = "") -> str:
    """Several short sections, most urgent first, and a single next step at the end."""
    people = state.get("people") or []
    claims = state.get("claims") or []
    asks = state.get("asks") or []
    conflicts = [c for c in state.get("conflicts") or [] if not c.get("resolution")]
    questions = [r for r in state.get("decision_requests") or [] if r.get("decision_id") is None]
    decisions = state.get("decisions") or []
    messages = state.get("messages") or []
    edits = (state.get("files") or {}).get("edits") or []
    git = state.get("git") or {}

    out = [f"Room {clean(state.get('room'), 50)}, as {clean(name, 50)}."]

    teammates = [p for p in people if not same(p.get("name"), name)]
    if teammates:
        out.append("Teammates: " + ", ".join(
            f"{clean(p['name'], 40)} ({when(p.get('seconds_ago'))})" for p in teammates[:6]) + ".")
    else:
        out.append("Teammates: nobody else has joined yet.")

    # 1. Things only this person can move forward.
    waiting = [a for a in asks if same(a.get("to"), name) and a.get("status") == "pending"]
    approved = [a for a in asks if same(a.get("to"), name) and a.get("status") == "approved" and a.get("via") == "dashboard"]
    needs = []
    for a in waiting[:SHOW]:
        limits = "may edit files" if a.get("can_edit") else "read only"
        needs.append(f"  • Request #{a.get('id')} from {clean(a.get('from'), 40)} ({limits}): "
                     f"{quoted(a.get('prompt'))}. Open Claude; it will ask you yes or no.")
    for a in approved[:SHOW]:
        needs.append(f"  • Request #{a.get('id')} is approved. Your agent runs it on your next prompt.")
    for c in conflicts[:SHOW]:
        needs.append(f"  • Conflict: {clean(c.get('new_author'), 40)}'s AI wanted {quoted(c.get('new_text'), 80)}, "
                     f"but the team decided {quoted(c.get('existing_text'), 80)}. Settle it on the dashboard.")
    for r in questions[:SHOW]:
        needs.append(f"  • Open question: {quoted(r.get('question'))}. Answer it on the dashboard.")
    out.append("Needs you:" if needs else "Needs you: nothing right now.")
    out += needs

    # 2. This person's own work.
    mine = []
    for c in [c for c in claims if same(c.get("author"), name)][:SHOW]:
        span = f"until {clean(c.get('branch'), 60)} merges" if c.get("until_merged") else f"{c.get('minutes_left')} min left"
        mine.append(f"  • You claimed {', '.join(clean(p, 60) for p in (c.get('paths') or [])[:3])} "
                    f"for {quoted(c.get('task'), 80)} ({span}).")
    for g in [g for g in git.get("activity") or [] if same(g.get("author"), name)][:1]:
        pr = {"draft": "draft", "in_review": "ready for review", "approved": "approved",
              "changes_requested": "changes requested"}.get(g.get("pr_state"))
        line = f"  • Your branch {clean(g.get('branch'), 60)}: {g.get('ahead', 0)} commit(s) of yours"
        if g.get("behind"):
            line += f", {g['behind']} behind the shared branch"
        if g.get("pr_number"):
            line += f", pull request #{g['pr_number']}" + (f" ({pr})" if pr else "")
        mine.append(line + ".")
    for a in [a for a in asks if same(a.get("from"), name)][:SHOW]:
        status = {"pending": "waiting for their OK", "approved": "approved, running", "done": "done",
                  "declined": "declined", "expired": "expired", "cancelled": "cancelled"}.get(a.get("status"), a.get("status"))
        line = f"  • Your request #{a.get('id')} to {clean(a.get('to'), 40)}: {status}"
        if a.get("status") == "done" and a.get("result"):
            line += f". Answer: {quoted(a.get('result'), 160)}"
        mine.append(line + ".")
    if mine:
        out.append("Your work:")
        out += mine

    # 3. What teammates are doing.
    theirs = [c for c in claims if not same(c.get("author"), name)]
    recent = [e for e in edits if not same(e.get("author"), name)]
    if theirs or recent:
        out.append("Teammates are working on:")
        for c in theirs[:SHOW]:
            out.append(f"  • {clean(c.get('author'), 40)}: {quoted(c.get('task'), 80)} "
                       f"({', '.join(clean(p, 60) for p in (c.get('paths') or [])[:3])}). Leave these files to them.")
        out += more(theirs, SHOW)
        for e in recent[:SHOW]:
            out.append(f"  • {clean(e.get('author'), 40)} edited {clean(e.get('path'), 80)}"
                       + (f": {clean(e.get('summary'), 100)}" if e.get("summary") else "") + ".")

    # 4. Latest chat.
    if messages:
        out.append("Latest messages:")
        for m in messages[-SHOW:]:
            to = f" (to {clean(m.get('to'), 40)})" if m.get("to") else ""
            out.append(f"  • {clean(m.get('author'), 40)}{to}: {quoted(m.get('text'), 160)}")

    out.append(f"Team decisions in force: {len(decisions)}.")

    # 5. One next step, the most useful first.
    if waiting:
        step = f"answer request #{waiting[0].get('id')} from {clean(waiting[0].get('from'), 40)}: open Claude and say yes or no."
    elif conflicts:
        step = "settle the conflict on the dashboard: keep the team's decision, or switch."
    elif questions:
        step = "answer the open question on the dashboard."
    elif not teammates:
        step = "invite a teammate: press Copy invite on the dashboard and send it to them."
    elif not any(same(c.get("author"), name) for c in claims):
        step = "start a task: open Claude and say what you want to build. It claims the files first."
    else:
        step = "keep building. When it works, tell Claude: “share my work”."
    out.append("Next step: " + step)
    if dashboard:
        out.append(f"Dashboard: {dashboard}")
    return "\n".join(out)
