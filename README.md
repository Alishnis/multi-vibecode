# Team Contract

Team Contract shares project decisions between Claude Code sessions. Each prompt loads the decisions for your team's room. When Claude proposes a decision that contradicts an existing one, the server logs the conflict and keeps the existing decision in the contract. A person then settles the conflict on the dashboard, and every teammate's agent is told about the change on its next prompt.

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
d=$(mktemp -d) && curl -fsSL 'https://team-contract.onrender.com/client.zip' -o "$d/tc.zip" \
  && unzip -q "$d/tc.zip" -d "$d" \
  && python3 "$d/install.py" . --room 'SHARED_ROOM_CODE' --server 'https://team-contract.onrender.com'
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

Copy `.env.example` to `.env` and put your OpenRouter API key there to enable conflict checking. Start the server with `sh start_server.sh`, then use `http://127.0.0.1:8000` as the installer URL for both sessions. Keep the server terminal open during the test.

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
| “Get the latest code.” | `get_latest` | Applies approved, merged work when you are on the shared branch with no unsaved edits. Otherwise it says why nothing changed. |
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

Each running watcher checks GitHub about every 30 seconds. It prints a notice when it sees an approved open PR. After someone merges that PR into the room's base branch, the watcher prints another notice and fast-forwards the local base branch to the detected merge commit if the checkout is clean. Task branches, local edits and diverged history are left alone. Use a separate clean base-branch clone if you want it to update while you work elsewhere. The watcher never merges the PR on GitHub.

Before testing automatic updates, run `git status --short` in the receiving clone. The installer can add shared project files that show up as local changes. Commit those shared setup files to the repository first, then use a clone that already has that commit. Leave `coord/me.json` and `.claude/settings.local.json` local and ignored.

Use `python3 coord/git_sync.py watch --once` for a single check and sync, or add `--notify-only` to see notices without applying changes. Press Ctrl+C to stop continuous watching. The command is opt-in on every laptop and uses your existing GitHub CLI login. Approve from a different GitHub account than the PR author when testing with two clones. GitHub controls review requirements and whether a new commit dismisses approval. The watcher checks the latest 50 PRs per state and applies a fetched commit it can match to an approved, merged PR.

By default the watcher applies only pull requests that someone approved. Many small teams merge without a formal approval, and GitHub does not let you approve your own pull request. In that case the watcher tells you that newer commits were left alone. Run `python3 coord/git_sync.py watch --any-merge` to apply every merged pull request, approved or not. Commits pushed straight to the shared branch are never applied; use `git pull` for those. New files that Git does not track yet do not block a sync. Unsaved edits to tracked files do, and the notice names them.

## Get file overlap warnings

Rerun the installer and restart Claude Code in each teammate's project. Use the same room with distinct names. In a linked room, both checkouts must point to the room's GitHub repository.

When Claude Code successfully edits a file using Edit, Write, MultiEdit, or NotebookEdit, Team Contract reports the project-relative path, teammate name, branch if available, and time. When a different teammate's agent is about to edit the same path within 30 minutes, the hook delivers a **FILE OVERLAP** notice to the terminal user and context to Claude before the edit. By default it also asks you to allow or deny the edit. After an allowed edit succeeds and is reported, further edits to that file go through until a teammate changes it again. The dashboard shows the recent reports and marks paths reported by multiple teammates.

Example terminal notice (Claude Code controls its visual styling):

```text
[Team Contract: FILE OVERLAP]
File: src/todos.py
  Ali on ali/todos edited this file (just now).
Their changes may not be in your local copy yet.
Next: review their changes before editing the same code.
Choose whether to continue in Claude Code's approval prompt.
```

This reports a recent edit, not proof that someone is still typing or that the code will conflict. The same branch name on two computers does not mean their files are identical. The hook does not fetch or merge code.

To try it, have Claude Code in the first checkout write a test file such as `src/todos.py`. Then ask Claude Code in the second checkout to edit the same relative path, and watch for the question before the second change. Shell commands and edits made outside these Claude Code tools are outside this check. Only file metadata is sent to the server.

To show the terminal warning and give Claude context without requesting approval, add `"overlap": "note"` to `coord/me.json`. Normal Claude Code permissions still apply. The installer preserves this preference on upgrades. In a session with nobody at the keyboard (`claude -p`), a question cannot be answered, so the default edit is refused; use the note setting there.

If the check fails, a **CHECK UNAVAILABLE** notice says the edit was not checked. The hook does not block the edit on a connection failure. A quiet successful check means no matching recent report was found; it cannot guarantee no teammate is editing.

Warnings arrive when Claude attempts a supported edit. They are not background notifications in an idle terminal. This stage supports Claude Code; shell edits, external editors and other agents need separate integrations.

Local automated check (uses two temporary installed clients and a local server, without AI calls):

```sh
.venv/bin/python -B -m unittest server.test_terminal_warnings
```
