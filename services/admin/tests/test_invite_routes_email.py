"""Unit tests for invite email delivery helpers."""

import sys
from pathlib import Path

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

from app import invite_routes


class _DummyEmails:
    last_payload = None

    @staticmethod
    def send(payload):
        _DummyEmails.last_payload = payload
        return {"id": "email_123"}


class _DummyResend:
    api_key = None
    Emails = _DummyEmails


def test_build_invite_link_uses_configured_base_url(monkeypatch):
    monkeypatch.setenv("INVITE_BASE_URL", "https://app.regengine.test")
    relative, absolute = invite_routes._build_invite_link("abc123")

    assert relative == "/accept-invite?token=abc123"
    assert absolute == "https://app.regengine.test/accept-invite?token=abc123"


def test_send_invite_email_uses_resend_when_key_configured(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_FROM_EMAIL", "onboarding@regengine.test")
    monkeypatch.setitem(sys.modules, "resend", _DummyResend)

    invite_routes._send_invite_email("buyer@example.com", "https://regengine.co/accept-invite?token=t")

    assert _DummyResend.api_key == "re_test_key"
    assert _DummyEmails.last_payload is not None
    assert _DummyEmails.last_payload["to"] == "buyer@example.com"
    assert _DummyEmails.last_payload["from"] == "onboarding@regengine.test"
    assert "Accept Invite" in _DummyEmails.last_payload["html"]


def test_send_invite_email_noop_without_api_key(monkeypatch):
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    invite_routes._send_invite_email("buyer@example.com", "https://regengine.co/accept-invite?token=t")
