#!/usr/bin/env python3
"""Link a Team Contract room to GitHub and publish committed task work."""

import argparse
import getpass
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))  # the coord folder
from tc_http import urlopen  # noqa: E402

PROJECT = Path(__file__).resolve().parent.parent
REPOSITORY = r"[a-zA-Z0-9][a-zA-Z0-9-]{0,38}/[a-zA-Z0-9_.-]{1,100}"


def command(*args: str) -> str:
    env = {**os.environ, "GH_PROMPT_DISABLED": "1", "GIT_TERMINAL_PROMPT": "0"}
    try:
        run = subprocess.run(args, cwd=PROJECT, capture_output=True, text=True, env=env, timeout=90)
    except FileNotFoundError:
        raise ValueError(f"Install {args[0]} before running this command.") from None
    except subprocess.TimeoutExpired:
        raise ValueError(f"{args[0]} {args[1]} timed out. Check the remote before retrying.") from None
    if run.returncode:
        detail = re.sub(r"https?://[^\s/]+@", "https://[redacted]@", run.stderr.strip())
        raise ValueError(detail or f"{args[0]} {args[1]} failed.")
    return run.stdout.strip()


def github_repository(remote: str) -> str:
    match = re.fullmatch(
        rf"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)({REPOSITORY})/?",
        remote,
        re.IGNORECASE,
    )
    if not match:
        raise ValueError("Set origin to a github.com HTTPS or SSH remote.")
    repo = match[1].removesuffix(".git").lower()
    if not re.fullmatch(REPOSITORY, repo) or repo.split("/")[1] in {".", ".."}:
        raise ValueError("The origin repository name is invalid.")
    return repo


def origin_repository() -> str:
    remotes = command("git", "remote", "get-url", "--all", "origin").splitlines()
    push_remotes = command("git", "remote", "get-url", "--push", "--all", "origin").splitlines()
    if len(remotes) != 1 or len(push_remotes) != 1:
        raise ValueError("Origin must have one fetch URL and one push URL.")
    repo = github_repository(remotes[0])
    if github_repository(push_remotes[0]) != repo:
        raise ValueError("Origin fetch and push URLs must point to the same GitHub repository.")
    return repo


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def api(me: dict, method: str, path: str, body: dict | None = None, token: str = "") -> dict:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Contract-Token"] = token
    url = me["server"].rstrip("/") + path
    if token:
        target = urllib.parse.urlsplit(url)
        if target.scheme != "https" and target.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Use HTTPS to link a room on a remote server.")
    request = urllib.request.Request(
        url, method=method, headers=headers,
        data=json.dumps({"room": me["room"], **body}).encode() if body is not None else None,
    )
    try:
        with urlopen(request, timeout=15, handlers=(NoRedirect(),)) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(f"Team Contract request failed (HTTP {error.code}): {error.read().decode()[:300]}") from None
    except urllib.error.URLError as error:
        raise ValueError(f"Could not reach Team Contract: {error.reason}") from None


def approval_token() -> str:
    if not sys.stdin.isatty():
        raise ValueError("Run this command in a terminal to enter the team key.")
    token = getpass.getpass("Team key for this room: ")
    if not token:
        raise ValueError("Enter the room's team key (set on the dashboard) to link the room.")
    return token


def linked_repository(me: dict) -> dict | None:
    query = urllib.parse.urlencode({"room": me["room"]})
    return api(me, "GET", f"/git?{query}")["repository"]


def link(me: dict, repo: str, token: str) -> None:
    info = json.loads(command("gh", "repo", "view", repo, "--json", "defaultBranchRef"))
    branch = info.get("defaultBranchRef")
    if not branch:
        raise ValueError("Create an initial commit on GitHub before linking this repository.")
    base = branch["name"]
    api(me, "PUT", "/git", {"repository": repo, "base_branch": base}, token)
    print(f"Linked room {me['room']} to {repo} (base branch: {base}).")


def create_repository(me: dict, repo: str) -> None:
    if not re.fullmatch(REPOSITORY, repo) or repo.split("/")[1] in {".", ".."}:
        raise ValueError("Give the new private repository as OWNER/REPO.")
    if "origin" in command("git", "remote").splitlines():
        raise ValueError("This checkout already has an origin. Use link for an existing repo.")
    if linked_repository(me):
        raise ValueError("This room already has a linked repository.")
    branch = command("git", "branch", "--show-current")
    if not branch:
        raise ValueError("Switch to a named branch before creating a repository.")
    command("git", "rev-parse", "--verify", "HEAD")
    token = approval_token()
    query = urllib.parse.urlencode({"room": me["room"]})
    api(me, "GET", f"/git/link-access?{query}", token=token)
    command("gh", "repo", "create", repo, "--private", "--source", ".", "--remote", "origin", "--push")
    print(f"Created private repository https://github.com/{repo}.", flush=True)
    link(me, origin_repository(), token)


