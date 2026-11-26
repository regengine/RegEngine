"""Measure the last 30 completed pull_request runs of five workflows: per-job median, p90, failures, top failing step."""

import collections
import datetime
import json
import statistics
import subprocess
import sys

WORKFLOWS = ["pr-gate.yml", "pr-guards.yml", "backend-ci.yml", "frontend-ci.yml", "security.yml"]
REPO = "regengine/RegEngine"


def api(path):
    out = subprocess.run(["gh", "api", path], capture_output=True, text=True, check=True).stdout
    # --paginate concatenates JSON objects; split on the boundary between them
    parts, depth, start, objs = [], 0, 0, []
    dec = json.JSONDecoder()
    i = 0
    while i < len(out):
        while i < len(out) and out[i].isspace():
            i += 1
        if i >= len(out):
            break
        obj, j = dec.raw_decode(out, i)
        objs.append(obj)
        i = j
    return objs


def dt(s):
    return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))


report = {}
for wf in WORKFLOWS:
    runs = []
    for page in api(f"repos/{REPO}/actions/workflows/{wf}/runs?event=pull_request&status=completed&per_page=30"):
        runs.extend(page.get("workflow_runs", []))
    runs = runs[:30]
    jobs_by_name = collections.defaultdict(list)
    run_rows = []
    for r in runs:
        wall = (dt(r["updated_at"]) - dt(r["run_started_at"] or r["created_at"])).total_seconds()
        run_rows.append(
            {
                "id": r["id"],
                "conclusion": r["conclusion"],
                "wall": wall,
                "sha": r["head_sha"][:7],
                "pr": (r.get("pull_requests") or [{}])[0].get("number"),
            }
        )
        for page in api(f"repos/{REPO}/actions/runs/{r['id']}/jobs?per_page=100"):
            for j in page.get("jobs", []):
                if not j.get("started_at") or not j.get("completed_at"):
                    continue
                dur = (dt(j["completed_at"]) - dt(j["started_at"])).total_seconds()
                failed_step = next((s["name"] for s in j.get("steps", []) if s.get("conclusion") == "failure"), None)
                jobs_by_name[j["name"]].append(
                    {"dur": dur, "conclusion": j["conclusion"], "step": failed_step, "run": r["id"]}
                )
    jobs = {}
    for name, rows in jobs_by_name.items():
        durs = sorted(x["dur"] for x in rows)
        p90 = durs[min(len(durs) - 1, int(round(0.9 * (len(durs) - 1))))]
        fails = [x for x in rows if x["conclusion"] == "failure"]
        causes = collections.Counter(x["step"] or "(no failing step recorded)" for x in fails)
        jobs[name] = {
            "n": len(rows),
            "median": statistics.median(durs),
            "p90": p90,
            "failures": len(fails),
            "cancelled": sum(1 for x in rows if x["conclusion"] == "cancelled"),
            "skipped": sum(1 for x in rows if x["conclusion"] == "skipped"),
            "top_cause": causes.most_common(1)[0] if causes else None,
        }
    report[wf] = {"runs": run_rows, "jobs": jobs}
    print(wf, len(runs), "runs", len(jobs), "job names", file=sys.stderr)
json.dump(report, open(sys.argv[1], "w"), indent=1, default=str)
print("done")
