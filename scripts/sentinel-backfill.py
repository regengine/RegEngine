#!/usr/bin/env python3
"""
sentinel-backfill — reconstruct closing-PR references for closed GH issues
whose `closedByPullRequestsReferences` field is empty.

Why: GitHub's auto-close field is empty for issues closed via commit message,
manual close, or legacy auto-close pre-2021. The Sentinel regressor cannot
anchor on those issues, leaving regression detection blind to a large slice
of the closed-issue universe.

Strategy (per issue, in order; first hit wins):
  1. GraphQL `ClosedEvent.closer` — works when GitHub recorded the closing
     commit/PR even though it didn't populate the legacy field.
  2. Comment + body scan for "Fixes #N" / "Closed by #N" / "Resolves #N"
     patterns. Each candidate `N` is verified to actually be a PR via
     `gh api repos/<r>/pulls/N` before being accepted.

Output: .claude/sentinel_anchors.json — single source of truth the
orchestrator loads at startup.

Usage:
    python scripts/sentinel-backfill.py            # full backfill
    python scripts/sentinel-backfill.py --limit 50 # smoke test
    python scripts/sentinel-backfill.py --dry-run  # don't write file

Re-run policy: idempotent. Safe to re-run any time. Anchors recovered on
prior runs are re-verified each time.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ANCHORS_PATH = REPO_ROOT / ".claude" / "sentinel_anchors.json"

# Patterns indicating a closing PR reference. The verify step rejects
# matches that resolve to issue numbers rather than PR numbers.
CLOSE_PATTERNS = [
    re.compile(r"(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)", re.I),
    re.compile(r"closed\s+by\s+#(\d+)", re.I),
    re.compile(r"merged\s+(?:in\s+)?#(\d+)", re.I),
    re.compile(r"#(\d+)\s+(?:closed|fixed|resolved)\s+this", re.I),
    re.compile(r"PR\s+#(\d+)", re.I),
]

# GraphQL: walk the issue's CLOSED_EVENT timeline; closer is Commit | PullRequest.
GRAPHQL_TIMELINE = """
query($owner:String!, $repo:String!, $num:Int!) {
  repository(owner:$owner, name:$repo) {
    issue(number:$num) {
      timelineItems(itemTypes:[CLOSED_EVENT], last:5) {
        nodes {
          ... on ClosedEvent {
            closer {
              __typename
              ... on PullRequest { number }
              ... on Commit {
                oid
                associatedPullRequests(first:3) { nodes { number merged } }
              }
            }
          }
        }
      }
    }
  }
}
"""


def gh(*args: str, check: bool = True) -> str:
    r = subprocess.run(["gh", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"gh {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def detect_repo() -> tuple[str, str]:
    raw = gh("repo", "view", "--json", "owner,name")
    data = json.loads(raw)
    return data["owner"]["login"], data["name"]


def load_universe() -> tuple[dict[int, int], list[int]]:
    """Return (already-anchored map, unanchored list)."""
    raw = gh(
        "issue",
        "list",
        "--state",
        "closed",
        "--limit",
        "2000",
        "--json",
        "number,closedByPullRequestsReferences",
    )
    issues = json.loads(raw)
    anchored: dict[int, int] = {}
    unanchored: list[int] = []
    for i in issues:
        prs = i.get("closedByPullRequestsReferences") or []
        if prs:
            anchored[i["number"]] = prs[0]["number"]
        else:
            unanchored.append(i["number"])
    return anchored, sorted(unanchored, reverse=True)


def resolve_via_close_event(owner: str, repo: str, num: int) -> int | None:
    raw = gh(
        "api",
        "graphql",
        "-f",
        f"query={GRAPHQL_TIMELINE}",
        "-f",
        f"owner={owner}",
        "-f",
        f"repo={repo}",
        "-F",
        f"num={num}",
        check=False,
    )
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    nodes = (
        data.get("data", {}).get("repository", {}).get("issue", {}).get("timelineItems", {}).get("nodes", [])
    ) or []
    for n in nodes:
        closer = n.get("closer")
        if not closer:
            continue
        if closer.get("__typename") == "PullRequest":
            return closer.get("number")
        if closer.get("__typename") == "Commit":
            apr = (closer.get("associatedPullRequests") or {}).get("nodes") or []
            for pr in apr:
                if pr.get("merged"):
                    return pr["number"]
            if apr:
                return apr[0]["number"]
    return None


def is_pull_request(owner: str, repo: str, n: int) -> bool:
    raw = gh(
        "api",
        f"repos/{owner}/{repo}/pulls/{n}",
        "--silent" if False else "-i",
        check=False,
    )
    # status line: "HTTP/2.0 200" => PR exists; 404 => not a PR (issue or absent)
    return raw.startswith(("HTTP/2.0 200", "HTTP/1.1 200"))


def resolve_via_comments(owner: str, repo: str, num: int) -> int | None:
    raw = gh("issue", "view", str(num), "--json", "body,comments", check=False)
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    haystack = data.get("body") or ""
    for c in data.get("comments") or []:
        haystack += "\n" + (c.get("body") or "")
    candidates: list[int] = []
    for pat in CLOSE_PATTERNS:
        candidates.extend(int(m.group(1)) for m in pat.finditer(haystack))
    if not candidates:
        return None
    # Prefer most-recent (highest) candidate; verify each is actually a PR.
    for n in sorted(set(candidates), reverse=True):
        if n == num:
            continue  # self-reference
        if is_pull_request(owner, repo, n):
            return n
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--limit", type=int, default=0, help="Process at most N unanchored issues (0 = all). For smoke testing."
    )
    ap.add_argument("--dry-run", action="store_true", help="Resolve and print stats; do not write the anchors file.")
    args = ap.parse_args()

    owner, repo = detect_repo()
    print(f"[backfill] repo={owner}/{repo}", flush=True)

    print("[backfill] loading universe...", flush=True)
    anchored, unanchored = load_universe()
    print(f"[backfill] anchored={len(anchored)}  unanchored={len(unanchored)}", flush=True)

    targets = unanchored[: args.limit] if args.limit else unanchored
    recovered: dict[int, int] = {}
    failed: list[int] = []
    started = time.time()

    for i, num in enumerate(targets, 1):
        if i % 25 == 0 or i == len(targets):
            elapsed = time.time() - started
            rate = i / elapsed if elapsed else 0
            eta = (len(targets) - i) / rate if rate else 0
            print(
                f"[backfill] {i}/{len(targets)}  recovered={len(recovered)}  rate={rate:.1f}/s  eta={eta:.0f}s",
                flush=True,
            )
        pr = resolve_via_close_event(owner, repo, num)
        if pr is None:
            pr = resolve_via_comments(owner, repo, num)
        if pr is not None:
            recovered[num] = pr
        else:
            failed.append(num)

    payload = {
        "_generated_by": "scripts/sentinel-backfill.py",
        "_repo": f"{owner}/{repo}",
        "_anchored_via_gh": len(anchored),
        "_recovered_via_backfill": len(recovered),
        "_unrecoverable": len(failed),
        "_total_anchored_after_backfill": len(anchored) + len(recovered),
        "anchors": {str(k): v for k, v in {**anchored, **recovered}.items()},
        "unrecoverable": sorted(failed),
    }

    if args.dry_run:
        print("[backfill] DRY RUN — not writing.")
        print(json.dumps({k: v for k, v in payload.items() if k != "anchors"}, indent=2))
        return 0

    ANCHORS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ANCHORS_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        f"[backfill] wrote {ANCHORS_PATH.relative_to(REPO_ROOT)}: "
        f"anchored={len(anchored)} +recovered={len(recovered)} unrecoverable={len(failed)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