def open_pr(repo: str, branch: str, base: str) -> dict | None:
    if branch == base:
        return None
    matches = json.loads(command(
        "gh", "pr", "list", "--repo", repo, "--head", branch, "--base", base,
        "--state", "open", "--json", "number,url,isCrossRepository",
    ))
    return next((pr for pr in matches if not pr["isCrossRepository"]), None)


def publish(repo: str, branch: str, base: str, ahead: int, title: str | None) -> dict:
    if branch == base:
        raise ValueError(f"Switch to a task branch before publishing. {base} is the review target.")
    if ahead == 0:
        raise ValueError(f"There are no commits on this branch to propose against {base}.")
    existing = open_pr(repo, branch, base)
    if command("git", "status", "--porcelain"):
        print("Only committed changes will be pushed.", file=sys.stderr)
    command(
        "git", "push", "--no-follow-tags", "--recurse-submodules=no", "origin",
        f"refs/heads/{branch}:refs/heads/{branch}",
    )
    print(f"Pushed {branch} to {repo}.", flush=True)
    if existing:
        return existing
    title = title or command("git", "log", "-1", "--format=%s") or branch
    try:
        url = command(
            "gh", "pr", "create", "--repo", repo, "--base", base, "--head", branch,
            "--draft", "--title", title, "--body", "Task branch shared with Team Contract.",
        )
    except ValueError as error:
        # Another publish may have created the PR between list and create.
        existing = open_pr(repo, branch, base)
        if existing:
            return existing
        raise ValueError(f"The branch is on GitHub. Retry publish to create its PR. {error}") from error
    return {"number": int(url.rstrip("/").rsplit("/", 1)[1]), "url": url}


def linked_base(me: dict, repo: str) -> str:
    linked = linked_repository(me)
    if not linked:
        raise ValueError("The room has no repository. Ask the room owner to run git_sync.py link.")
    if linked["repository"] != repo:
        raise ValueError("Origin does not match the room's linked repository.")
    base = linked["base_branch"]
    command("git", "check-ref-format", f"refs/heads/{base}")
    return base


def fetch_base(base: str) -> str:
    ref = f"refs/remotes/origin/{base}"
    command(
        "git", "fetch", "--no-tags", "--no-recurse-submodules", "origin",
        f"+refs/heads/{base}:{ref}",
    )
    return ref


def sync(me: dict, repo: str, action: str, title: str | None) -> None:
    base = linked_base(me, repo)
    branch = command("git", "branch", "--show-current")
    if not branch:
        raise ValueError("Switch to a named branch before checking or publishing.")
    if action == "publish" and branch == base:
        raise ValueError(f"Switch to a task branch before publishing. {base} is the review target.")
    ref = fetch_base(base)
    behind, ahead = map(int, command(
        "git", "rev-list", "--left-right", "--count", f"{ref}...HEAD",
    ).split())
    if action == "publish":
        pr = publish(repo, branch, base, ahead, title)
    else:
        pr = open_pr(repo, branch, base)
    print(f"{branch}: {ahead} ahead, {behind} behind origin/{base}.")
    if pr:
        print(f"Pull request: {pr['url']}")
    try:
        api(me, "POST", "/git/activity", {
            "author": me["name"], "repository": repo, "base_branch": base,
            "branch": branch, "ahead": ahead, "behind": behind,
            "pr_number": pr["number"] if pr else None,
        })
    except ValueError as error:
        raise ValueError(f"Dashboard status was not sent. Run status to retry. {error}") from error
    print("Status sent to the Team Contract dashboard.")


def pull_requests(repo: str, base: str, state: str, fields: str) -> list[dict]:
    return json.loads(command(
        "gh", "pr", "list", "--repo", f"github.com/{repo}", "--base", base,
        "--state", state, "--limit", "50", "--json", fields,
    ))


def has_approval(pr: dict) -> bool:
    decision = pr.get("reviewDecision")
    if decision:
        return decision == "APPROVED"
    # GitHub can omit the aggregate decision on branches without required reviews.
    reviews = {review["state"] for review in (pr.get("latestReviews") or [])}
    return "APPROVED" in reviews and "CHANGES_REQUESTED" not in reviews


