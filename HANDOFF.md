# Handoff: team contract tool for multi-person AI coding

You are taking over a project from another AI assistant. This file is everything you need to continue. Read it fully before acting. It was written on 2026-11-13 and every "verified" claim below was checked on that date.

## 1. Who you are working with

- A team of 3-4 first-year Computer Science students (City University of Hong Kong) preparing for a **startup competition** with a **5-minute pitch**. Judges are not technical.
- They build with AI coding tools ("vibecoding") and have basic IT knowledge. Their stack comfort is **Python**. Their git knowledge is basic.
- One person is doing all the early work alone. The other teammates join later.
- Budget is close to zero. They pay for AI calls through **OpenRouter** and want cheap models.

### How the user wants you to work

These are standing instructions from the user. Follow them.

1. **Explain simply.** Short sentences, plain words, define jargon the first time. Use tables and checklists.
2. **List your steps before acting.** A short numbered list of what you are about to do, then do it, then report in the same order. The user reports this work to others and must be able to explain it.
3. **Commit and push after each finished stage**, to `main`, only after that stage's test passes. One commit per stage with a plain message.
4. **No attribution lines** in commits (no "Co-Authored-By").
5. **Never ask for, print or commit secrets.** The OpenRouter key lives in `.env` (ignored by git) and in Render's settings. If a key is needed somewhere, tell the user where to paste it.
6. **Be honest about what is and is not verified.** Say "not tested" when it is not tested. The user asked for criticism, not encouragement.
7. If you are unsure of a fact about a tool (Claude Code, Render, OpenRouter), check its documentation instead of guessing.

## 2. What the product is

**One sentence:** a shared "team contract" that every teammate's Claude Code agent reads before it acts and writes to when it decides something, with a warning when a new decision contradicts an old one.

**The problem it solves:** when several people each use an AI coding agent on one project, the agents cannot see each other. One picks Python, another picks Node.js. One names a field `user_id`, another `userId`. Git merges this without complaint and the app breaks later. This is a **decision conflict**, as opposed to a file conflict.

**Positioning:** a competitor, agentmash (`agentmash.dev`, launched around early November 2026, $16-20 per developer per month), warns agents about overlapping **file** edits. This project's wedge is **decisions, not files**. Important: nobody has verified that agentmash misses decision conflicts. See section 8.

## 3. Where everything is

| Thing | Location |
|---|---|
| Code on this Mac | `/Users/aliserromankul/Desktop/hacks/multi-vibecode` |
| GitHub repo | `https://github.com/Alishnis/multi-vibecode` (branch `main`) |
| Deployed server | `https://team-contract.onrender.com` (Render free plan) |
| Deployed dashboard | `https://team-contract.onrender.com/?room=demo` |
| Test folders from the two-person test | `/Users/aliserromankul/Desktop/hacks/test-plain-ali`, `test-plain-mei`, `test-tool-ali`, `test-tool-mei` (not in git) |

Latest commit when this was written: `1f197bb`. This file itself is not committed yet.

### Files in the repo

| File | What it is |
|---|---|
| `server/server.py` | The coordination server (FastAPI + SQLite). All requests are here. |
| `server/conflicts.py` | The AI conflict checker. Calls OpenRouter. |
| `server/test_conflicts.py` | 15 hand-written test cases for the checker. |
| `server/dashboard.html` | The live dashboard, one file, no build step. |
| `server/requirements.txt` | `fastapi`, `uvicorn`, `httpx`. |
| `coord/hooks/contract_hook.py` | Claude Code hook. Runs on every prompt and prints the contract into the agent's context. |
| `coord/mcp/server.py` | MCP server giving the agent one tool, `record_decision`. Hand-written, built-in Python only. |
| `coord/me.example.json` | Template for each person's `coord/me.json` (name, room, server address). |
| `.claude/settings.json` | Registers the hook (`UserPromptSubmit`). |
| `.mcp.json` | Registers the MCP server under the name `team-contract`. |
| `install.py` | Adds the tool to any project folder. Merges with existing settings. |
| `start_server.sh` | Starts the server locally so other devices on the same network can reach it. |
| `render.yaml` | Render Blueprint used for the deployment. |
| `.env.example` | Template for `.env` (`OPENROUTER_API_KEY`, optional `CONTRACT_CHECK_MODEL`). |

Not in git on purpose: `.env`, `.venv/`, `server/contract.db`, `coord/me.json`, `.claude/settings.local.json`.

## 4. How it works

