# Team Contract

Team Contract shares project decisions between Claude Code sessions. Each prompt loads the decisions for your team's room. When Claude proposes a decision that contradicts an existing one, the server logs the conflict and keeps the existing decision in the contract.

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

Run the installer from a checkout of this repository, pointing it at your own project folder. Each teammate uses their own name and the same room code and server URL. Start a fresh Claude Code session in the installed project.

```sh
python3 install.py /path/to/project --name YOUR_NAME --room SHARED_ROOM_CODE \
  --server https://team-contract.onrender.com
```

The hosted flow has been tested with two independent sessions on one Mac. Setup and connectivity from a second laptop and Windows support are still untested.

## Troubleshooting

- **Python reports `CERTIFICATE_VERIFY_FAILED` on macOS.** If `/etc/ssl/cert.pem` exists, prefix the failing command with `SSL_CERT_FILE=/etc/ssl/cert.pem`. For example, run `(cd "$test_dir/ali" && SSL_CERT_FILE=/etc/ssl/cert.pem claude --permission-mode default)`. Use the same prefix for the teammate session and for `install.py` if its connection check fails. This tells Python which trusted certificates to use. For a Python.org installation, you can also run its bundled [Install Certificates.command](https://docs.python.org/3/using/mac.html).
- **Claude Code Auto mode denies the recording tool.** Launch the test session with `claude --permission-mode default` and review the tool call in Manual mode. If the MCP server itself is missing, follow the installer's project approval instructions. [Claude Code permission modes](https://code.claude.com/docs/en/permission-modes)
- **The dashboard is empty after a pause.** Check the room code and confirm the first decision was saved. Render's free service can take about a minute to wake, and the SQLite database can be cleared by spin-down, restart, or deploy. [Render free service limits](https://render.com/docs/free)

## Run your own server

Copy `.env.example` to `.env` and put your OpenRouter API key there to enable conflict checking. Start the server with `sh start_server.sh`, then use `http://127.0.0.1:8000` as the installer URL for both sessions. Keep the server terminal open during the test.

The hosted prototype has no accounts. Anyone who knows the room code can access and change its decisions. Use a fresh room with sample decisions when testing.

## Check a plan and request a decision

Update your checkout, rerun the installer for each test project, and restart Claude Code to load the new tools. The server needs a working OpenRouter key for plan reviews.

1. Ask Claude to check a plan that depends on a shared choice, such as the response shape for `GET /todos`. `check_plan` reports contradictions and missing agreements without changing the contract.
2. For a missing agreement, ask Claude to use `request_decision` with the topic from the review. Requests with the same topic in a room share one record. Ask from a second session to see it reuse the existing request.
3. On the dashboard, select **Answer request**, choose a suggested decision or write one, and enter your name and approval token. The answer joins the contract once. A fresh prompt in either project reads it through the existing hook.

To enable dashboard approval, set a long random `CONTRACT_APPROVAL_TOKEN` in your local `.env` or in the Render service's environment settings. Share the token with the people who should approve decisions. Keep it out of project files and URLs. When set, the same token is required to reset rooms. It protects approval and reset, while the existing room-code access for reading and proposing decisions still applies.