def approved_requests(repo: str, base: str) -> dict[int, str]:
    approved = pull_requests(
        repo, base, "open", "number,headRefOid,isDraft,reviewDecision,latestReviews",
    )
    return {
        pr["number"]: pr["headRefOid"] for pr in approved
        if not pr["isDraft"] and has_approval(pr)
    }


def merged_update(repo: str, base: str, ref: str) -> tuple[str, list[int]] | None:
    # Match GitHub's merge commits to the fetched branch history. An open PR
    # or an unrelated remote tip is not a pull target.
    commits = command("git", "rev-list", "--first-parent", f"HEAD..{ref}").splitlines()
    if not commits:
        return None
    merged = pull_requests(repo, base, "merged", "number,mergeCommit,reviewDecision,latestReviews")
    by_commit = {
        pr["mergeCommit"]["oid"]: pr["number"] for pr in merged
        if pr.get("mergeCommit") and has_approval(pr)
    }
    matches = [(commit, by_commit[commit]) for commit in commits if commit in by_commit]
    if not matches:
        return None
    return matches[0][0], [number for _, number in reversed(matches)]


def update_checkout(base: str, target: str) -> str:
    if command("git", "branch", "--show-current") != base:
        return f"Switch to {base} when ready to sync."
    for operation in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply", "sequencer", "BISECT_START"):
        if (PROJECT / command("git", "rev-parse", "--git-path", operation)).exists():
            return "Finish your current Git operation before syncing."
    if command("git", "status", "--porcelain", "--untracked-files=normal", "--ignore-submodules=none"):
        return "Local changes detected. Commit or stash them before syncing."
    ahead, behind = map(int, command(
        "git", "rev-list", "--left-right", "--count", f"HEAD...{target}",
    ).split())
    if ahead or not behind:
        return f"Local {base} cannot be fast-forwarded. Review it before syncing."
    command("git", "merge", "--ff-only", "--no-autostash", "--no-overwrite-ignore", target)
    return f"Updated local {base} to {target[:12]}."


def watch(me: dict, interval: int, notify_only: bool) -> None:
    print("Watching the linked repository. Press Ctrl+C to stop.", flush=True)
    approvals: set[tuple[str, str, int, str]] = set()
    last_status = ""
    while True:
        try:
            repo = origin_repository()
            base = linked_base(me, repo)
            current = {(repo, base, number, head) for number, head in approved_requests(repo, base).items()}
            for _, _, number, _ in sorted(current - approvals):
                print(f"[Team Contract] PR #{number} approved. Waiting for merge. "
                      f"https://github.com/{repo}/pull/{number}", flush=True)
            approvals = current
            update = merged_update(repo, base, fetch_base(base))
            status = ""
            if update:
                target, numbers = update
                prs = ", ".join(f"#{number}" for number in numbers)
                result = "Run git_sync.py watch without --notify-only to sync." if notify_only else update_checkout(base, target)
                status = f"Approved PRs merged into {base}: {prs}. {result}"
        except (OSError, ValueError, KeyError) as error:
            status = f"Watch check failed: {error}"
        if status and status != last_status:
            print(f"[Team Contract] {status}", flush=True)
        last_status = status
        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    subparsers.add_parser("link", help="link this origin to the room (room owner)")
    create_parser = subparsers.add_parser("create", help="create a private GitHub repo from committed local work and link it")
    create_parser.add_argument("repository", metavar="OWNER/REPO")
    subparsers.add_parser("status", help="fetch the base branch and report branch status")
    publish_parser = subparsers.add_parser("publish", help="push committed work and open or reuse its PR")
    publish_parser.add_argument("--title", help="title for a new draft PR")
    watch_parser = subparsers.add_parser("watch", help="notify about approved PRs and sync after merge")
    watch_parser.add_argument("--interval", type=int, default=30, help="seconds between checks (minimum 15)")
    watch_parser.add_argument("--notify-only", action="store_true", help="show updates without applying them")
    args = parser.parse_args()
    if args.action == "watch" and args.interval < 15:
        parser.error("--interval must be at least 15 seconds")
    try:
        me = json.loads((PROJECT / "coord/me.json").read_text())
        if command("git", "rev-parse", "--show-toplevel") != str(PROJECT):
            raise ValueError("Install Team Contract at the root of the Git repository.")
        if args.action == "create":
            create_repository(me, args.repository)
        elif args.action == "link":
            link(me, origin_repository(), approval_token())
        elif args.action == "watch":
            linked_base(me, origin_repository())
            watch(me, args.interval, args.notify_only)
        else:
            sync(me, origin_repository(), args.action, getattr(args, "title", None))
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f"Stopped: {error}")
    except KeyboardInterrupt:
        print("\nStopped watching.")


if __name__ == "__main__":
    main()
