"""Unit tests for ``app.stripe_billing.helpers`` — issue #1342.

Raises coverage from 90% to 100% by filling in the edge branches the
existing suites leave behind.

The redirect-allowlist happy / reject paths are covered by
``test_stripe_redirect_allowlist.py``; this file targets the
non-redirect helpers plus the small branches that test leaves open.

Pinned behaviors:
  - ``_configure_stripe``: missing STRIPE_SECRET_KEY raises
    HTTPException(500) rather than silently leaving stripe.api_key
    unset (which would surface as a cryptic auth error later).
  - ``_is_host_allowed``: empty hostname is rejected before any
    allowlist check (``urlparse("https:///path").hostname`` returns
    ``""`` for malformed URLs).
  - ``_allowed_redirect_hosts``: empty comma-separated entries and
    un-dotted suffixes are skipped (the latter so
    ``regengine.co`` as a suffix can't match ``evil-regengine.co``).
  - ``_extract_invoice_period_end`` / ``_extract_paid_at``: every
    fallback step of the multi-location Stripe invoice field lookup
    — direct, lines, and final None — plus the "paid_at missing but
    created present" path that keeps an invoice visible when stripe
    strips status_transitions on older event versions.
  - ``_principal_role``: admin short-circuit via ``*`` permission and
    via ``admin`` scope prefix.
  - ``_resolve_tenant_context``: all three fallback tiers (explicit
    kwarg → X-Tenant-Id header → principal.tenant_id) and the
    "nothing matched" HTTPException(400).
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")
pytest.importorskip("stripe")

from fastapi import HTTPException  # noqa: E402

from app.stripe_billing import helpers as mod  # noqa: E402
from app.stripe_billing.helpers import (  # noqa: E402
    _allowed_redirect_hosts,
    _coerce_int,
    _coerce_optional_int,
    _configure_stripe,
    _enforce_admin_or_operator,
    _extract_invoice_period_end,
    _extract_paid_at,
    _format_period_end,
    _is_host_allowed,
    _normalize_scope,
    _principal_role,
    _resolve_tenant_context,
    _stripe_get,
    _validate_redirect_url,
)


# ---------------------------------------------------------------------------
# _configure_stripe
# ---------------------------------------------------------------------------


class TestConfigureStripe:
    def test_missing_secret_key_raises_http_500(self, monkeypatch):
        # Without a secret key we cannot talk to Stripe at all; fail
        # loudly and early rather than deferring to a cryptic auth
        # error from the SDK when the route fires.
        monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
        with pytest.raises(HTTPException) as ei:
            _configure_stripe()
        assert ei.value.status_code == 500
        assert "STRIPE_SECRET_KEY" in ei.value.detail

    def test_secret_key_sets_stripe_api_key(self, monkeypatch):
        # Pin that the env var actually lands on the stripe SDK. The
        # real SDK reads from ``stripe.api_key`` at each request — if
        # this assignment is ever removed, every Stripe call silently
        # becomes anonymous.
        monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_abc123")
        monkeypatch.setattr(mod.stripe, "api_key", None, raising=False)
        _configure_stripe()
        assert mod.stripe.api_key == "sk_test_abc123"


# ---------------------------------------------------------------------------
# _allowed_redirect_hosts — extra suffix parsing
# ---------------------------------------------------------------------------


class TestAllowedRedirectHosts:
    def test_defaults_returned_without_env(self, monkeypatch):
        monkeypatch.delenv("STRIPE_REDIRECT_ALLOWED_HOSTS", raising=False)
        monkeypatch.delenv("STRIPE_REDIRECT_ALLOWED_HOST_SUFFIXES", raising=False)
        exact, suffixes = _allowed_redirect_hosts()
        # The function always returns the compiled-in defaults.
        assert "regengine.co" in exact
        assert ".vercel.app" in suffixes

    def test_extra_exact_hosts_appended(self, monkeypatch):
        monkeypatch.setenv("STRIPE_REDIRECT_ALLOWED_HOSTS", "staging.example.com, ,OTHER.example.com")
        monkeypatch.delenv("STRIPE_REDIRECT_ALLOWED_HOST_SUFFIXES", raising=False)
        exact, _ = _allowed_redirect_hosts()
        # Lowercased and trimmed; empty entries from double-commas
        # skipped (covers the ``if host:`` guard).
        assert "staging.example.com" in exact
        assert "other.example.com" in exact

    def test_undotted_suffixes_are_rejected(self, monkeypatch, caplog):
        # ``regengine.co`` as a suffix (no leading dot) would match
        # ``evil-regengine.co``. The allowlist reader MUST discard any
        # suffix without the dot — validated in the reader rather than
        # the matcher so bad configs fail open at the shortest path.
        monkeypatch.delenv("STRIPE_REDIRECT_ALLOWED_HOSTS", raising=False)
        monkeypatch.setenv(
            "STRIPE_REDIRECT_ALLOWED_HOST_SUFFIXES",
            ".ok.example.com,undotted.bad,  ,.also-ok.example.com",
        )
        _, suffixes = _allowed_redirect_hosts()
        assert ".ok.example.com" in suffixes
        assert ".also-ok.example.com" in suffixes
        # Un-dotted and empty entries skipped.
        assert "undotted.bad" not in suffixes
        assert "" not in suffixes


# ---------------------------------------------------------------------------
# _is_host_allowed — empty-host guard
# ---------------------------------------------------------------------------


class TestIsHostAllowed:
    def test_empty_host_rejected(self):
        # ``urlparse("https:///path").hostname`` returns "" for
        # malformed URLs; _is_host_allowed MUST reject before any
        # allowlist comparison or empty-string membership tests could
        # behave unexpectedly (e.g. ``"" in (".vercel.app",)`` is
        # False by default, but a future refactor could flip that).
        assert _is_host_allowed("") is False

    def test_none_rejected(self):
        # Defensive — same early-return.
        assert _is_host_allowed(None) is False  # type: ignore[arg-type]

    def test_exact_allowlist_hit(self):
        assert _is_host_allowed("regengine.co") is True

    def test_suffix_allowlist_hit(self):
        # ``foo.vercel.app`` ends with ``.vercel.app`` and has chars
        # before the dot.
        assert _is_host_allowed("feature-branch.vercel.app") is True

    def test_suffix_match_requires_prefix_chars(self):
        # ``len(host) > len(suf)`` guard — a host that's *only* the
        # suffix (``.vercel.app``) should be rejected because it's
        # syntactically just the suffix with a leading dot and no
        # actual subdomain.
        assert _is_host_allowed(".vercel.app") is False


# ---------------------------------------------------------------------------
# _validate_redirect_url — urlparse ValueError branch
# ---------------------------------------------------------------------------


class TestValidateRedirectUrlParseError:
    def test_malformed_ipv6_url_raises_http_400_unparseable(self):
        # ``urlparse`` raises ValueError on truly malformed IPv6
        # brackets (the only shape that still trips Python 3.12's
        # otherwise-lenient parser). The helper turns that into a
        # structured 400 so operators can grep the error rather than
        # chasing a raw ValueError stack.
        with pytest.raises(HTTPException) as ei:
            _validate_redirect_url("https://[", field="success_url")
        assert ei.value.status_code == 400
        detail = ei.value.detail
        # Structured body (dict, not a string) so ingest callers can
        # branch on ``error`` field rather than parse English.
        assert isinstance(detail, dict)
        assert detail["error"] == "unparseable_redirect_url"
        assert detail["field"] == "success_url"


# ---------------------------------------------------------------------------
# _format_period_end — Optional[int] → ISO
# ---------------------------------------------------------------------------


class TestFormatPeriodEnd:
    def test_zero_returns_none(self):
        # Stripe uses 0 as "unset" in some event payload shapes.
        assert _format_period_end(0) is None

    def test_none_returns_none(self):
        assert _format_period_end(None) is None

    def test_valid_epoch_formatted_utc(self):
        # 1700000000 = 2023-11-14T22:13:20+00:00 — assert UTC offset.
        result = _format_period_end(1700000000)
        assert result is not None
        assert result.endswith("+00:00")
        assert result.startswith("2023-11-14T")


# ---------------------------------------------------------------------------
# _stripe_get — dict + object dual-access
# ---------------------------------------------------------------------------


class TestStripeGet:
    def test_dict_returns_mapping_value(self):
        assert _stripe_get({"foo": "bar"}, "foo") == "bar"

    def test_dict_default_on_miss(self):
        assert _stripe_get({}, "foo", default="d") == "d"

    def test_object_returns_attribute(self):
        obj = SimpleNamespace(foo="bar")
        assert _stripe_get(obj, "foo") == "bar"

    def test_object_default_on_miss(self):
        obj = SimpleNamespace(other="x")
        assert _stripe_get(obj, "foo", default="d") == "d"


# ---------------------------------------------------------------------------
# _coerce_int / _coerce_optional_int
# ---------------------------------------------------------------------------


class TestCoerceInt:
    @pytest.mark.parametrize("value,expected", [("42", 42), (7, 7), (7.9, 7)])
    def test_valid_returns_int(self, value, expected):
        assert _coerce_int(value) == expected

    def test_invalid_string_returns_default(self):
        assert _coerce_int("NaN", default=-1) == -1

    def test_none_returns_default(self):
        assert _coerce_int(None, default=0) == 0


class TestCoerceOptionalInt:
    def test_valid_positive(self):
        assert _coerce_optional_int("10") == 10

    def test_zero_returns_none(self):
        # The "> 0" guard — zero is semantically "unset" in Stripe
        # event payloads, so normalize to None.
        assert _coerce_optional_int(0) is None
        assert _coerce_optional_int("0") is None

    def test_negative_returns_none(self):
        assert _coerce_optional_int(-1) is None

    def test_invalid_returns_none(self):
        assert _coerce_optional_int("NaN") is None

    def test_none_returns_none(self):
        assert _coerce_optional_int(None) is None


# ---------------------------------------------------------------------------
# _extract_invoice_period_end — multi-location fallback
# ---------------------------------------------------------------------------


class TestExtractInvoicePeriodEnd:
    def test_direct_period_end_preferred(self):
        payload = {"period_end": 1700000000, "lines": {"data": []}}
        result = _extract_invoice_period_end(payload)
        assert result is not None
        assert result.startswith("2023-11-14T")

    def test_falls_back_to_lines_data_period_end(self):
        # No direct period_end — reach into lines.data[].period.end.
        payload = {
            "lines": {
                "data": [
                    {"period": {"end": 1700000000}},
                ]
            }
        }
        result = _extract_invoice_period_end(payload)
        assert result is not None
        assert result.startswith("2023-11-14T")

    def test_non_dict_line_is_skipped(self):
        # ``if not isinstance(line, dict): continue`` — guards against
        # Stripe event shape drift.
        payload = {
            "lines": {
                "data": [
                    "not-a-dict",
                    {"period": {"end": 1700000000}},
                ]
            }
        }
        result = _extract_invoice_period_end(payload)
        assert result is not None

    def test_non_dict_lines_top_level_returns_none(self):
        # lines isn't a dict — short-circuit without iteration.
        payload = {"lines": "unexpected"}
        assert _extract_invoice_period_end(payload) is None

    def test_non_list_lines_data_returns_none(self):
        # lines.data isn't a list either.
        payload = {"lines": {"data": "scrambled"}}
        assert _extract_invoice_period_end(payload) is None

    def test_all_empty_returns_none(self):
        # Neither direct nor lines-embedded — final ``return None``.
        assert _extract_invoice_period_end({}) is None
        assert _extract_invoice_period_end({"lines": {}}) is None
        assert _extract_invoice_period_end({"lines": {"data": []}}) is None

    def test_lines_data_with_empty_period(self):
        # Line exists but period.end is zero — falls through to next
        # line / final None.
        payload = {"lines": {"data": [{"period": {"end": 0}}]}}
        assert _extract_invoice_period_end(payload) is None

    def test_lines_data_with_missing_period_dict(self):
        # ``.get("period") or {}`` — None / missing doesn't raise.
        payload = {"lines": {"data": [{"other": "field"}]}}
        assert _extract_invoice_period_end(payload) is None


# ---------------------------------------------------------------------------
# _extract_paid_at — status_transitions → created fallback
# ---------------------------------------------------------------------------


class TestExtractPaidAt:
    def test_paid_at_preferred(self):
        payload = {
            "status_transitions": {"paid_at": 1700000000},
            "created": 1600000000,
        }
        result = _extract_paid_at(payload)
        assert result is not None
        assert result.startswith("2023-11-14T")

    def test_falls_back_to_created(self):
        # Old Stripe event versions strip status_transitions; ``created``
        # is the invoice-level timestamp that always exists.
        payload = {"created": 1700000000}
        result = _extract_paid_at(payload)
        assert result is not None
        assert result.startswith("2023-11-14T")

    def test_no_timestamps_returns_none(self):
        assert _extract_paid_at({}) is None
        assert _extract_paid_at({"status_transitions": {}}) is None

    def test_status_transitions_non_dict_tolerated(self):
        # ``.get("status_transitions") or {}`` — None / malformed
        # normalizes to empty dict, so we don't AttributeError.
        payload = {"status_transitions": None, "created": 1700000000}
        result = _extract_paid_at(payload)
        assert result is not None


# ---------------------------------------------------------------------------
# _normalize_scope + _principal_role + _enforce_admin_or_operator
# ---------------------------------------------------------------------------


class _Principal:
    """Minimal ``IngestionPrincipal`` stand-in for role/tenant tests."""

    def __init__(self, scopes, tenant_id=None):
        self.scopes = scopes
        self.tenant_id = tenant_id


class TestNormalizeScope:
    def test_colon_to_dot_and_lower(self):
        assert _normalize_scope("Admin:Write") == "admin.write"

    def test_strip_whitespace(self):
        assert _normalize_scope("  scope  ") == "scope"


class TestPrincipalRole:
    def test_wildcard_permission_is_admin(self):
        # The ``has_permission(..., "*")`` branch — a single wildcard
        # scope escalates to admin regardless of anything else.
        principal = _Principal(scopes=["*"])
        assert _principal_role(principal) == "admin"

    def test_admin_prefix_is_admin(self):
        # ``admin``, ``admin.write``, ``admin:override`` all start with
        # ``admin`` after normalize — the ``any(... .startswith('admin'))``
        # branch.
        principal = _Principal(scopes=["admin.export"])
        assert _principal_role(principal) == "admin"

    def test_write_scope_is_operator(self):
        principal = _Principal(scopes=["events.write"])
        assert _principal_role(principal) == "operator"

    @pytest.mark.parametrize("suffix", [".write", ".ingest", ".export", ".verify"])
    def test_all_operator_suffixes_covered(self, suffix):
        principal = _Principal(scopes=[f"events{suffix}"])
        assert _principal_role(principal) == "operator"

    def test_read_only_is_viewer(self):
        principal = _Principal(scopes=["events.read"])
        assert _principal_role(principal) == "viewer"

    def test_empty_scopes_is_viewer(self):
        principal = _Principal(scopes=[])
        assert _principal_role(principal) == "viewer"


class TestEnforceAdminOrOperator:
    def test_viewer_is_rejected(self):
        principal = _Principal(scopes=["events.read"])
        with pytest.raises(HTTPException) as ei:
            _enforce_admin_or_operator(principal, "invoices.read")
        assert ei.value.status_code == 403
        # The required_permission string is echoed in the detail so
        # auditors know exactly which scope the caller was missing.
        assert "invoices.read" in ei.value.detail

    def test_operator_passes(self):
        principal = _Principal(scopes=["events.write"])
        # No raise.
        _enforce_admin_or_operator(principal, "invoices.read")

    def test_admin_passes(self):
        principal = _Principal(scopes=["*"])
        _enforce_admin_or_operator(principal, "invoices.read")


# ---------------------------------------------------------------------------
# _resolve_tenant_context — authenticated principal authority
# ---------------------------------------------------------------------------


class TestResolveTenantContext:
    def test_principal_tenant_wins(self):
        principal = _Principal(scopes=[], tenant_id="from-principal")
        assert (
            _resolve_tenant_context(None, None, principal) == "from-principal"
        )

    def test_header_or_explicit_matching_principal_ok(self):
        principal = _Principal(scopes=[], tenant_id="from-principal")
        assert _resolve_tenant_context("from-principal", None, principal) == "from-principal"
        assert _resolve_tenant_context(None, "from-principal", principal) == "from-principal"

    def test_mismatched_requested_tenant_rejected_for_principal(self):
        principal = _Principal(scopes=[], tenant_id="from-principal")
        with pytest.raises(HTTPException) as ei:
            _resolve_tenant_context("explicit", None, principal)
        assert ei.value.status_code == 403

    def test_legacy_header_used_when_principal_has_no_tenant(self):
        principal = _Principal(scopes=[], tenant_id=None)
        assert _resolve_tenant_context(None, "header", principal) == "header"
        assert _resolve_tenant_context("", "header", principal) == "header"

    def test_whitespace_only_falls_back_to_principal(self):
        principal = _Principal(scopes=[], tenant_id="from-principal")
        assert _resolve_tenant_context("   ", "", principal) == "from-principal"

    def test_conflicting_explicit_and_header_rejected(self):
        with pytest.raises(HTTPException) as ei:
            _resolve_tenant_context("explicit", "header", None)
        assert ei.value.status_code == 400

    def test_no_source_raises_http_400(self):
        with pytest.raises(HTTPException) as ei:
            _resolve_tenant_context(None, None, None)
        assert ei.value.status_code == 400
        assert "Tenant" in ei.value.detail

    def test_none_principal_without_header_or_kwarg_raises(self):
        # Explicitly covers the ``principal.tenant_id if principal else None``
        # short-circuit when principal itself is None.
        with pytest.raises(HTTPException) as ei:
            _resolve_tenant_context("", "", None)
        assert ei.value.status_code == 400

    def test_principal_with_none_tenant_raises(self):
        # Principal exists but has no tenant_id — falls through to the
        # "" catch-all and raises.
        principal = _Principal(scopes=["events.read"], tenant_id=None)
        with pytest.raises(HTTPException):
            _resolve_tenant_context(None, None, principal)
