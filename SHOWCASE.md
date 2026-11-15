# CoopDev showcase: two agents, GitHub, every main feature

This is the full path from nothing to a working demo. Two folders on one Mac play two teammates, **Ali** and **Mei**. Each has their own terminal and their own Claude Code. At the end you will have shown: shared decisions, claims, blocked edits, chat, asking a teammate's agent, and Git sharing through a real pull request.

Time: about 40 minutes the first time, 15 when you rehearse it.

- **Terminal A** = Ali, `~/coopdev-demo/ali`
- **Terminal B** = Mei, `~/coopdev-demo/mei`
- **Browser** = the team dashboard
- Demo app: a small translator (`translate.py`). Use any app you like.

## 0. Before you start

You need on your Mac:

| Tool | Check | If missing |
| --- | --- | --- |
| Python 3 | `python3 --version` | python.org |
| Git | `git --version` | `xcode-select --install` |
| curl | `curl --version` | comes with macOS |
| GitHub CLI | `gh --version` | `brew install gh` |
| Claude Code, logged in | `claude --version` | https://code.claude.com/docs/en/setup |

Log in to GitHub once:

```bash
gh auth login
```

Pick a room name nobody else uses, for example `coopdev-demo-4821`. Use it in every command below. In the commands, replace `YOUR_GITHUB_NAME` with your GitHub user name.

Wake the free server. Open this in a browser and wait until the page loads (up to a minute):

```text
https://team-contract.onrender.com/app?room=coopdev-demo-4821
```

(The address still has the old name. That is only the Render address, the product is CoopDev.)

**Expect:** a workspace page for your room with a setup checklist.

## 1. Make Ali's project

```bash
mkdir -p ~/coopdev-demo/ali && cd ~/coopdev-demo/ali
git init -q -b main
echo "# Translator app" > README.md
git add README.md && git commit -qm "start"
```

**Expect:** a folder with one commit on branch `main`.

## 2. Connect Ali (Terminal A)

```bash
curl -fsSL https://team-contract.onrender.com/install.sh | bash -s -- --server https://team-contract.onrender.com --room coopdev-demo-4821 --name Ali
```

Answers to the questions:

| Question | Answer |
| --- | --- |
| Connect GitHub for sharing and syncing? | **n** for now (we link it in step 4) |
| Keep merged code up to date while your workspace is open? | **n** |
| Open your workspace now? | **n** |

**Expect:** "server reached", a list of OK lines, and "Ready. Next time, in this folder, run: ./coopdev work".

Setup added ignore rules to `.gitignore`. Commit them so the repo stays clean:

```bash
git add .gitignore && git commit -qm "ignore CoopDev files"
```

## 3. Set the team key (Browser)

On the dashboard press **Set team key**. Enter `Ali` and a key of 8 or more characters, for example `demo-key-2026`. Remember it. The key is the room's password for things only a person may do: settling conflicts, approving requests, linking GitHub. Agents never get it.

**Expect:** the checklist shows the key step as done.

## 4. Put the project on GitHub and link the room (Terminal A)

This creates a **private** repository and links it to the room in one step:

```bash
python3 coord/git_sync.py create YOUR_GITHUB_NAME/coopdev-demo
```

Enter the team key when it asks.

**Expect:** "Created private repository https://github.com/YOUR_GITHUB_NAME/coopdev-demo", then a link message. On the dashboard a **GitHub** panel shows the repository.

## 5. Make Mei's copy and connect her (Terminal B)

Mei clones the repository, like a real teammate would. Run this in a normal terminal:

```bash
cd ~/coopdev-demo && gh repo clone YOUR_GITHUB_NAME/coopdev-demo mei && cd mei
```

```bash
curl -fsSL https://team-contract.onrender.com/install.sh | bash -s -- --server https://team-contract.onrender.com --room coopdev-demo-4821 --name Mei
```

Same answers as Ali, except GitHub: here answer **y**. It is already logged in, so it only asks you to link; if it asks for the team key, enter the same key. If it says the room is already linked, that is fine.

Ali already committed the ignore rules, so Mei has nothing to commit. `git status` should print nothing.

**Expect:** the dashboard shows two people, Ali and Mei.

## 6. Start Claude Code in both terminals

```bash
claude
```

Say yes to trusting the folder, to the `coopdev` server and to the hooks. Approve each `coopdev` tool the first time it is used, or pick "Yes, don't ask again".

**Expect:** nothing special on screen. If no `coopdev` tools are ever called, quit Claude and start it again.

---

# The showcase

Each scene says what to type and what is supposed to happen.

## Scene A. Shared decision (Terminal A)

> We will build the translator backend with FastAPI. Save that as a team decision.

**Expect:** Claude calls `record_decision`: "Recorded in the shared contract". The decision shows under **Team decisions** on the dashboard.

## Scene B. A conflict a person settles (B, then Browser)

**Terminal B:**

> Set up the translator backend with Express on port 3000.

**Expect:** Claude calls `record_decision`, gets **CONFLICT with the shared contract** (FastAPI was chosen), stops and asks you instead of writing Express code. The dashboard shows a red **Decision conflicts** card.