```
 Each teammate's laptop                          One server
┌─────────────────────────────┐          ┌──────────────────────────────┐
│ Claude Code                 │          │ server/server.py             │
│  hook (every prompt) ───────┼─ GET ───▶│  /contract  returns decisions│
│  record_decision tool ──────┼─ POST ──▶│  /decisions checks, then     │──▶ OpenRouter
└─────────────────────────────┘          │             saves or blocks  │    (cheap model)
                                         │  /state     for the dashboard│
        Browser: dashboard.html ─ GET ──▶│  /          serves the page  │
                                         └──────────────────────────────┘
```

**Reading the contract (automatic).** On every prompt, Claude Code runs `contract_hook.py`. It fetches `/contract?room=...&name=...` and prints the decisions. Claude Code adds printed text to the agent's context. The agent cannot skip this. The same call marks the person as active.

**Recording a decision (the agent chooses to).** When the agent picks a framework, defines an endpoint, names a field, picks a port or sets a convention, it calls `record_decision(category, text)`. Categories: `stack`, `api`, `data`, `convention`, `other`. The agent is told to do this in three places: the MCP server's instructions, the tool description, and a reminder line the hook prints on every prompt.

**Checking (on the server).** `POST /decisions` compares the new decision with the room's existing ones by asking a model for one verdict:

| Verdict | Server does | Agent is told |
|---|---|---|
| `ok` | Saves the decision | "Recorded" |
| `conflict` | Does not save it; stores a row in `conflicts` | "CONFLICT... Stop. Tell the user and ask whether to follow the team's decision or change it." |
| `duplicate` | Does not save it | "Already in the team contract. Follow the existing decision." |
| checker unavailable | Saves it anyway (fails open) | "Recorded", with a note that it was not checked |

When a user's request contradicts the contract, the agent is instructed to submit it with `record_decision` first, so the conflict is logged and appears on the dashboard, and then ask its human.

### Server requests

| Request | Purpose |
|---|---|
| `POST /decisions` | Body: `room`, `author`, `category`, `text`. Reply always has `decision`, `conflict`, `duplicate`, `check`. |
| `GET /contract?room=&name=` | Decisions as a list and as ready-to-print `text`. |
| `GET /state?room=` | `decisions`, `conflicts`, `people`, `checker` (`on`/`off`), `now`. |
| `POST /reset?room=` | Empties one room. |
| `GET /` | The dashboard. Room comes from `?room=`. |
| `GET /health` | For hosting health checks. |
| `GET /docs` | Auto-generated page listing all requests. |

Database tables: `decisions`, `conflicts`, `people`. Rooms are just a text column; there is no list of rooms and no accounts.

### The checker

- Calls `https://openrouter.ai/api/v1/chat/completions` with a JSON schema for the reply.
- Default model `anthropic/claude-haiku-5.5` ($0.10 in, $0.50 out per million tokens on OpenRouter when checked). Change it with `CONTRACT_CHECK_MODEL` in `.env`. The user explicitly wants cheap models; do not switch to an expensive one without asking.
- Uses `httpx`, because Python's built-in web client failed on this Mac with a certificate error.
- About 2 seconds per check. Skipped entirely when the room is empty.

## 5. How to run and test

All commands run from the project folder.

| Task | Command |
|---|---|
| Start the local server | `sh start_server.sh` (creates `.venv` on first run, prints the addresses) |
| Open the local dashboard | `http://127.0.0.1:8000/?room=demo` |
| Run the checker test set | `.venv/bin/python -m server.test_conflicts` (real API calls, well under one cent; target 13 of 15) |
| Add the tool to a project | `python3 install.py /path/to/project --name NAME --room ROOM --server URL` |
| Empty a room | `curl -X POST "URL/reset?room=ROOM"` or the "Reset room" button |

**Testing agent behaviour without a human.** Run Claude Code from the command line in a folder that has the tool installed:

```
claude -p "PROMPT" --allowedTools "Write,mcp__team-contract__record_decision" --max-turns 20
```

In this mode the project's hook and MCP server load without an approval question. Then read the result from `GET /state` or the database. This is how every agent test below was run.

**Do not test inside the tool's own repo.** It contains `server/`, a FastAPI app, which biases any agent asked to "set up a backend". Use a separate folder prepared with `install.py`.

## 6. What is verified

