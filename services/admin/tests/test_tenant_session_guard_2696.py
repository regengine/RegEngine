"""#2696: ``get_tenant_session`` raises on a falsy tenant_id.

Pre-fix, a falsy/empty ``tenant_id`` silently yielded a session with NO
``app.tenant_id`` GUC, relying solely on the RLS fail-closed predicate and
hiding the caller's bug.
"""

from __future__ import annotations

import pytest


@pytest.mark.parametrize("bad_tenant", ["", None])
def test_falsy_tenant_id_raises(bad_tenant):
    from services.admin.app.database import get_tenant_session

    gen = get_tenant_session(bad_tenant)
    with pytest.raises(ValueError, match="non-empty tenant_id"):
        next(gen)


def test_valid_tenant_id_yields_session(monkeypatch):
    from unittest.mock import MagicMock

    import services.admin.app.database as db_mod

    session = MagicMock()
    monkeypatch.setattr(db_mod, "SessionLocal", lambda: session)

    calls = {}

    def _fake_guc(sess, tenant_id):
        calls["args"] = (sess, tenant_id)

    import shared.tenant_context as tc_mod

    monkeypatch.setattr(tc_mod, "set_tenant_guc", _fake_guc)

    gen = db_mod.get_tenant_session("11111111-1111-1111-1111-111111111111")
    yielded = next(gen)
    assert yielded is session
    if db_mod._engine.dialect.name != "sqlite":
        assert calls["args"][1] == "11111111-1111-1111-1111-111111111111"
