"""#2807 — ``verify_admin_key`` must compare the admin master key in constant time.

``X-Admin-Key`` authorises the highest-privilege surface in the product: minting
API keys for arbitrary tenants, creating tenants, revoking keys. Python's ``!=``
short-circuits at the first differing byte, so the comparison's duration leaked
how much of a guess was correct. Every other secret comparison in the codebase
already uses ``hmac.compare_digest`` (``shared/api_key_store.py``,
``shared/observability/metrics_auth.py``, ``ingestion/app/authz.py``, …).

Timing itself is not asserted here — a wall-clock assertion would be flaky under
CI load and would prove little at Python's resolution. Instead this module pins
the two things that are checkable: the accept/reject contract is unchanged, and
the module does not compare the master key with a short-circuiting operator.

All key material in this file is synthetic.
"""

from __future__ import annotations

import inspect
import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from services.admin.app import routes as admin_routes

SYNTHETIC_MASTER_KEY = "synthetic-admin-master-key-0123456789abcdef"  # pragma: allowlist secret
CALLER_IP = "203.0.113.7"


def _request(path: str = "/v1/admin/keys", ip: str = CALLER_IP) -> SimpleNamespace:
    """Minimal stand-in for the two Request attributes verify_admin_key reads."""
    return SimpleNamespace(client=SimpleNamespace(host=ip), url=SimpleNamespace(path=path))


@pytest.fixture(autouse=True)
def _synthetic_settings(monkeypatch):
    """Pin a synthetic master key and clear the brute-force counter each test.

    verify_admin_key locks an IP out with a 429 after 5 failures in 60s, and the
    counter is shared (Redis-backed when available), so stale state from an
    earlier test would turn the expected 401s into 429s.
    """
    monkeypatch.setattr(
        admin_routes,
        "get_settings",
        lambda: SimpleNamespace(admin_master_key=SYNTHETIC_MASTER_KEY),
    )
    admin_routes._reset_admin_failures(CALLER_IP)
    yield
    admin_routes._reset_admin_failures(CALLER_IP)


def test_correct_key_is_accepted():
    assert admin_routes.verify_admin_key(_request(), SYNTHETIC_MASTER_KEY) is True


@pytest.mark.parametrize(
    "candidate",
    [
        pytest.param(None, id="absent"),
        pytest.param("", id="empty"),
        pytest.param(SYNTHETIC_MASTER_KEY[:1], id="first-byte-only"),
        pytest.param(SYNTHETIC_MASTER_KEY[:-1], id="all-but-last-byte"),
        pytest.param(SYNTHETIC_MASTER_KEY + "x", id="correct-plus-suffix"),
        pytest.param(SYNTHETIC_MASTER_KEY.upper(), id="wrong-case"),
        pytest.param("x" * len(SYNTHETIC_MASTER_KEY), id="same-length-wrong"),
    ],
)
def test_wrong_key_is_rejected_with_401(candidate):
    with pytest.raises(HTTPException) as excinfo:
        admin_routes.verify_admin_key(_request(), candidate)
    assert excinfo.value.status_code == 401


def test_non_ascii_candidate_does_not_raise_through_the_comparison():
    """``compare_digest`` raises TypeError on non-ASCII ``str`` operands.

    A caller controls this header, so an encode-first comparison is required —
    otherwise a single multi-byte character turns a 401 into a 500.
    """
    with pytest.raises(HTTPException) as excinfo:
        admin_routes.verify_admin_key(_request(), "sünthetic-key")
    assert excinfo.value.status_code == 401


def test_verify_admin_key_uses_a_constant_time_comparison():
    """No short-circuiting ``==``/``!=`` against the master key in this module."""
    source = inspect.getsource(admin_routes.verify_admin_key)
    assert "compare_digest" in source, "verify_admin_key must use hmac.compare_digest"

    module_source = inspect.getsource(admin_routes)
    bare_comparison = re.compile(r"(?:==|!=)\s*(?:settings\.)?admin_master_key|admin_master_key\s*(?:==|!=)")
    offenders = [line.strip() for line in module_source.splitlines() if bare_comparison.search(line)]
    assert not offenders, f"admin_master_key compared with a short-circuiting operator: {offenders}"


def test_empty_key_is_rejected_before_the_digest_comparison():
    """The empty-key guard must stay ahead of compare_digest.

    ``settings.admin_master_key`` is typed ``str`` but can be empty in a
    misconfigured deployment; comparing an empty candidate against an empty
    secret would otherwise succeed.
    """
    import services.admin.app.routes as mod

    mod_settings = SimpleNamespace(admin_master_key="")
    original = mod.get_settings
    mod.get_settings = lambda: mod_settings
    try:
        with pytest.raises(HTTPException) as excinfo:
            mod.verify_admin_key(_request(), "")
        assert excinfo.value.status_code == 401
    finally:
        mod.get_settings = original
