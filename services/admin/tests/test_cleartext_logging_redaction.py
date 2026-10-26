"""Regression coverage for CodeQL py/clear-text-logging-sensitive-data.

These tests lock in that the secret-related warning paths keep their
operator-useful message (the env var *name* and the action taken) while
never emitting the actual secret material into the logs.

Covers:
* ``auth_crypto.AuthCryptoService._fetch_hmac_secret_from_kms_or_env``
  (alert: services/admin/app/auth_crypto.py:109)
* ``auth.fingerprint_repair.repair_null_email_fingerprints``
  (alert: services/admin/app/auth/fingerprint_repair.py:60)
"""

from __future__ import annotations

import logging

import pytest

from services.admin.app import auth_crypto
from services.admin.app.auth import fingerprint_repair


def test_ephemeral_secret_warning_names_env_without_leaking_secret(monkeypatch, caplog):
    # Force the dev-ephemeral branch: no env secret, non-production.
    monkeypatch.delenv("AUTH_OTP_HMAC_SECRET", raising=False)
    monkeypatch.setenv("REGENGINE_ENV", "development")
    monkeypatch.setattr(auth_crypto, "_DEV_EPHEMERAL_HMAC_SECRET", None, raising=False)

    with caplog.at_level(logging.WARNING, logger="auth_crypto"):
        secret = auth_crypto.AuthCryptoService._fetch_hmac_secret_from_kms_or_env()

    assert secret  # a usable ephemeral secret is still produced
    records = [r for r in caplog.records if r.name == "auth_crypto"]
    assert len(records) == 1
    message = records[0].getMessage()
    # Useful: names the missing env var and the fallback action.
    assert "AUTH_OTP_HMAC_SECRET" in message
    assert "ephemeral" in message
    # Safe: the actual secret value never reaches the log record.
    assert secret not in message
    assert records[0].args in (None, ())


def test_fingerprint_repair_warning_names_env_without_leaking_secret(monkeypatch, caplog):
    # Non-production + unset secret => warn-and-skip path (returns 0).
    for var in ("REGENGINE_ENV", "ENV", "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("AUTH_OTP_HMAC_SECRET", raising=False)

    with caplog.at_level(logging.WARNING, logger="auth.fingerprint_repair"):
        updated = fingerprint_repair.repair_null_email_fingerprints()

    assert updated == 0
    records = [r for r in caplog.records if r.name == "auth.fingerprint_repair"]
    assert len(records) == 1
    message = records[0].getMessage()
    assert "AUTH_OTP_HMAC_SECRET" in message
    assert "email_fingerprint" in message
    # No secret-shaped positional args were passed to the logger.
    assert records[0].args in (None, ())