| Claim | Evidence |
|---|---|
| Hook delivers the contract to the agent | A fresh session answered with an unguessable fact from the contract (a port number) without reading files. |
| Agents record decisions unprompted | Three separate fresh sessions recorded 3, 5 and 6 decisions for a "choose a stack" task that never mentioned recording. |
| Checker accuracy | 15 of 15 on the test set, twice, with `anthropic/claude-haiku-5.5`. |
| Conflict path end to end | Contract said Django; a fresh session asked for an Express server wrote no code, logged the conflict, and asked its human. |
| The problem reproduces | Two agents in plain folders, same task, one user "most comfortable with Python" and one "with JavaScript": one built FastAPI on port 8000, the other a Node.js server on port 3000. |
| The tool fixes it | With the tool, the "JavaScript" user's agent got the identical prompt and built FastAPI, citing the contract. Asked explicitly to rewrite in Express, it wrote nothing and logged two conflicts. |
| Dashboard | Shows decisions, activity, active people and red conflict cards; updates within about a second without reload; works at phone width and in dark mode. |
| Installer | Seven cases: empty folder, folder with existing settings, rerun, broken settings file, missing name, git project with unreachable server, the tool's own folder. |
| Render deployment | `https://team-contract.onrender.com` answers `/health`, serves the dashboard, reports `checker: on`, and blocked a Django-vs-Express pair sent directly to it. |

The task prompt used in the two-person test, which reliably shows the problem:

> Set up the backend for our team's todo app, with one endpoint that lists todos. Create only the minimal starter files. Do not install anything or run any commands. I'm most comfortable with Python.

(Second person: the same, ending "I'm most comfortable with JavaScript.")

## 7. What is NOT verified, and known problems

Ordered by how much they matter.

1. **No real two-laptop test.** Everything ran on one Mac. No teammate has installed the tool against the Render server and used it from their own laptop. This is the most important missing test.
2. **Same-network access failed for the user.** The local server was started on `0.0.0.0` and answered on the Mac's network address (`10.10.95.166:8000`) from the Mac itself, but the user reported it "didn't open", presumably from another device. The likely cause is that the network blocks device-to-device connections (the address looks like a managed campus network). It was never diagnosed. Since Render now works, this only matters as a demo fallback: a phone hotspot should work, untested.
3. **Render free plan limits.** The server sleeps when idle and takes up to a minute to wake. The database file is wiped on every restart or redeploy, so the contract is lost. For real use this needs a persistent database; for a demo, open the dashboard ten minutes early.
4. **This Mac still points at the local server.** `coord/me.json` here has `"server": "http://127.0.0.1:8000"`. To use the deployed server, rerun `install.py` with `--server https://team-contract.onrender.com`.
5. **No password.** Anyone with the server address and a room code can read, add and reset. Each added decision in a non-empty room triggers a paid AI call. Mitigations so far are advice only: use a non-obvious room code, and set a credit limit on the OpenRouter key. A shared team token would be the proper fix.
6. **Each person must approve the MCP tool once.** In the desktop app the approval question did not appear. The workaround is a file `.claude/settings.local.json` containing `{"enabledMcpjsonServers": ["team-contract"]}`. You, the AI, are blocked from writing this file or any permission setting; the user must do it. `install.py` prints the instruction.
7. **Windows is untested.** The hook and MCP commands use `python3`, which often does not exist on Windows (`python` instead).
8. **Agent behaviour varies.** Each agent test ran once or a few times. Recording decisions depends on the agent cooperating. Run the demo path several times before trusting it.
9. **Two agents deciding at the same moment** was not tested. The server checks each decision, but there is no locking between two simultaneous conflicting writes.
10. **Decisions can be long.** The tool asks for one short sentence; agents sometimes write 200+ characters. The limit is 500.
11. **Conflicts never clear.** There is no "resolve" button; a conflict stays on the dashboard until the room is reset. There is also no way to change or delete a single decision, so "change the contract" has no real path yet.
12. **"Active" is approximate.** It means "sent a prompt in the last 10 minutes".
13. **The "Reset room" button was never clicked** in a test (its confirmation box was avoided in the automated browser). The request behind it works.
14. **No README.** The GitHub page has no setup instructions.
15. **Only Claude Code is supported.**

## 8. The biggest strategic risk

The whole pitch rests on the claim that agentmash does not catch **decision** conflicts in an empty or new repo. This was never tested. The user was asked twice to run the test and chose to proceed on the assumption.

The test (30-45 minutes): two people install agentmash's free tier on an empty repo, both prompt "build a backend for a todo app" with no stack named, and see whether the second agent learns what the first chose. Repeat with an API mismatch.

- If agentmash misses it: the wedge is real. Use the result in the pitch.
- If agentmash catches it: the story becomes a narrower niche (student and hackathon teams) or the idea needs rethinking.

Raise this with the user again before pitch work begins.

