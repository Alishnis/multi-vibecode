# Team Contract

Team Contract shares project decisions between Claude Code sessions. Each prompt loads the decisions for your team's room. When Claude proposes a decision that contradicts an existing one, the server logs the conflict and keeps the existing decision in the contract. A person then settles the conflict on the dashboard, and every teammate's agent is told about the change on its next prompt.

## Guided setup — one command

Open [Team Contract](https://team-contract.onrender.com/), choose your room and name, and copy the setup command. Run it inside your project folder on Mac or Linux:

```sh
curl -fsSL https://team-contract.onrender.com/install.sh | bash -s -- --server https://team-contract.onrender.com --room YOUR_ROOM
```

Python 3 and curl are prerequisites. Setup installs the Team Contract files and merges the agent configuration with your existing settings. It offers to install Claude Code from Anthropic, install GitHub CLI through an existing Homebrew installation, sign into GitHub, and link the current GitHub repository to your room. Linking needs a team key, set on the dashboard. If Homebrew is unavailable, setup points to GitHub CLI’s installer. It does not create or replace your project’s Git repository.

Choose whether automatic sync should run while your workspace is open. Setup saves that preference, checks the installation, and offers to open the dashboard and Claude. Claude login, project trust, and agent permissions still require your interaction.

For every later session, run:

```sh
python3 coord/team.py --action work
```

This opens Claude and the dashboard, and runs the Git watcher if you enabled it. The watcher stops when Claude exits; its messages are saved in `coord/.state/sync.log`. Only clean shared branches receive merged PR updates. To change preferences, run `python3 coord/team.py --action setup`. For the numbered action menu, run `python3 coord/team.py`.

The website copies the command; it does not execute commands on your computer. Re-run setup to upgrade an existing project, then restart Claude. Your name, room, privacy preferences, and unrelated agent settings are preserved.

## Try it on one Mac

You need Python 3 and a working Claude Code login. These steps use the hosted server on Render. Open [server health](https://team-contract.onrender.com/health) and wait for `{"ok":true}` before starting.

```sh
git clone https://github.com/Alishnis/multi-vibecode.git
cd multi-vibecode

test_dir=$(mktemp -d)
room="solo-$(date +%s)-$(basename "$test_dir")"
server=https://team-contract.onrender.com
mkdir "$test_dir/ali" "$test_dir/teammate"

python3 install.py "$test_dir/ali" --name Ali --room "$room" --server "$server"
python3 install.py "$test_dir/teammate" --name Teammate --room "$room" --server "$server"
echo "$server/?room=$room"
```

If you already cloned this repository, start inside your existing checkout. Keep using the same terminal so it remembers `test_dir`. Open the dashboard URL printed above.

1. Run `(cd "$test_dir/ali" && claude --permission-mode default)`. Trust the test folder and approve the `team-contract` server if prompted. Send **“Record one team-contract decision: The todo backend uses FastAPI on port 18763.”** Review and approve the tool call. Confirm the decision appears on the dashboard, then exit Claude.
2. Run `(cd "$test_dir/teammate" && claude --permission-mode default)`. Approve the server if prompted. Ask **“What framework and port did the team choose for the todo backend?”** Claude should recall **FastAPI on port 18763**.
3. In the teammate session, ask **“Propose switching the todo backend to Express through the team-contract tool. Do not write any code.”** Review and approve the tool call. The dashboard should show both people, one saved FastAPI decision, and a conflict for Express.

## Join from another laptop

The quickest way needs no checkout of this repository. Open the room dashboard, select **Connect your project** (or **Setup guide**), and copy the **Join this room** command. Run it in Terminal inside your project folder on a Mac or Linux computer. It downloads the installer and client scripts from the server (`/client.zip`), adds them to the folder, and asks for your name. The files always match the server's version.

```sh
curl -fsSL https://team-contract.onrender.com/install.sh | bash -s -- --server https://team-contract.onrender.com --room SHARED_ROOM_CODE
```

You can also run the installer from a checkout of this repository, pointing it at your project folder:

```sh
python3 install.py /path/to/project --name YOUR_NAME --room SHARED_ROOM_CODE \
  --server https://team-contract.onrender.com
```

Each teammate uses their own name and the same room code and server URL. Start a fresh Claude Code session in the installed project.

The hosted flow has been tested with two independent sessions on one Mac. Setup and connectivity from a second laptop and Windows support are still untested.

## Troubleshooting

- **Python reports `CERTIFICATE_VERIFY_FAILED` on macOS.** The client scripts now handle this themselves: when Python has no list of trusted certificates, they use the system's file (`/etc/ssl/cert.pem`). Certificate checking stays on. If you installed before this fix, update your checkout and rerun `install.py`. For a Python.org installation, you can also run its bundled [Install Certificates.command](https://docs.python.org/3/using/mac.html).
- **Claude says the team contract could not be loaded.** The hook could not reach the server within 3 seconds. Open the server address in a browser to wake it, wait for the dashboard, and send the prompt again. The agent is told about the problem so that it does not guess teammates' decisions.
- **Claude Code Auto mode denies the recording tool.** Launch the test session with `claude --permission-mode default` and review the tool call in Manual mode. If the MCP server itself is missing, follow the installer's project approval instructions. [Claude Code permission modes](https://code.claude.com/docs/en/permission-modes)
- **The dashboard is empty after a pause.** Check the room code and confirm the first decision was saved. Render's free service can take about a minute to wake, and the SQLite database can be cleared by spin-down, restart, or deploy. [Render free service limits](https://render.com/docs/free)

## Run your own server

Copy `.env.example` to `.env` and put your OpenRouter API key there to enable conflict checking. Optionally add a free Gemini key (`GEMINI_API_KEY`): it runs the small jobs, such as one-sentence edit summaries, so they cost nothing. With only a Gemini key, the conflict checks use Gemini too. Start the server with `sh start_server.sh`, then use `http://127.0.0.1:8000` as the installer URL for both sessions. Keep the server terminal open during the test.

The hosted prototype has no accounts. Anyone who knows the room code can read the room and propose decisions. Changing the contract by hand (answering, settling, retiring, resetting) needs the room's team key, described below. Use a fresh room with sample decisions when testing, and pick a room code that is hard to guess.

The database is one SQLite file. Set `CONTRACT_DB_PATH` to keep it somewhere that survives restarts.

## Check a plan and request a decision

Update your checkout, rerun the installer for each test project, and restart Claude Code to load the new tools. The server needs a working OpenRouter key for plan reviews.

1. Ask Claude to check a plan that depends on a shared choice, such as the response shape for `GET /todos`. `check_plan` reports contradictions and missing agreements without changing the contract.
2. For a missing agreement, ask Claude to use `request_decision` with the topic from the review. Requests with the same topic in a room share one record. Ask from a second session to see it reuse the existing request.
3. On the dashboard, select **Answer request**, choose a suggested decision or write one, and enter your name and the team key. The answer joins the contract once. A fresh prompt in either project reads it through the existing hook.

## Set the team key

The team key is a password for one room. It is needed for everything a person decides on the dashboard: answering a request, settling a conflict, retiring a decision, resetting the room, and linking a GitHub repository. AI agents never receive it, so an agent cannot approve its own request.

1. Open the dashboard for your room and select **Set team key** at the bottom of the page.
2. Enter your name and a key of 8 characters or more. Share the key with your teammates outside the project files.

The key can be set once per room. The server stores only a salted hash of it. If the team loses the key, start a new room. The browser remembers the key until the tab is closed.

A server owner can also set `CONTRACT_APPROVAL_TOKEN` in `.env` or in the hosting settings. That one token is accepted in every room, next to each room's own key.

## Change a decision

Decisions are not permanent. Three actions on the dashboard change the contract, and each needs the team key.

- **Settle a conflict.** Each open conflict shows what the AI wanted next to what the team decided. **Keep this** closes the conflict and changes nothing. **Switch to this** retires the old decision and saves the new one in one step. Before switching, the server checks the new decision against the rest of the contract. If it contradicts another decision, nothing changes and the dashboard says which one.
- **Retire a decision.** Select **Retire** next to a decision to take it out of the contract. If that decision answered a request, the request opens again.
- **Look at the history.** Retired decisions stay under **Retired decisions**, with who retired them and what replaced them.

On its next prompt, each teammate's agent receives a short list of what was added or retired since it last read the contract, and is asked to say what earlier code has to change.

## Share code through GitHub

Run the updated installer for each teammate's clone. The room dashboard has copyable commands under **Connect your project**, **Share changes**, and **Sync updates**. Run them in Terminal on your computer. The Git commands need Git and the GitHub CLI (`gh auth login`). Give each teammate access on GitHub.

### Ask Claude Code instead of typing commands

Once the room is linked to GitHub, you can stay inside Claude Code. The `team-contract` tool server has four Git tools, and Claude uses them when you ask in plain words. Claude Code asks you to approve each tool call.

| You say | Claude uses | What happens |
| --- | --- | --- |
| “Start a task for the delete endpoint.” | `start_task` | Creates a task branch from the latest shared code. Work you already began on the shared branch comes along. |
| “Share my work.” | `share_work` | Claude commits the files for the task, pushes the branch, and opens or updates one pull request. You get the link. |
| “Get the latest code.” | `get_latest` | Applies merged work (approval review optional) when you are on the shared branch with no unsaved edits. Otherwise it says why nothing changed. |
| “Where does my branch stand?” | `branch_status` | Reports commits ahead and behind and the review status, and updates the dashboard. |

These tools run the same `coord/git_sync.py` commands described below, so the terminal and Claude behave the same way. Linking a room, reviewing, and merging stay with people. After updating, rerun the installer in each project and restart Claude Code so it loads the new tools.

1. **Link the room once.** From an installed project with an existing GitHub `origin`, run `python3 coord/git_sync.py link` and enter the room's team key. The command reads GitHub's default branch. For a new project with an initial local commit and no `origin`, run `python3 coord/git_sync.py create OWNER/REPO` to create a private GitHub repo, push the current branch's committed history, and link the room. Review that history before running the command. Teammates clone the repo and use the same room code and server URL.
2. **Start a task.** Run `python3 coord/git_sync.py start ali/todo-api` to create a branch from the latest shared code. Make your edits and commit the files you want to share using your editor’s Source Control panel or Git. If you already began on the shared branch, run `start` anyway: unsaved edits and commits you made there move to the new task branch, and your local shared branch goes back to match GitHub.
3. **Share it for review.** Run `python3 coord/git_sync.py publish --ready`. This pushes your commits, opens or updates one pull request, and prints the review link. Add `--title "Add todo API"` to name a new pull request. Use `publish` on its own to open a new pull request as a draft.
4. **Review and merge.** From the dashboard, a teammate can select **View changed files** to review on GitHub. Someone with permission merges it on GitHub after approval. The dashboard shows the branch and review status last reported by `publish` or `python3 coord/git_sync.py status`.

The dashboard gets repository, branch, and review metadata. GitHub handles the source code, credentials, and reviews. Use `publish` to open or update the pull request while pushing your commits.

### Contract check before sharing

Before `publish` pushes anything (and so before `share_work` does), it sends the changed lines of your commits to the room's server. The server asks the AI checker whether the code breaks a team decision: another framework or database than the one chosen, a different response shape for a decided endpoint, a different field name, a different port, or the opposite of a convention.

- **The code fits.** The push goes ahead and the dashboard shows **Fits the contract** next to the branch.
- **The code breaks a decision.** Nothing is pushed. The terminal, or Claude, names the file, what the code does, and the decision. Fix the code, or settle the decision with your team on the dashboard.
- **You want to share it as it is.** Run `python3 coord/git_sync.py publish --anyway`, or tell Claude to share anyway. The dashboard then shows **Breaks a team decision** next to the branch, with the reason.
- **The check cannot run** (no API key on the server, an empty contract, the server unreachable). The push goes ahead and you are told the code was not checked.

What leaves your computer: up to 12,000 characters of the change, without Team Contract's own setup files. The server passes it to the checker and stores only the findings. To send nothing, add `"check_code": false` to `coord/me.json`, or run `publish --no-check`.

The checker is tested with `.venv/bin/python -m server.test_share_live`, which needs the OpenRouter key.


### Get approval notices and sync after merge

In each linked clone, rerun the installer and start this in a separate terminal:

```sh
python3 coord/git_sync.py watch
```

Each running watcher checks GitHub about every 30 seconds. It prints a notice when it sees an approved open PR. After someone merges a PR into the room's base branch, the watcher prints another notice and fast-forwards the local base branch to the detected merge commit if the checkout is clean. Task branches, local edits and diverged history are left alone. Use a separate clean base-branch clone if you want it to update while you work elsewhere. The watcher never merges the PR on GitHub.

Before testing automatic updates, run `git status --short` in the receiving clone. The installer can add shared project files that show up as local changes. Commit those shared setup files to the repository first, then use a clone that already has that commit. Leave `coord/me.json` and `.claude/settings.local.json` local and ignored.

Use `python3 coord/git_sync.py watch --once` for a single check and sync, or add `--notify-only` to see notices without applying changes. Press Ctrl+C to stop continuous watching. The command is opt-in on every laptop and uses your existing GitHub CLI login. GitHub controls review requirements and whether a new commit dismisses approval. The watcher checks the latest 50 PRs per state and applies a fetched commit it can match to a merged PR.

By default the watcher and `get_latest` apply merged pull requests whether or not they received an approval review. No extra flag or `include_unapproved` argument is needed. Use `watch --approved-only` or `get_latest` with `include_unapproved: false` to request the older filter. `--any-merge` remains accepted. Restart existing watchers and Claude sessions after upgrading. GitHub branch rules still control who can merge; this setting does not approve or merge PRs. Updates still require a clean shared branch and fast-forward history. Direct pushes are not selected as update targets, but commits preceding an eligible merge arrive with that merge.

## Claim work before editing

A claim says what a teammate is about to change, before any edit. It is the one moment another agent can still pick different work.

- **How it is made.** Claude calls the `claim_work` tool before the first edit of a task, with the task in one sentence and the files or folders it expects to change. You can also say "claim `server/` for the login work". A folder covers everything inside it.
- **Who sees it.** Every teammate's agent gets live claims in its context on each prompt. The dashboard lists them under **Claimed work**. A teammate's first edit of a claimed file shows **CLAIMED BY A TEAMMATE** and blocks the edit until the overlap is resolved or you deliberately select advisory mode.
- **Overlap.** If two claims cover the same files, `claim_work` replies with **NOT CLAIMED** and names the owner. The second request is not registered, so it cannot block the first owner.
- **How it ends.** A claim runs out after 120 minutes (5 to 480 can be asked for). Say "release my claim" to end it early (`release_claim`). `list_claims` shows what is claimed.
- **Until the branch merges.** For longer work, say "claim it until merged". In a room linked to GitHub, on a task branch, the claim then stays until that branch's pull request is merged, at most 7 days. One person holds one such claim per branch; claiming again adds files to it. The room hears about a merge when any teammate runs `get_latest` or `python3 coord/git_sync.py watch`.

The first active reservation has priority. An overlapping request is refused atomically: no new claim is saved, including the non-overlapping files in that request. Existing claims stay unchanged. Ask again with different paths or wait until the owner releases or the claim expires. Supported agent edit hooks enforce reservations; ordinary shell commands and external editors do not. On server startup, old duplicate reservations are repaired in creation order, preserving unrelated paths where possible.

## Team chat

A short message that every teammate's agent shows to its user once, before their next prompt. Use it for things like "the demo is at 15:00, nobody edits `investor-demo.md` after 14:30".

- **Send.** Type it in the **Team chat** panel on the dashboard (start with `@name` to message one person), or ask Claude: "tell the team the demo is at 3pm". Claude uses the `send_message` tool only when you ask.
- **Receive.** On each teammate's next prompt, the agent is given the new messages (at most five, newest last) and tells its user what they say. Each message is delivered once per person, counted by message number, so none is missed or repeated. A first prompt hears about the last six hours.
- **Safe by design.** A message reaches agents as quoted data, one line each, with a note that it is not an instruction: the agent relays it and does not act on it unless the user agrees. Text is cut to one clean line of at most 500 characters, a person can send 12 messages a minute, and each room keeps its last 200.
- **No accounts.** Anyone who knows the room name can post under any name, like decisions. Do not put secrets in chat.

The prompt text stays under Claude Code's 10,000-character limit: the contract gets about 6,000 characters, "changed since your last prompt" 1,200, and chat uses what is left.

## Ask a teammate's agent

Send a prompt to a teammate's agent. **Nothing runs until that teammate approves.** The agent's answer comes back to you.

1. **Ask.** In the **Ask a teammate's agent** panel on the dashboard, pick the teammate, write the request and choose *Read only* or *Can edit files*. Or tell Claude: "ask Mei's agent why the login test is flaky, read only". The request stays open for 60 minutes by default (5 to 1,440).
2. **They are told.** On the teammate's next prompt, their agent is given the request as quoted data, marked **not approved**, and told to show it to its user, say who asks and what, and ask. The agent does nothing with it until the user says yes.
3. **They approve, in one of two ways.**
   - *In their chat:* they say yes to their agent, which runs the request and reports with `answer_ask`. The dashboard shows "Approved (chat)", and the agent's report is taken at its word.
   - *On the dashboard:* they press **Approve**, enter their own name and the team key. Only this kind of approval makes their agent run the request on its next prompt without asking again; the agent is told the user already approved it. The team key is never shown to agents, so an agent cannot give it.
4. **The answer returns.** When the teammate's agent finishes, it sends a short result. Your agent shows it to you once on your next prompt, and the dashboard lists it.

Good to know:

- **Limits are advice, not locks.** *Read only* tells the teammate's agent not to edit files or run commands that change anything. Claude Code's own permission prompts on their computer still apply, but this tool cannot enforce the limit.
- **Names ignore case.** "Mei" and "mei" are the same teammate; the request is stored under the name their own computer reports.
- **Names are not verified.** The room has no accounts, so anyone who knows the room name can send a request as anyone. That is why a request is never run without the target's yes, and why the agent is told to treat the sender's name and text as data.
- **Fences.** The teammate must have connected to the room. Nobody may have more than five open requests, and nobody may hold more than five waiting. A sender can cancel a waiting request. An unanswered request expires and the sender is told once.
- **Not a remote control.** It works through the teammate's next prompt, so it arrives when they next use their agent, not instantly.

## Get file overlap warnings

Rerun the installer and restart Claude Code in each teammate's project. Use the same room with distinct names. In a linked room, both checkouts must point to the room's GitHub repository.

### What is reported after each edit

When Claude Code successfully edits a file using Edit, Write, MultiEdit, or NotebookEdit, a hook reports it to the room. Nobody has to do anything. The report holds:

| Field | Example | Notes |
| --- | --- | --- |
| File path | `src/todos.py` | Relative to the project folder. |
| Teammate and branch | Ali, `ali/todo-delete` | |
| Session | `f7cfb68784229f55` | An opaque id for the Claude Code session. Not the real session id. |
| Change summary | `+5/-1 lines, touching count_todos` | Line counts and the names the edit introduced. Worked out on your computer. |
| Changed lines | the removed and added lines, at most 4,000 characters | Only for the AI summary below. The server uses them once and does not store them. |
| Checkout id | `9a41…` | Says whether two edits were made in the same folder. Made with a random key that stays on your computer, so it names neither the computer nor the folder. |
| File fingerprint | `c03e…` | A hash of the file after the edit. Lets a teammate's computer tell whether it has exactly that version. |

**AI summary.** If the server has a Gemini key, its free small model turns the changed lines into one sentence, for example `Adds delete_todo to remove a todo by its id. (+10/-2 lines)`. That replaces the counts-and-names summary a few seconds after the edit. Paid checker tokens are never spent on this: without a Gemini key the local summary stays. To keep your changed lines on your computer, add `"ai_summary": false` to `coord/me.json`. Files that usually hold secrets (`.env`, key files) are never sent. Note that a free Gemini tier may use what it receives to improve Google's models.

The dashboard shows the summary next to each recent edit. When this session reads a file, the time is noted on your computer only (`coord/.state/`, kept out of Git).

### Four kinds of warning

Before an edit, the hook asks the room whether a teammate changed the same file in the last 30 minutes. If so, the warning appears in the terminal and is given to Claude. It names one of four kinds:

| Kind | When | What to do |
| --- | --- | --- |
| **ACTIVE COLLISION** | A teammate changed the file in the last 5 minutes and their agent is still working. | Agree who changes which part before editing. |
| **OUTDATED READ** | Their change is already in your checkout (your file, or your Git history), but this session read the file before it. | Read the file again, then edit. |
| **WORK IN ANOTHER CHECKOUT** | Their change is in their own copy, not yours. Reading your file again will not show it. | Get their changes first, or agree who edits what. A merge conflict is forming. |
| **RECENT EDIT** | Their change was in your copy when this session last read the file. | Low urgency. Check that your edit does not undo theirs. |

The first three block the edit with `permissionDecision: deny`; claimed files also block. Claude receives the rejection before the tool writes. A recent edit is a note only. If your file exactly matches the teammate's reported version and this session has read it since, the edit warning clears (a separate live claim may still block). Resolve claims with the teammate and have their owner release them when finished. For changes in another checkout, review and integrate them first. Do not ask the agent to bypass the hook through a shell command.

**Git-aware.** Each edit report also carries Git's own fingerprint of the file. Before an edit, the hook looks at the file's last 40 commits in your checkout. If a teammate's exact version is in that history, you have already pulled it, so it is never reported as work in another checkout, even if you have edited the file since. It then counts like a change in your own copy: quiet if this session has read the file since, OUTDATED READ if not. A version the teammate has not committed and pushed cannot be in your history, so it still shows as another checkout.

Example terminal notice (Claude Code controls its visual styling):

```text
[Team Contract: ACTIVE COLLISION]
File: app.py
  Ali on ali/todo-delete edited this file (just now): +5/-1 lines, touching count_todos.
They are working on this file right now, and their latest version is not in your copy.
Next: agree with them who changes which part before you edit, or one of you will have to merge by hand.
Edit blocked before writing. Resolve the overlap before trying again.
```

Ranking a warning by "is their change in my copy" and "are they still there" follows the published AgentMash protocol. The code is our own. Unlike AgentMash, a live edit on another laptop counts as an active collision here.

If you intentionally want advisory mode after reviewing the risk, set `"overlap": "note"` yourself in `coord/me.json`. Normal Claude permissions still apply. The agent must not change this setting to bypass a block. The installer preserves it. Default blocking works in interactive and headless sessions.

Repeated notices for the same activity, file, room and session are quiet for ten minutes. A repeat of a blocked edit still returns a short denial; suppression never grants permission. New edits, teammates or changed claims produce a fresh notice. Background summary updates do not. Connection failures show an unchecked notice at most once a minute per session and server/room. Cache failures show full warnings. The bounded cache stores only hashes and timestamps in the ignored `coord/.state/` folder.

If the check fails, a **CHECK UNAVAILABLE** notice says the edit was not checked. The hook does not block the edit on a connection failure. A quiet successful check means no matching recent report was found; it cannot guarantee no teammate is editing.

Warnings arrive when Claude attempts a supported edit. They are not background notifications in an idle terminal. This stage supports Claude Code; shell edits, external editors and other agents need separate integrations.

Local automated check (uses two temporary installed clients and a local server, without AI calls):

```sh
.venv/bin/python -B -m unittest server.test_terminal_warnings
```


## One command for everyday actions

After joining a project, run `python3 coord/team.py`. Choose a number to start a task, share committed work, get latest code, keep syncing, check branch status, see reserved files, release your own reservations, check setup, open the dashboard, or open Claude. Press Ctrl+C while watching to return to the menu. Sharing still requires committed changes. No command auto-commits all your files.

For a setup check without opening the menu, run `python3 coord/team.py --action doctor`. It checks client files, hook registration, the agent connection, installed tools, GitHub login and server reachability. It does not prove that an agent has approved the hooks; test that in a fresh Claude session.

The dashboard's **Action menu** button copies the launcher command. Browser buttons do not execute arbitrary terminal commands. The existing one-line Join command installs the menu too.