**Browser:** press **Keep this** under FastAPI, enter `Ali` and the team key.

**Expect:** the card disappears. Mei's next prompt follows FastAPI.

## Scene C. Claim, then a blocked edit (A, then B)

**Terminal A:**

> Create translate.py with a function translate(text, language) that returns a placeholder string.

**Expect:** Claude calls `claim_work` for `translate.py` ("Claimed … Go ahead"), then writes the file. The dashboard shows Ali's claim and a **Recent file edits** line with a one-sentence summary.

**Terminal B** (Mei has not pulled Ali's work):

> Create translate.py with a translate(text) function.

**Expect:** `claim_work` answers **NOT CLAIMED**: Ali has the file. Claude tells you and suggests other work.

Now push it:

> I understand, write it anyway.

**Expect:** the write is **blocked before it happens**, with a block like:

```text
[CoopDev: ACTIVE COLLISION]
File: translate.py
  Ali claimed this for "…"
  Ali edited this file (1 min ago): …
Edit blocked before writing. Resolve the overlap before trying again.
```

Check with `!ls`: Mei has no `translate.py`.

## Scene D. Team chat (A, then B)

**Terminal A:**

> Tell the team that the demo is at 3pm and nobody edits translate.py after 2:30.

**Expect:** `send_message`: "Sent to the whole team". The message shows in **Team chat**.

**Terminal B:**

> What's new from the team?

**Expect:** Claude relays Ali's message. Asking again does not repeat it.

## Scene E. Ask a teammate's agent (A, B, B, A)

**Terminal A:**

> Ask Mei's agent which files are in her folder. Read only.

**Expect:** `ask_teammate`: "Request #N sent to Mei … Nothing runs until Mei approves." The dashboard shows **Waiting for approval**.

**Terminal B:**

> Anything for me?

**Expect:** Claude shows the request and **asks whether to run it**. It does not run yet.

> Yes, run it.

**Expect:** Claude lists the files, then calls `answer_ask`. The dashboard shows **Done** with the answer.

**Terminal A:**

> Any news?

**Expect:** Claude reports the answer from Mei's agent.

## Scene F. Share through GitHub, then pull (A, GitHub, B)

**Terminal A:** release the claim and commit the work on a task branch.

```text
!python3 coord/git_sync.py start ali/translate-function
```

This makes a task branch from the latest shared code and moves your unsaved work onto it. (`./coopdev start` does the same but asks you a question, and questions do not work well after `!`. Use it in a normal terminal if you prefer.) Then:

> I'm done with translate.py. Release my claim.

```text
!git add translate.py && git commit -m "add translate function"
!./coopdev share
```

**Expect:** "This shares saved Git commits." Then a pull request opens on GitHub. The dashboard's GitHub panel shows Ali's branch and the pull request.

**GitHub (Browser):** open the pull request from the dashboard (**View changed files**) and press **Merge**. Merging is always a person's job on GitHub.

**Terminal B:** get the merged code:

```text
!./coopdev sync
```

**Expect:** `translate.py` arrives in Mei's folder (check with `!ls`). Now:

> Add a function supported_languages() to translate.py.

**Expect:** Claude claims the file and edits it **with no collision warning**. Ali's version is already in Mei's Git history, so CoopDev knows she has it. Compare with Scene C: the same file was blocked before she pulled.

## Scene G. One-screen status (A and B)

```text
!./coopdev today
```

**Expect:** plain sections: teammates, what needs you, your work, what teammates are doing, latest messages, and **one next step** at the end, plus the dashboard address.

---

# Clean up

**Browser:** at the bottom of the dashboard, **Reset room** (name and team key).

```bash
rm -rf ~/coopdev-demo
gh repo delete YOUR_GITHUB_NAME/coopdev-demo --yes
```

The last command deletes the demo repository on GitHub. Skip it if you want to keep it.

# If something does not happen

| What you see | What to do |
| --- | --- |
| No `coopdev` tools are called | Quit Claude, run `claude` again, approve the `coopdev` server. If no approval question appears, run `./coopdev doctor` |
| `[CoopDev: CHECK UNAVAILABLE]` | The server is asleep. Open the dashboard, wait, retry |
| `create` says "already has an origin" | The folder already has a GitHub remote. Use `python3 coord/git_sync.py link` instead |
| `create` or `link` asks for a key you do not have | Do step 3 first |
| Scene C writes the file anyway | Check both folders show the same room in `!./coopdev today`, and that hooks were approved |
| Scene B shows no conflict | The dashboard footer says whether the conflict check is on. Off means the server has no AI key |
| `share` finds nothing to share | Commit first. Only saved commits are shared |
| Everything vanished from the dashboard | The free server restarted and lost the room. Start again from the room step |
| Page looks unstyled | Reload with Cmd+Shift+R |

# For the video

Take the screenshots in the order of the scenes. Hide long lines with `/focus` in Claude Code, and keep each terminal about 100 columns wide. Wake the server five minutes before recording, and record Scenes A to G in one run, because a server restart wipes the room.
