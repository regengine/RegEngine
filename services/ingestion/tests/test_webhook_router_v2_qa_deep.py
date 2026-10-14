"""Deep-QA regression tests for ``app.webhook_router_v2``.

Each test below covers a real defect found during the QA pass: an
unhandled exception shape, a missing validation, or an env-parsing crash.
Every test fails on the pre-fix code (500 / raise / non-zero exit) and
passes after the fix.
"""

from __future__ import annotations

import subprocess
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_router_v2 as wr  # noqa: E402
from app.authz import IngestionPrincipal, get_ingestion_principal  # noqa: E402
from app.subscription_gate import require_active_subscription  # noqa: E402

TENANT_A = "00000000-0000-0000-0000-0000000000aa"


class _FakeRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


# ---------------------------------------------------------------------------
# 1. HMAC: non-ASCII signature must be a 401, not a 500 (TypeError).
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_hmac_non_ascii_signature_rejected_401(monkeypatch):
    """A header FastAPI decodes but compare_digest cannot compare.

    Pre-fix: ``hmac.compare_digest`` raised ``TypeError`` (unhandled 500).
    """
    from fastapi import HTTPException

    monkeypatch.setenv("WEBHOOK_HMAC_SECRET", "shh")
    req = _FakeRequest(b'{"events":[]}')
    with pytest.raises(HTTPException) as exc:
        await wr._verify_webhook_signature(req, x_webhook_signature="sha256=caf\u00e9")
    assert exc.value.status_code == 401
    assert exc.value.detail["error"] == "invalid_webhook_signature"


# ---------------------------------------------------------------------------
# 2. Replay window: non-string timestamp returns an error, never raises.
# ---------------------------------------------------------------------------


def test_timestamp_window_non_string_returns_error():
    """A datetime object passed to the helper is unparseable, not fatal.

    Pre-fix: ``datetime.replace("Z", ...)`` raised ``TypeError`` out of
    the helper (``_classify_replay_rejection`` already handled this).
    """
    err = wr._validate_event_timestamp_window(datetime.now(timezone.utc))
    assert err is not None
    assert "not parseable" in err


def test_negative_age_env_clamped_fail_closed(monkeypatch):
    """A negative WEBHOOK_MAX_EVENT_AGE_DAYS clamps to 0 (fail-closed).

    Pre-fix: the raw negative flowed into the comparison, so the floor
    became now + 5 days and the error message advertised the nonsense
    value (WEBHOOK_MAX_EVENT_AGE_DAYS=-5). Post-fix the value clamps to
    0, the window rejects loudly, and the message shows the clamped 0
    so the operator typo is visible.
    """
    monkeypatch.setenv("WEBHOOK_MAX_EVENT_AGE_DAYS", "-5")
    assert wr._max_event_age_days() == 0
    now = datetime.now(timezone.utc).isoformat()
    err = wr._validate_event_timestamp_window(now)
    assert err is not None
    assert "WEBHOOK_MAX_EVENT_AGE_DAYS=0" in err


# ---------------------------------------------------------------------------
# 3. Rate-limit env parsing: garbage must not crash the module import.
# ---------------------------------------------------------------------------


def test_ratelimit_garbage_env_imports_with_defaults():
    """All four rate-limit env vars set to garbage in a fresh interpreter.

    Pre-fix: ``int("abc")`` at module import raised ``ValueError`` and the
    whole service failed to start. Runs in a subprocess so the garbage env
    cannot leak into this test process's already-imported modules.
    """
    probe = (
        "import sys; sys.path.insert(0, %r); sys.path.insert(0, %r);"
        "from app.webhook_router_v2 import ratelimit as r;"
        "print(r._WEBHOOK_RATE_LIMIT_RPM, r._WEBHOOK_RATE_LIMIT_WINDOW_SECS,"
        " r._WEBHOOK_READ_RATE_LIMIT_RPM, r._WEBHOOK_READ_RATE_LIMIT_WINDOW_SECS)"
    ) % (str(service_dir), str(service_dir.parent))
    env = {
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "WEBHOOK_INGEST_RATE_LIMIT_RPM": "abc",
        "WEBHOOK_INGEST_RATE_LIMIT_WINDOW_SECONDS": "nope",
        "WEBHOOK_READ_RATE_LIMIT_RPM": "",
        "WEBHOOK_READ_RATE_LIMIT_WINDOW_SECONDS": "-40",
    }
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        cwd=str(service_dir),
        env=env,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    # "abc"/"nope"/"" fall back to defaults; "-40" floors at 1. The
    # import chain logs a dev-default DATABASE_URL warning to stdout,
    # so compare the last line, not the whole stream.
    assert proc.stdout.strip().splitlines()[-1] == "120 60 30 1"


