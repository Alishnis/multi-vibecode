# Try Team Contract with two terminals

A real-world rehearsal on one Mac. Two folders play two teammates, **Ali** and **Mei**, each with their own Claude Code in their own terminal. Every step says what to type and **what is supposed to happen**. Takes about 30 minutes.

- **Terminal A** = Ali, in `~/tc-trial/ali`
- **Terminal B** = Mei, in `~/tc-trial/mei`
- **Browser** = the team dashboard

Tips before you start:

- Inside Claude Code, a line that starts with `!` runs as a shell command, for example `!git status`. You never have to leave Claude.
- Claude Code asks before it uses a tool. When it asks about a `team-contract` tool, choose **Yes** (or "Yes, and don't ask again" to go faster).
- The hosted server is free: it sleeps after about 15 idle minutes and forgets rooms when it restarts. If you take a long break, start again from step 0.
- Room name used below: `tc-trial-7319`. Use exactly this in every command.

---

## 0. Prepare (Terminal A)

Wake the server: open https://team-contract.onrender.com/app?room=tc-trial-7319 in your browser. Wait until the page loads (up to a minute).

**Expect:** the workspace page for `tc-trial-7319` with a **Get your team set up** list at "0 of 5 done".

Create the two "computers". Ali's folder is the shared project; Mei's folder is a clone of it, as if she cloned from GitHub:

```bash
mkdir -p ~/tc-trial && cd ~/tc-trial
```

```bash
mkdir ali && cd ali && git init -q && echo "# Todo app" > README.md && git add README.md && git commit -qm "start" && cd ..
```

```bash
git clone -q ali mei
```

**Expect:** `~/tc-trial/ali` and `~/tc-trial/mei`, both with `README.md`.

---

## 1. Join the room (both terminals)

**Terminal A:**

```bash
cd ~/tc-trial/ali
```

```bash
curl -fsSL https://team-contract.onrender.com/install.sh | bash -s -- --server https://team-contract.onrender.com --room tc-trial-7319 --name Ali
```

Answer the questions like this:

| Question | Answer |
| --- | --- |
| Connect GitHub for sharing and syncing? | **Enter** (no) |
| Keep merged code up to date while your workspace is open? | **Enter** (no) |
| Open your workspace now? | **n** |

**Expect:** "server reached: room tc-trial-7319 has 0 decision(s)", a list of OK/CHECK lines (a CHECK for `gh` or GitHub is fine), then "Ready. Next time, in this folder, run: ./tc work".

**Terminal B:** the same, as Mei:

```bash
cd ~/tc-trial/mei
```

```bash
curl -fsSL https://team-contract.onrender.com/install.sh | bash -s -- --server https://team-contract.onrender.com --room tc-trial-7319 --name Mei
```

Same answers.

Now start Claude Code in **both** terminals:

```bash
claude
```

**Expect:** Claude Code asks whether you trust the folder (yes) and whether to use the `team-contract` server from `.mcp.json` (yes). If it asks to approve project hooks, approve them.

**Dashboard:** "Connect your project" is ticked.

---

## 2. Ali builds something (Terminal A)

Type to Claude:

> Build a small todo module in src/todos.py in plain Python: a list of todos, list_todos(), add_todo(title) and delete_todo(todo_id). Each todo has id, title and done.

**Expect in Terminal A:**

1. Claude calls **team-contract claim_work** for `src/todos.py` (approve it). Reply: "Claimed … No teammate has claimed these files. Go ahead."
2. It may call **record_decision**, for example "Todo items have id, title and done fields." Reply: "Recorded in the team contract".
3. It writes `src/todos.py`.

**Expect on the dashboard (within a few seconds):**

- **Claimed work:** Ali, "…todo module…", `src/todos.py`, about 119 min left.
- **Recent file edits:** `src/todos.py` by Ali, with a one-sentence summary such as "Adds a todo module with list, add and delete functions. (wrote 20 lines)".
- **Team decisions:** the data decision, if Claude recorded one.

---

## 3. Mei collides with Ali (Terminal B)

Mei has not pulled Ali's work, so she does not have `src/todos.py`. Type:

> Create src/todos.py with a todos list and a get_todos() function.

**Expect in Terminal B:**

- Claude calls **claim_work** and gets **NOT CLAIMED**: Ali already reserved `src/todos.py` for his task. Claude tells you that and suggests other work, without writing the file.

Now push it. Type:

> I understand, try to write it anyway.

**Expect:** the write is **blocked before it happens**. The terminal shows a block like:

```text
[Team Contract: ACTIVE COLLISION]
File: src/todos.py
  Ali claimed this for "…"
  Ali edited this file (1 min ago): Adds a todo module …
…
Edit blocked before writing. Resolve the overlap before trying again.
```

