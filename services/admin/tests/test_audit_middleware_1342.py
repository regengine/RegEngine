"""Coverage-sweep top-up for ``app.audit_middleware``.

Two slices of the module are exercised here:

* ``_trusted_proxy_cidrs`` line 62 — the ``continue`` branch hit when
  ``AUDIT_TRUSTED_PROXY_CIDRS`` contains an empty token after splitting on
  ``,`` and stripping whitespace (trailing comma, double comma,
  whitespace-only entry). Without this guard the loop would fall through
  to ``ipaddress.ip_network("")`` and log a spurious
  ``audit_trusted_proxy_cidr_invalid`` warning for benign operator input.

* ``AuditContextMiddleware.dispatch`` lines 100-114 — the full request
  wrapper: skip-path fast-path, audit-context attachment on the happy
  path, and the ``_get_client_ip`` proxy-aware IP resolver.

Why this matters: ``audit_middleware`` sits on the critical tamper-evidence
path for the EPIC-K #1414 story — it decides which sockets are allowed to
forge ``actor_ip`` via ``X-Forwarded-For``. Ops teams routinely hand-edit
``AUDIT_TRUSTED_PROXY_CIDRS`` (Railway edge rollout, dev overrides), and
every request that reaches an admin route runs through ``dispatch``, so
both slices must stay exercised.

This file holds pure, no-DB tests that mirror the style of
``tests/test_epic_k_audit_hygiene.py``. Tracks GitHub issue #1342.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

# pytest.importorskip guards against test environments where Starlette
# isn't installed (CI job matrix).
pytest.importorskip("starlette")

from app.audit_middleware import (  # noqa: E402
    AuditContextMiddleware,
    _is_trusted_proxy,
    _should_skip,
    _trusted_proxy_cidrs,
)


# ---------------------------------------------------------------------------
# #1342 — tolerant parsing of AUDIT_TRUSTED_PROXY_CIDRS
# ---------------------------------------------------------------------------


def test_trusted_proxy_cidrs_skips_trailing_empty_token(monkeypatch):
    """A trailing comma produces an empty token after ``.strip()``.

    The loop must ``continue`` (line 62) rather than attempt to parse ``""``
    as a network — otherwise ops typos produce noisy
    ``audit_trusted_proxy_cidr_invalid`` warnings for something benign.
    """
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8,")
    cidrs = _trusted_proxy_cidrs()
    assert len(cidrs) == 1
    assert str(cidrs[0]) == "10.0.0.0/8"


def test_trusted_proxy_cidrs_skips_whitespace_only_token(monkeypatch):
    """A ``,  ,`` run is whitespace after strip — must still ``continue``."""
    monkeypatch.setenv(
        "AUDIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8,   ,172.16.0.0/12",
    )
    cidrs = _trusted_proxy_cidrs()
    # Both real CIDRs parse; the empty middle token is silently skipped.
    assert [str(c) for c in cidrs] == ["10.0.0.0/8", "172.16.0.0/12"]


def test_trusted_proxy_cidrs_warns_on_invalid_cidr_and_continues(monkeypatch):
    """An un-parseable token must hit the ``ValueError`` branch (lines
    65-66) — log a warning and keep processing other entries rather than
    crash the whole middleware on one fat-fingered CIDR."""
    monkeypatch.setenv(
        "AUDIT_TRUSTED_PROXY_CIDRS",
        "10.0.0.0/8,not-a-cidr,172.16.0.0/12",
    )
    cidrs = _trusted_proxy_cidrs()
    # Bad token dropped; valid neighbours survive.
    assert [str(c) for c in cidrs] == ["10.0.0.0/8", "172.16.0.0/12"]


# ---------------------------------------------------------------------------
# #1342 — path-skip and trusted-proxy helper edge cases
# ---------------------------------------------------------------------------


def test_should_skip_covers_docs_subpaths():
    """FastAPI mounts Swagger/Redoc assets at ``/docs/...`` and
    ``/redoc/...`` — the prefix branch (line 42-43) must match those."""
    assert _should_skip("/docs/oauth2-redirect") is True
    assert _should_skip("/redoc/somefile.js") is True
    # Sanity: an audit-bearing admin route must NOT skip.
    assert _should_skip("/admin/users") is False


def test_is_trusted_proxy_returns_false_for_non_ip_client_host(monkeypatch):
    """``client.host`` can legitimately be a UNIX socket path or an
    ASGI-test-client sentinel like ``"testclient"`` that is not a valid
    IP literal. ``ipaddress.ip_address`` raises ``ValueError`` there; the
    except branch (lines 75-76) must swallow it and return False rather
    than 500 the request."""
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    assert _is_trusted_proxy("testclient") is False
    assert _is_trusted_proxy("not-an-ip") is False
    # Also confirm the early-return on empty input stays green.
    assert _is_trusted_proxy(None) is False
    assert _is_trusted_proxy("") is False


# ---------------------------------------------------------------------------
# #1342 — AuditContextMiddleware.dispatch behaviour
# ---------------------------------------------------------------------------


def _make_request(
    *,
    path: str = "/admin/users",
    method: str = "GET",
    client_host: str | None = "203.0.113.7",
    headers: dict[str, str] | None = None,
) -> MagicMock:
    """Build a Starlette-shaped fake request.

    ``BaseHTTPMiddleware.dispatch`` only reads:
      - ``request.url.path`` (skip check + endpoint string)
      - ``request.method`` (endpoint string)
      - ``request.headers.get(...)`` (user-agent, XFF, X-Real-IP)
      - ``request.client.host`` (raw socket peer)
      - ``request.state`` (write target for audit_context)

    A MagicMock with these attrs wired is enough — we do NOT need a real
    Starlette app, ASGI scope, or event loop routing.
    """
    req = MagicMock()
    req.url.path = path
    req.method = method
    req.headers = headers or {}
    if client_host is None:
        req.client = None
    else:
        req.client = MagicMock()
        req.client.host = client_host
    # Fresh namespace object so ``request.state.audit_context = ...`` is a
    # real attribute write we can assert against (MagicMock would accept
    # any attribute silently, which hides bugs).
    req.state = type("_State", (), {})()
    return req


@pytest.mark.asyncio
async def test_dispatch_skips_health_path_without_attaching_context():
    """``/health`` is in _AUDIT_SKIP_PATHS — dispatch must bypass the
    context attach and call straight through (line 102-103)."""
    mw = AuditContextMiddleware(app=MagicMock())
    req = _make_request(path="/health")
    sentinel_response = MagicMock(name="response")

    async def _call_next(r):
        assert r is req
        return sentinel_response

    resp = await mw.dispatch(req, _call_next)

    assert resp is sentinel_response
    # Skip path must NOT attach audit_context.
    assert not hasattr(req.state, "audit_context")


@pytest.mark.asyncio
async def test_dispatch_attaches_audit_context_on_happy_path():
    """Non-skipped path must populate request.state.audit_context with
    request_id, actor_ip, actor_ua, endpoint (lines 105-111)."""
    mw = AuditContextMiddleware(app=MagicMock())
    req = _make_request(
        path="/admin/users",
        method="POST",
        client_host="198.51.100.42",
        headers={"user-agent": "pytest-ua/1.0"},
    )
    sentinel_response = MagicMock(name="response")

    async def _call_next(r):
        # The context must be attached BEFORE call_next runs so downstream
        # route handlers can read it.
        assert hasattr(r.state, "audit_context")
        return sentinel_response

    resp = await mw.dispatch(req, _call_next)

    assert resp is sentinel_response
    ctx = req.state.audit_context
    assert set(ctx.keys()) == {"request_id", "actor_ip", "actor_ua", "endpoint"}
    assert ctx["endpoint"] == "POST /admin/users"
    assert ctx["actor_ua"] == "pytest-ua/1.0"
    # No trusted-proxy env set, so actor_ip == raw client socket host.
    assert ctx["actor_ip"] == "198.51.100.42"
    # request_id is a fresh UUID4 string.
    assert isinstance(ctx["request_id"], str)
    assert len(ctx["request_id"]) == 36


@pytest.mark.asyncio
async def test_dispatch_truncates_long_user_agent():
    """``actor_ua`` slices to 512 chars to bound audit-row width (line 109)."""
    mw = AuditContextMiddleware(app=MagicMock())
    long_ua = "A" * 2000
    req = _make_request(headers={"user-agent": long_ua})

    async def _call_next(r):
        return MagicMock()

    await mw.dispatch(req, _call_next)
    assert len(req.state.audit_context["actor_ua"]) == 512


@pytest.mark.asyncio
async def test_dispatch_honors_xff_when_peer_is_trusted_proxy(monkeypatch):
    """When the socket peer is inside AUDIT_TRUSTED_PROXY_CIDRS, the
    left-most X-Forwarded-For hop becomes actor_ip (lines 128-131)."""
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    mw = AuditContextMiddleware(app=MagicMock())
    req = _make_request(
        client_host="10.1.2.3",  # inside 10.0.0.0/8
        headers={"x-forwarded-for": "203.0.113.9, 10.1.2.3"},
    )

    async def _call_next(r):
        return MagicMock()

    await mw.dispatch(req, _call_next)
    assert req.state.audit_context["actor_ip"] == "203.0.113.9"


@pytest.mark.asyncio
async def test_dispatch_falls_back_to_x_real_ip_when_trusted(monkeypatch):
    """Trusted proxy + no XFF: X-Real-IP becomes actor_ip (lines 132-134)."""
    monkeypatch.setenv("AUDIT_TRUSTED_PROXY_CIDRS", "10.0.0.0/8")
    mw = AuditContextMiddleware(app=MagicMock())
    req = _make_request(
        client_host="10.1.2.3",
        headers={"x-real-ip": "203.0.113.50"},
    )

    async def _call_next(r):
        return MagicMock()

    await mw.dispatch(req, _call_next)
    assert req.state.audit_context["actor_ip"] == "203.0.113.50"


@pytest.mark.asyncio
async def test_dispatch_ignores_xff_from_untrusted_peer(monkeypatch):
    """Untrusted peer: XFF MUST be ignored to prevent actor_ip spoofing.

    This is the #1414 security invariant — attackers on open routes
    cannot forge actor_ip by sending X-Forwarded-For.
    """
    monkeypatch.delenv("AUDIT_TRUSTED_PROXY_CIDRS", raising=False)
    mw = AuditContextMiddleware(app=MagicMock())
    req = _make_request(
        client_host="198.51.100.42",
        headers={"x-forwarded-for": "1.2.3.4"},  # attacker-supplied
    )

    async def _call_next(r):
        return MagicMock()

    await mw.dispatch(req, _call_next)
    # Real peer wins, not XFF.
    assert req.state.audit_context["actor_ip"] == "198.51.100.42"


@pytest.mark.asyncio
async def test_dispatch_handles_missing_client_as_unknown():
    """When ``request.client`` is None (rare, but possible with some
    ASGI transports / tests), actor_ip falls back to ``"unknown"``
    instead of raising (line 125, line 136)."""
    mw = AuditContextMiddleware(app=MagicMock())
    req = _make_request(client_host=None)

    async def _call_next(r):
        return MagicMock()

    await mw.dispatch(req, _call_next)
    assert req.state.audit_context["actor_ip"] == "unknown"
