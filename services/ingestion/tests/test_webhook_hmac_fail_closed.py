"""Fail-closed webhook HMAC gate: production without WEBHOOK_HMAC_SECRET rejects.

Covers the audit finding: the ingest webhook HMAC check was skipped whenever
WEBHOOK_HMAC_SECRET was unset, including in production. The migration ramp
(skip with a WARN log plus a Prometheus counter increment) is kept for
non-production, but production now fails closed.

Cases:
- production + secret unset -> HTTP 401, counter incremented, error logged.
- non-production + secret unset -> allowed (None), WARN logged, counter up.
- secret set + valid signature -> allowed in any environment.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

pytest.importorskip("fastapi")

import app.webhook_router_v2 as wr  # noqa: E402


class _FakeRequest:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


def _sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


class TestProductionWithoutSecretRejects:
    def setup_method(self):
        wr._last_hmac_skip_warn_at = 0.0

    def test_production_unset_secret_raises_401(self, monkeypatch):
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        monkeypatch.setattr(wr, "_is_production", lambda: True)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                wr._verify_webhook_signature(
                    request=_FakeRequest(b'{"events":[]}'),
                    x_webhook_signature=None,
                )
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == {"error": "webhook_hmac_not_configured"}

    def test_production_reject_logs_error(self, monkeypatch):
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        monkeypatch.setattr(wr, "_is_production", lambda: True)
        calls = []

        def _spy(*args, **kwargs):
            calls.append((args, kwargs))

        monkeypatch.setattr(wr.logger, "error", _spy)
        with pytest.raises(HTTPException):
            asyncio.run(
                wr._verify_webhook_signature(
                    request=_FakeRequest(b"{}"),
                    x_webhook_signature=None,
                )
            )
        assert any(
            args and "webhook_hmac_secret_missing_in_production" in str(args[0])
            for args, kwargs in calls
        ), "expected an error log line naming the missing production secret"

    def test_production_reject_increments_reject_counter_not_skip_counter(
        self, monkeypatch
    ):
        # #3229 follow-up: the closed-gate 401 must not feed the
        # fail-open skip counter, or alarms on skipped verifications
        # count rejected requests as accepted unsigned traffic.
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        monkeypatch.setattr(wr, "_is_production", lambda: True)
        if wr.WEBHOOK_HMAC_REJECTED is None or wr.WEBHOOK_HMAC_SKIPPED is None:
            pytest.skip("prometheus_client not available in this env")
        rejected = wr.WEBHOOK_HMAC_REJECTED.labels(reason="secret_unset")
        skipped = wr.WEBHOOK_HMAC_SKIPPED.labels(reason="secret_unset")
        rejected_before = rejected._value.get()
        skipped_before = skipped._value.get()
        with pytest.raises(HTTPException):
            asyncio.run(
                wr._verify_webhook_signature(
                    request=_FakeRequest(b"{}"),
                    x_webhook_signature=None,
                )
            )
        assert rejected._value.get() >= rejected_before + 1
        assert skipped._value.get() == skipped_before


class TestNonProductionRampPreserved:
    def setup_method(self):
        wr._last_hmac_skip_warn_at = 0.0

    def _clear_strict_triggers(self, monkeypatch):
        from shared.env import CLOUD_ENV_VARS

        for var in CLOUD_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("REGENGINE_AUTH_STRICT", raising=False)
        monkeypatch.setenv("REGENGINE_ENV", "test")

    def test_dev_unset_secret_allows_with_warning(self, monkeypatch):
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        monkeypatch.setattr(wr, "_is_production", lambda: False)
        self._clear_strict_triggers(monkeypatch)
        calls = []

        def _spy(*args, **kwargs):
            calls.append((args, kwargs))

        monkeypatch.setattr(wr.logger, "warning", _spy)
        result = asyncio.run(
            wr._verify_webhook_signature(
                request=_FakeRequest(b'{"events":[]}'),
                x_webhook_signature=None,
            )
        )
        assert result is None
        assert any(
            args and "webhook_hmac_verification_skipped" in str(args[0])
            for args, kwargs in calls
        ), "expected a rate-limited WARN log on the non-production skip path"

    def test_dev_skip_increments_counter(self, monkeypatch):
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        monkeypatch.setattr(wr, "_is_production", lambda: False)
        self._clear_strict_triggers(monkeypatch)
        if wr.WEBHOOK_HMAC_SKIPPED is None:
            pytest.skip("prometheus_client not available in this env")
        labelled = wr.WEBHOOK_HMAC_SKIPPED.labels(reason="secret_unset")
        before = labelled._value.get()
        asyncio.run(
            wr._verify_webhook_signature(
                request=_FakeRequest(b"{}"),
                x_webhook_signature=None,
            )
        )
        assert labelled._value.get() >= before + 1


class TestValidHmacAccepted:
    @pytest.mark.parametrize("production", [False, True])
    def test_valid_signature_passes(self, monkeypatch, production):
        secret = "test-webhook-secret"
        monkeypatch.setenv("WEBHOOK_HMAC_SECRET", secret)
        monkeypatch.setattr(wr, "_is_production", lambda: production)
        body = b'{"events":[]}'
        result = asyncio.run(
            wr._verify_webhook_signature(
                request=_FakeRequest(body),
                x_webhook_signature=_sign(secret, body),
            )
        )
        assert result is None


class TestClosedGateUsesRealEnvironmentPredicate:
    """These tests do NOT stub ``wr._is_production``: they drive the real
    ``shared.env`` helpers so a staging-shaped environment cannot stay
    fail-open while the stubbed tests stay green."""

    def setup_method(self):
        wr._last_hmac_skip_warn_at = 0.0

    def _clear_cloud_markers(self, monkeypatch):
        from shared.env import CLOUD_ENV_VARS

        for var in CLOUD_ENV_VARS:
            monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv("REGENGINE_AUTH_STRICT", raising=False)
        monkeypatch.delenv("ENV", raising=False)

    def test_staging_cloud_deploy_rejects_without_secret(self, monkeypatch):
        # This repo writes REGENGINE_ENV=staging for Railway staging
        # (scripts/railway/bootstrap_staging_database.py). A cloud
        # staging deploy with no secret must fail closed, not accept
        # unsigned compliance events.
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        monkeypatch.setenv("REGENGINE_ENV", "staging")
        monkeypatch.setenv("RAILWAY_ENVIRONMENT_NAME", "staging")
        monkeypatch.delenv("ENV", raising=False)
        monkeypatch.delenv("REGENGINE_AUTH_STRICT", raising=False)
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                wr._verify_webhook_signature(
                    request=_FakeRequest(b'{"events":[]}'),
                    x_webhook_signature=None,
                )
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == {"error": "webhook_hmac_not_configured"}

    def test_local_development_without_secret_still_skips(self, monkeypatch):
        # The unsigned ramp survives only for local names with no cloud
        # marker and no strict flag.
        self._clear_cloud_markers(monkeypatch)
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        monkeypatch.setenv("REGENGINE_ENV", "development")
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost:5432/regengine")
        result = asyncio.run(
            wr._verify_webhook_signature(
                request=_FakeRequest(b'{"events":[]}'),
                x_webhook_signature=None,
            )
        )
        assert result is None

    def test_explicit_production_without_secret_rejects(self, monkeypatch):
        self._clear_cloud_markers(monkeypatch)
        monkeypatch.delenv("WEBHOOK_HMAC_SECRET", raising=False)
        monkeypatch.setenv("REGENGINE_ENV", "production")
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                wr._verify_webhook_signature(
                    request=_FakeRequest(b"{}"),
                    x_webhook_signature=None,
                )
            )
        assert exc_info.value.status_code == 401
        assert exc_info.value.detail == {"error": "webhook_hmac_not_configured"}
