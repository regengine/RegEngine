"""Env-guard checks for the PostgreSQL evidence workflow; no database needed.

The evidence workflow module skips entirely without
REGENGINE_EVIDENCE_TEST_DATABASE_URL, so these guard tests live here and
load only the small env-check helper from that module.
"""

import importlib.util
from pathlib import Path

import pytest

PG_WORKFLOW_FILE = Path(__file__).resolve().parent / "test_postgres_evidence_workflow_pg.py"
EVIDENCE_URL = "postgresql://regengine:pw@localhost:5432/live_suite"


def _load_check():
    spec = importlib.util.spec_from_file_location("pg_evidence_env_target", PG_WORKFLOW_FILE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._require_database_url_matches


def test_missing_database_url_fails_with_readable_message(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(AssertionError, match="DATABASE_URL must be set"):
        _load_check()(EVIDENCE_URL)


def test_mismatched_database_url_fails_with_readable_message(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://regengine:pw@localhost:5432/other_db")
    with pytest.raises(AssertionError, match="must equal REGENGINE_EVIDENCE_TEST_DATABASE_URL"):
        _load_check()(EVIDENCE_URL)


def test_matching_database_url_passes(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", EVIDENCE_URL)
    _load_check()(EVIDENCE_URL)
