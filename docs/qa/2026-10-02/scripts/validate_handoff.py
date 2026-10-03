#!/usr/bin/env python3
"""Validate the local QA handoff without changing git or contacting a service."""
from collections import Counter
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[4]
QA = ROOT / "docs/qa/2026-10-02"


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def main() -> None:
    assert git("branch", "--show-current") == "qa/2026-10-02-sweep"
    required = ["PLAN.md", "SESSION-LOG.md", "FINDINGS.md", "COVERAGE.md", "SUMMARY.md"]
    for name in required:
        assert (QA / name).is_file(), f"Missing {name}"
        assert (QA / name).stat().st_size > 100, f"Empty report {name}"
    rows = []
    for line in (QA / "FINDINGS.md").read_text().splitlines():
        if re.match(r"\| (?:BE|FE|UX)-\d{3} \|", line):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            assert len(cells) == 9, f"Incorrect columns: {cells[0]}"
            assert all(cells), f"Empty finding field: {cells[0]}"
            rows.append(cells)
    assert rows, "No finding rows found"
    assert len({r[0] for r in rows}) == len(rows), "Duplicate finding IDs"
    counts = Counter(r[1] for r in rows)
    assert not (set(counts) - {"Critical", "High", "Medium", "Low"})
    count_line = "Counts: " + " ".join(f"{s}={counts[s]}" for s in ("Critical", "High", "Medium", "Low"))
    summary = (QA / "SUMMARY.md").read_text()
    assert count_line in summary, f"Expected {count_line}"
    assert "PR: opened by orchestrator" in summary
    assert "CI status: pending at time of writing" in summary
    for group in ("BACKEND", "FRONTEND", "UX"):
        for suffix in ("REPORT", "SESSION-LOG"):
            assert (QA / f"{group}-{suffix}.md").is_file()
    changed = set(filter(None, git("diff", "--name-only", "HEAD").splitlines()))
    changed.update(filter(None, git("ls-files", "--others", "--exclude-standard").splitlines()))
    allowed = (
        "docs/qa/2026-10-02/", "tests/qa_sweep_20261002/",
        "services/ingestion/tests/test_qa_sweep_20261002_",
        "frontend/src/__tests__/lib/qa-sweep-",
        "frontend/src/__tests__/hooks/useSync.test.tsx",
    )
    unexpected = [p for p in sorted(changed) if not p.startswith(allowed)]
    assert not unexpected, f"Unexpected changed files: {unexpected}"
    oversized = [str(p.relative_to(ROOT)) for p in QA.rglob("*") if p.is_file() and p.stat().st_size > 5_000_000]
    assert not oversized, f"Oversized artifact(s): {oversized}"
    print(count_line)
    print("Groups:", dict(Counter(r[2] for r in rows)))
    print(f"PASS: mandatory docs, group reports/logs, findings, branch and {len(changed)} allowed files")
    print("PR/CI remain orchestrator-owned; this check does not establish remote status.")


if __name__ == "__main__":
    main()
