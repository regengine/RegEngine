"""The deprecated bootstrap script must never print raw key material to stdout.

Stdout from operator scripts is captured in CI and run logs, so printing
``key_resp.raw_key`` leaks a live secret. The script may only print the
stored key prefix, which identifies the key without authenticating as it.
"""

from __future__ import annotations

from types import SimpleNamespace

import services.admin.scripts.bootstrap_auth as bootstrap_mod
from services.admin.scripts.bootstrap_auth import bootstrap, public_key_reference


def test_public_key_reference_exposes_prefix_not_secret():
    resp = SimpleNamespace(key_prefix="rge_live_abc123", raw_key="rge_live_SECRETVALUE")
    rendered = public_key_reference(resp)
    assert "rge_live_abc123" in rendered
    assert "SECRETVALUE" not in rendered
    assert "raw_key" not in rendered


async def test_bootstrap_stdout_contains_no_raw_key(capsys, monkeypatch):
    raw_key = "rge_live_SUPERSECRETKEYMATERIAL"
    resp = SimpleNamespace(key_prefix="rge_live_abc123", raw_key=raw_key)

    class FakeStore:
        async def create_key(self, **kwargs):
            return resp

        async def close(self):
            return None

    async def fake_get_db_key_store():
        return FakeStore()

    monkeypatch.setattr(bootstrap_mod, "get_db_key_store", fake_get_db_key_store)
    await bootstrap()

    out = capsys.readouterr().out
    assert "BOOTSTRAP_SUCCESS" in out
    assert "rge_live_abc123" in out
    assert raw_key not in out