Other competitors found: session-sharing tools (claude-share, ccshare, Clay, Agor), which put many humans around one agent and are not the same idea; and shared-memory vendors (Hjarni, ContextStream, MemoryLake, Deeplake Hivemind), which are closer. ContextStream's own blog says shared memory does not resolve two conflicting saved decisions, which supports the wedge. All of this came from search summaries and vendor pages, not from using the products.

## 9. What was planned but not built

The original scope, in the order the user agreed:

| Feature | Status |
|---|---|
| Room, decision contract, contract injection, conflict warning, dashboard | Built |
| Installer / join command | Built |
| Deployment | Built (Render) |
| File overlap warning: a `PreToolUse` hook that reports each file edit and warns if a teammate touched that file recently | Not built |
| Auto-save to the person's own git branch when the agent finishes a turn (`Stop` hook) | Not built |
| Conflict radar: after `git fetch`, test-merge against teammates' branches with `git merge-tree` and warn | Not built |
| Team chat visible to agents | Dropped |

The user decided: **never auto-pull**; merging is done by the human. Variable-name conflicts are handled through the decision contract, not through code analysis.

## 10. Suggested next steps, in order

1. **Point this Mac at the Render server and confirm a real session works against it.** Rerun `install.py` with the Render address, then run one `claude -p` test and check the deployed dashboard.
2. **Get one teammate connected from their own laptop.** Clone the repo, run `install.py` on a test project with the Render address, approve the tool, send a prompt. This is the first true two-laptop test. Write down every snag.
3. **Write a short README** with the setup steps that test confirms. The user has not asked for one yet; offer it.
4. **Run the agentmash test** (section 8).
5. **Prepare the demo** (section 11): record the "without the tool" failure, save the prompts, rehearse, record a backup video.
6. **Fix what the demo exposes.** Likely candidates: a persistent database on Render, a shared token, a "resolve conflict" button, shorter decisions.
7. Only then consider the unbuilt features in section 9. They are parity with agentmash, not the wedge.

Feature freeze should happen before the last day. The scope has already grown several times.

## 11. Demo and pitch plan already agreed

**Format:** 5 minutes total. About 3 minutes of demo, 2 minutes of business.

**Rules:** the dashboard is the stage, because judges cannot read a terminal. Show the problem as a recording and the solution live. The presenter never stops talking during waits. Keep a backup video and switch to it if an agent is silent for 20 seconds.

| Time | Scene |
|---|---|
| 0:00-0:25 | The team's own story: AIs built incompatible backends at a hackathon. Use their real incident and true numbers. |
| 0:25-0:50 | Recording: two agents, same task, one builds Python, one builds Node.js. |
| 0:50-1:10 | Switch on the tool. Dashboard shows two people, empty contract. |
| 1:10-1:50 | Live: Ali's agent chooses a stack; decisions appear on the dashboard. |
| 1:50-2:35 | Live: Mei asks for Express; a red conflict card appears. |
| 2:35-3:00 | Mei says "follow the team". Close: "Other tools stop AIs colliding on files. We stop them disagreeing on decisions." |
| 3:00-5:00 | Competition and market (agentmash proves people pay), first customers (hackathon and student teams, then small startups), pricing (free for students, per-developer for teams), honest proof, the ask. |

**Likely judge questions and agreed answers:**

- "How are you different from agentmash?" They catch collisions on files; this catches contradictions between decisions, which git cannot see. (Only say this if section 8 is tested.)
- "Why not agree at the start, or share one file?" That covers the first ten minutes. Agents then make dozens of decisions nobody writes down.
- "What if Anthropic builds this?" Possible, for their own tool. Teams mix tools; this aims to be the neutral layer. Today it supports one tool, and that should be said plainly.

## 12. Practical notes for you

- **Permissions.** In the previous session, an automatic check blocked the AI from editing permission settings and from approving the MCP server. `git push` worked after the user added `Bash(git push:*)` to `~/.claude/settings.json`. If a push is blocked, give the user the command to run.
- **The local server stops when the session that started it ends.** Start it again with `sh start_server.sh`, or use the Render server.
- **Rooms.** `demo` is used everywhere in tests. On the local database it still holds the two-person test result (6 decisions, 2 conflicts). On Render it is empty.
- **Editing the checker prompt.** After any change to `SYSTEM_PROMPT` in `server/conflicts.py`, rerun the 15-case test.
- **Deploying.** Render redeploys automatically on every push to `main`, and that wipes the deployed database.
- **Hook facts checked against the Claude Code docs:** `UserPromptSubmit` needs no matcher; plain text printed by the hook is added to the agent's context; the limit is 10,000 characters; exit code 2 would block the prompt, so the hook always exits 0. In `.mcp.json`, the project folder must be written `${CLAUDE_PROJECT_DIR:-.}`.
