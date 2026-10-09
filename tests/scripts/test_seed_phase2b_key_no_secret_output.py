"""seed_phase2b_key must never print the minted secret.

The script mints RAW_KEY from PHASE2B_API_SECRET. stdout must carry only the
public key id, never the secret or the full raw key, and the stored prefix
must not embed a character of the secret.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"

SENTINEL_SECRET = "sentinel-phase2b-secret-xyz"


class _FakeCursor:
    def __init__(self):
        self.statements = []
        self._calls = 0

    def execute(self, query, params=None):
        self.statements.append((query, params))

    def fetchone(self):
        self._calls += 1
        return None

    def close(self):
        pass


class _FakeConn:
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


def _load(monkeypatch, module_name):
    monkeypatch.setenv("PHASE2B_API_SECRET", SENTINEL_SECRET)
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / "seed_phase2b_key.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_seed_output_never_contains_secret(monkeypatch, capsys):
    mod = _load(monkeypatch, "_seed_phase2b_no_leak")
    conn = _FakeConn()
    monkeypatch.setattr(mod.psycopg, "connect", lambda *a, **k: conn)
    mod.seed_key()
    out = capsys.readouterr().out
    assert SENTINEL_SECRET not in out
    assert mod.RAW_KEY not in out
    assert mod.KEY_ID in out


def test_stored_prefix_contains_no_secret_char(monkeypatch, capsys):
    mod = _load(monkeypatch, "_seed_phase2b_prefix")
    conn = _FakeConn()
    monkeypatch.setattr(mod.psycopg, "connect", lambda *a, **k: conn)
    mod.seed_key()
    capsys.readouterr()
    inserts = [params for query, params in conn.cursor_obj.statements if "INSERT INTO api_keys" in query]
    assert inserts, "expected one api_keys insert"
    key_prefix = inserts[0][2]
    assert key_prefix == mod.KEY_ID
    assert SENTINEL_SECRET not in key_prefix