def test_positive_int_env_helper(monkeypatch):
    from app.webhook_router_v2 import ratelimit as rl

    monkeypatch.setenv("WEBHOOK_INGEST_RATE_LIMIT_RPM", "not-a-number")
    assert rl._limit_from_env("WEBHOOK_INGEST_RATE_LIMIT_RPM", 120) == 120
    monkeypatch.setenv("WEBHOOK_INGEST_RATE_LIMIT_RPM", "-7")
    assert rl._limit_from_env("WEBHOOK_INGEST_RATE_LIMIT_RPM", 120) == 1
    monkeypatch.setenv("WEBHOOK_INGEST_RATE_LIMIT_RPM", "45")
    assert rl._limit_from_env("WEBHOOK_INGEST_RATE_LIMIT_RPM", 120) == 45


# ---------------------------------------------------------------------------
# 4. Read path: DB failures degrade, and limit is validated.
# ---------------------------------------------------------------------------


def _install_failing_db(monkeypatch, exc):
    from sqlalchemy.exc import SQLAlchemyError  # noqa: F401

    class _BoomSession:
        def execute(self, *_a, **_k):
            raise exc

        def close(self):
            pass

    fake_db = types.ModuleType("shared.database")
    fake_db.SessionLocal = lambda: _BoomSession()
    fake_db.get_db_session = lambda: iter([_BoomSession()])
    monkeypatch.setitem(sys.modules, "shared.database", fake_db)


@pytest.mark.asyncio
async def test_recent_events_db_error_degrades_to_empty(monkeypatch):
    """A failed query degrades to an empty list, like the other except arm.

    Pre-fix: SQLAlchemyError was not caught, so a dashboard read raised
    out of the helper (unhandled 500 from the endpoint).
    """
    from sqlalchemy.exc import SQLAlchemyError

    _install_failing_db(monkeypatch, SQLAlchemyError("connection lost"))
    result = await wr.get_recent_events(TENANT_A, 10)
    assert result == {"tenant_id": TENANT_A, "events": [], "total": 0}


def _build_app(principal):
    app = FastAPI()
    app.include_router(wr.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: principal
    app.dependency_overrides[wr._verify_api_key_present] = lambda: None
    app.dependency_overrides[wr._verify_api_key] = lambda: None
    app.dependency_overrides[require_active_subscription] = lambda: None
    return app


def _principal():
    return IngestionPrincipal(
        key_id="key-scoped",
        scopes=["webhooks.read"],
        tenant_id=TENANT_A,
        auth_mode="test",
    )


def test_chain_verify_db_error_returns_correlated_500(monkeypatch):
    """A DB failure in chain verification returns the correlated 500.

    Pre-fix: SQLAlchemyError escaped the handler, so the response had no
    correlation id for support to join on (raw 500 via TestClient raise).
    """
    from sqlalchemy.exc import SQLAlchemyError

    _install_failing_db(monkeypatch, SQLAlchemyError("connection lost"))

    class _BoomPersistence:
        def __init__(self, _session):
            pass

        def verify_chain(self, _tenant_id):
            raise SQLAlchemyError("connection lost")

    fake_cte = types.ModuleType("shared.cte_persistence")
    fake_cte.CTEPersistence = _BoomPersistence
    monkeypatch.setitem(sys.modules, "shared.cte_persistence", fake_cte)
    monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))

    client = TestClient(_build_app(_principal()))
    resp = client.get(
        "/api/v1/webhooks/chain/verify",
        params={"tenant_id": TENANT_A},
        headers={"X-RegEngine-API-Key": "any"},
    )
    assert resp.status_code == 500
    assert "correlation" in resp.json()["detail"]


def test_recent_limit_validation(monkeypatch):
    """limit=0 / negative is a 422; valid limits still work (capped at 50).

    Pre-fix: limit=0 or negative flowed into ``min(limit, 50)`` and hit
    the database (Postgres rejects negative LIMIT).
    """

    class _Session:
        def execute(self, _stmt, _params=None):
            params = _params or {}

            class _R:
                def fetchall(self):
                    lim = params.get("lim", 10)
                    assert lim >= 1, "negative LIMIT must never reach the query"
                    return []

            return _R()

        def close(self):
            pass

    fake_db = types.ModuleType("shared.database")
    fake_db.SessionLocal = lambda: _Session()
    fake_db.get_db_session = lambda: iter([_Session()])
    monkeypatch.setitem(sys.modules, "shared.database", fake_db)
    monkeypatch.setattr(wr, "consume_tenant_rate_limit", lambda **_kw: (True, 999))

    client = TestClient(_build_app(_principal()))
    headers = {"X-RegEngine-API-Key": "any"}
    assert client.get("/api/v1/webhooks/recent", params={"tenant_id": TENANT_A, "limit": 0}, headers=headers).status_code == 422
    assert client.get("/api/v1/webhooks/recent", params={"tenant_id": TENANT_A, "limit": -5}, headers=headers).status_code == 422
    ok = client.get("/api/v1/webhooks/recent", params={"tenant_id": TENANT_A, "limit": 5}, headers=headers)
    assert ok.status_code == 200, ok.text
    capped = client.get("/api/v1/webhooks/recent", params={"tenant_id": TENANT_A, "limit": 500}, headers=headers)
    assert capped.status_code == 200, capped.text