(If Ali's edit is more than 5 minutes old the title is **WORK IN ANOTHER CHECKOUT**. Either way, the file is not written.) Claude explains the overlap instead of retrying.

Check: `!ls src` in Terminal B shows no `todos.py`.

---

## 4. Team chat (A, then B)

**Terminal A:**

> Tell the team the demo is at 3pm and nobody should edit src/todos.py after 2:30.

**Expect:** Claude calls **send_message**: "Sent to the whole team…". The dashboard's **Team chat** shows the message.

**Terminal B:**

> What's new from the team?

**Expect:** Claude relays Ali's message ("The demo is at 3pm…"). It may call **team_status** and give a short summary ending with a next step. Ask the same question again: the message is **not** repeated as new.

---

## 5. Ask a teammate's agent (A, B, B, A)

**Terminal A:**

> Ask Mei's agent to look at her folder and tell me which files are in it. Read only.

**Expect:** Claude calls **ask_teammate**: "Request #N sent to Mei (read only…). Nothing runs until Mei approves." The dashboard's **Ask a teammate's agent** shows it as **Waiting for approval**.

**Terminal B:**

> Anything for me?

**Expect:** Claude shows "request #N from Ali (read only): …" and **asks you whether to run it. It does not run it yet.**

**Terminal B:**

> Yes, run it.

**Expect:** Claude lists the files (it only reads), then calls **answer_ask** with `done` and a short result. The dashboard shows **Done** with the answer.

**Terminal A:**

> Any news?

**Expect:** Claude reports "Request #N to Mei: done" with her agent's answer. Ask again: it is not repeated.

*Optional, the other approval path:* repeat the request from Terminal A, and this time on the dashboard press **Approve** (you need the team key from step 7 first; type the name `Mei`). Then in Terminal B type anything, for example "ok": Claude runs it **without asking again**, because a person approved it on the dashboard.

---

## 6. Hand over the file, then edit it safely (A, then B)

**Terminal A:** release the claim and commit Ali's work:

> I'm done with the todo module. Release my claim.

**Expect:** **release_claim**: "Released 1 claim(s)". The claim disappears from the dashboard.

```text
!git add src && git commit -m "todo module"
```

**Terminal B:** get Ali's commit, the way a teammate would after a merge:

```text
!git pull
```

**Expect:** `src/todos.py` arrives in Mei's folder.

> Add a mark_done(todo_id) function to src/todos.py.

**Expect:** Claude claims the file (it is free now), reads it and edits it **with no overlap warning**. Ali's version is in Mei's Git history, so Team Contract knows she already has his change. The dashboard shows Mei's claim and her edit.

*Contrast:* in step 3, without the pull, the same file was blocked.

---

## 7. A decision conflict, settled by a person (A, B, browser)

**Browser:** in **Get your team set up**, press **Set team key**. Enter your name and a key of 8 or more characters (for example `trial-key-123`). Remember it.

**Terminal A:**

> We will use FastAPI for the backend. Record that as a team decision.

**Expect:** **record_decision**: "Recorded in the team contract: [stack] Backend is FastAPI…". It appears under **Team decisions**.

**Terminal B:**

> Set up the backend with Express on port 3000.

**Expect:** Claude calls **record_decision** for Express and gets **CONFLICT with the team contract**: FastAPI was already chosen. Claude **stops and asks you** instead of writing Express code. The dashboard shows a red **Decision conflicts** card: "Mei's AI wanted … Express", "Team already decided … FastAPI".

**Browser:** on the conflict card press **Keep this** under FastAPI, then enter your name and the team key.

**Expect:** the card disappears. On Mei's next prompt, Claude follows FastAPI.

---

## 8. One-line status in each terminal

**Terminal A:**

```text
!./tc today
```

**Expect** plain sections, for example:

```text
Room tc-trial-7319, as Ali.
Teammates: Mei (active now).
Needs you: nothing right now.
Your work:
  • Your request #1 to Mei: done. Answer: "…the files in her folder…".
Teammates are working on:
  • Mei: "…mark_done…" (src/todos.py). Leave these files to them.
  • Mei edited src/todos.py: Adds mark_done to mark a todo as finished. (+6/-0 lines).
Latest messages:
  • Ali: "The demo is at 3pm…"
Team decisions in force: 2.
Next step: start a task: open Claude and say what you want to build. It claims the files first.
Dashboard: https://team-contract.onrender.com/app?room=tc-trial-7319
```

**Terminal B:** `!./tc today` shows the same room from Mei's side. Her own claim appears under **Your work**.

Also try `!./tc help`, which lists every word, and `!./tc todya`, which answers "I don't know 'todya'" and shows the list.

**Dashboard:** the setup list shows 4 of 5 done. Only "Connect GitHub (optional)" is left.

---

## 9. Clean up

**Browser:** at the bottom of the dashboard, **Reset room** (enter your name and the team key).

Exit Claude in both terminals (`/exit`), then:

```bash
rm -rf ~/tc-trial
```

---

## If something does not happen

| What you see | Why, and what to do |
| --- | --- |
| No `team-contract` tools are called at all | Claude Code was started before the install finished, or the server was not approved. Exit Claude, run `claude` again, and approve `team-contract`. |
| `[Team Contract: CHECK UNAVAILABLE]` | The server is asleep or unreachable. Open the dashboard to wake it, then retry. |
| Step 3 writes the file anyway | Check that both folders joined the **same** room (`!./tc today` prints the room) and that you approved the hooks. |
| Step 7 shows no conflict | The dashboard footer says whether the conflict check is on. If it is OFF, the server has no AI key. |
| The dashboard looks unstyled | Reload once with Cmd+Shift+R. |
| Everything vanished from the dashboard | The free server restarted and lost the room. Start again from step 0. |
