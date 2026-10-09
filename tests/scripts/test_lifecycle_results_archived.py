"""The checked-in lifecycle snapshot must say it is archived.

scripts/lifecycle_test_results.json is a stale all-error run captured by
scripts/seed_lifecycle_test.py. Readers must be able to tell it is not a
current result, so the file must carry archival metadata.
"""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = REPO_ROOT / "scripts" / "lifecycle_test_results.json"


def _load_snapshot() -> dict:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def test_snapshot_is_marked_archived():
    data = _load_snapshot()
    assert data.get("_archived") is True


def test_snapshot_note_says_failures_are_not_current():
    data = _load_snapshot()
    note = data.get("_note", "")
    assert "not current" in note
    assert "scripts/seed_lifecycle_test.py" in (note + data.get("_generated_by", "") + data.get("_regenerate", ""))


def test_snapshot_still_carries_original_sections():
    data = _load_snapshot()
    for key in (
        "suppliers",
        "products",
        "cte_events",
        "compliance",
        "audit_log",
        "recall_simulation",
        "recall_report",
        "fda_export",
        "mock_drill",
    ):
        assert key in data
