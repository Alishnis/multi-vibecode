# Team Contract demo

## Before presenting

1. Open [Render health](https://team-contract.onrender.com/health) early. Wait for `{"ok":true}`, then keep the demo dashboard open.
2. Use a fresh room with two Claude Code sessions named Ali and Teammate. Follow the [setup guide](README.md), approve the project tool, and use Manual mode. In each session, ask “Say ready. Do not record a decision.” Check the dashboard shows both names and an empty contract.
3. Rehearse the prompts below and save a local copy of the rehearsal results. Have the backup video ready. If the live agent is silent for 20 seconds, switch to the backup.

## Five-minute run

| Time | What judges see |
| --- | --- |
| 0:00–0:25 | Tell the team's real hackathon story. Use numbers only if the team can verify them. |
| 0:25–0:50 | Show the baseline from two empty folders. The Python session chose port 8000 and the JavaScript session chose port 3000. |
| 0:50–1:10 | Open the shared dashboard with both people visible. |
| 1:10–1:50 | Ali records FastAPI on port 18763. Point to the decision as it appears. |
| 1:50–2:35 | Teammate recalls the framework and port, then proposes Express. Show the conflict card and the saved FastAPI decision. |
| 2:35–3:00 | Follow the saved decision. Say “Both agents can read the same project decisions before they write code.” |
| 3:00–5:00 | Explain the first customers and proposed pricing. End with the team's ask and describe the scope of the test: two sessions on one Mac, using a hosted server. |

## Copy and paste prompts

**Baseline.** Start in two empty folders without Team Contract installed. Run the same prompt in both and change only the last word from Python to JavaScript.

> Set up the backend for our team's todo app, with one endpoint that lists todos. Create only the minimal starter files. Do not install anything or run any commands. I'm most comfortable with Python.

**Ali.**

> Record one team-contract decision: The todo backend uses FastAPI on port 18763.

**Teammate.**

> What framework and port did the team choose for the todo backend?

> Propose switching the todo backend to Express through the team-contract tool. Do not write any code.

For an API rehearsal, have Ali also record “GET /todos returns a JSON object containing an items array.” Ask Teammate to propose changing it to a bare JSON array through the tool.

## Rehearsal results

On November 13, 2026, two fresh Claude Code sessions on one Mac shared the FastAPI choice, port 18763, and the `GET /todos` response shape through Render. The second session submitted Express and a bare array as separate proposals. Render logged both conflicts against the original decisions, which stayed in the contract. In the baseline, both agents returned a JSON array, but the Python version used `done` and the JavaScript version used `completed` for the same field.

## AgentMash comparison

The AgentMash 0.14.0 test reached a valid room from two temporary repositories. Its server refused unsigned reports with `402 free_plan_sign_in`, including the test file edit. The second session therefore had no confirmed teammate activity to inspect. The comparison is inconclusive.

To resume, use [AgentMash's setup guide](https://agentmash.dev/docs/setup) and sign in with GitHub from an isolated test repository. Confirm `agentmash doctor` accepts reports and verify that the second session can see a synthetic edit from the first. Use separate checkouts and distinct test identities. Then repeat the pre-edit test in a clean room:

1. In session A, share the framework, port, and response shape using the available AgentMash features. Do not edit any project files.
2. In session B, ask for the framework, port, and response shape without including the answers. Record what it can recover, where the information came from, and whether it was supplied automatically or queried.
3. Propose Express and a bare array before writing code. Record whether AgentMash warns about either proposal, and whether it identifies the earlier decision.

AgentMash documents warnings for overlapping file edits and changes to shared code symbols. Describe what Team Contract demonstrated until the signed-in comparison establishes how both products handle this scenario. [AgentMash conflict docs](https://agentmash.dev/docs/conflicts)
