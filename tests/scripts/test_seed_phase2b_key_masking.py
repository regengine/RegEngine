"""Regression tests for scripts/seed_phase2b_key.py key masking.

The defect: seed_key() printed the full minted raw API key to stdout
("Seeding API Key: rge_phase2b.<secret>"), leaking the secret into shell
history, CI logs and any log aggregator. The fix prints only the key id
with the secret masked ("rge_phase2b.***") while still storing the full
SHA-256 hash in the database.

The script is loaded by file path because ``scripts/`` is not a package
(no __init__.py) and ``services/ingestion/scripts/`` (a real package)
shadows the name under pytest.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
from contextlib import redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_seeder():
    name = "test_support_seed_phase2b_key"
    spec = importlib.util.spec_from_file_location(
        name, REPO_ROOT / "scripts" / "seed_phase2b_key.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


seeder = _load_seeder()

SECRET = "s3cr3t-phase2b-secret-for-tests-only"
RAW_KEY = f"rge_phase2b.{SECRET}"


class _FakeCursor:
    def __init__(self):
        self.statements = []

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def fetchone(self):
        return None

    def close(self):
        pass


class _FakeConnection:
    def __init__(self):
        self.cursor_obj = _FakeCursor()
        self.committed = False

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.committed = True

    def rollback(self):
        pass

    def close(self):
        pass


def _run_seed(monkeypatch):
    monkeypatch.setattr(seeder, "SECRET", SECRET)
    monkeypatch.setattr(seeder, "RAW_KEY", RAW_KEY)
    conn = _FakeConnection()
    monkeypatch.setattr(seeder.psycopg, "connect", lambda *a, **k: conn)
    buf = io.StringIO()
    with redirect_stdout(buf):
        seeder.seed_key()
    return buf.getvalue(), conn


def test_seed_output_never_contains_raw_secret(monkeypatch):
    output, _ = _run_seed(monkeypatch)
    assert SECRET not in output
    assert RAW_KEY not in output


def test_seed_output_still_identifies_key_id(monkeypatch):
    output, _ = _run_seed(monkeypatch)
    assert "rge_phase2b" in output
    assert "***" in output


def test_masking_is_display_only_full_hash_still_stored(monkeypatch):
    _, conn = _run_seed(monkeypatch)
    expected_hash = hashlib.sha256(RAW_KEY.encode()).hexdigest()
    all_params = [v for _, p in conn.cursor_obj.statements if p for v in p]
    assert expected_hash in all_params
    assert conn.committed
