"""Tests for the Postmark inbound-email ingestion webhook.

Covers: HTTP Basic Auth enforcement, tenant resolution from the recipient
address, CSV-attachment parity with the /ingest/csv upload path, and that a
malformed/unrecognized email is quarantined (dead-lettered) rather than
crashing the webhook or silently disappearing.
"""

from __future__ import annotations

import base64

import pytest
from app import inbound_email_rejection_log as rejlog
from app import routes_inbound_email as m
from app.authz import IngestionPrincipal, get_ingestion_principal
from app.csv_templates import parse_csv_rows
from app.webhook_models import EventResult, IngestResponse
from fastapi import FastAPI
from fastapi.testclient import TestClient

VALID_CSV = (
    "cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,"
    "location_name,location_gln,event_time,ship_date\n"
    "shipping,TLC-EMAIL-001,Organic Kale,500,lbs,Sunrise Farm,0614141000012,08:00:00,2026-04-01\n"
)


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _postmark_payload(
    *,
    to: str = "ingest+acme@inbound.regengine.co",
    original_recipient: str | None = None,
    attachments: list[dict] | None = None,
    subject: str = "Weekly shipment data",
) -> dict:
    payload = {
        "From": "shipper@example.com",
        "To": to,
        "Subject": subject,
        "TextBody": "See attached CSV.",
        "Attachments": attachments if attachments is not None else [
            {"Name": "shipment.csv", "Content": _b64(VALID_CSV), "ContentType": "text/csv"}
        ],
    }
    if original_recipient:
        payload["OriginalRecipient"] = original_recipient
    return payload


@pytest.fixture(autouse=True)
def _reset_rejections():
    rejlog.reset_inbound_email_rejections()
    yield
    rejlog.reset_inbound_email_rejections()


@pytest.fixture(autouse=True)
def _configured_credentials(monkeypatch):
    monkeypatch.setenv("POSTMARK_INBOUND_WEBHOOK_USER", "postmark-user")
    monkeypatch.setenv("POSTMARK_INBOUND_WEBHOOK_PASSWORD", "postmark-pass")


def _basic_auth_header(user: str = "postmark-user", password: str = "postmark-pass") -> dict:
    token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    return {"Authorization": f"Basic {token}"}


def _build_app(principal_tenant: str | None = "tenant-acme") -> FastAPI:
    app = FastAPI()
    app.include_router(m.router)
    app.dependency_overrides[get_ingestion_principal] = lambda: IngestionPrincipal(
        key_id="test-key",
        scopes=["*"],
        tenant_id=principal_tenant,
    )
    return app


def _make_ingest_response(accepted: int) -> IngestResponse:
    return IngestResponse(
        accepted=accepted,
        rejected=0,
        total=accepted,
        events=[
            EventResult(
                traceability_lot_code="TLC-EMAIL-001",
                cte_type="shipping",
                status="accepted",
                event_id="evt-1",
                sha256_hash="deadbeef",
            )
        ],
    )


# ---------------------------------------------------------------------------
# Basic Auth
# ---------------------------------------------------------------------------


class TestBasicAuth:
    def test_missing_credentials_rejected(self):
        client = TestClient(_build_app())
        resp = client.post("/api/v1/webhooks/inbound-email", json=_postmark_payload())
        assert resp.status_code == 401

    def test_wrong_credentials_rejected(self):
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email",
            json=_postmark_payload(),
            headers=_basic_auth_header(password="wrong"),
        )
        assert resp.status_code == 401

    def test_malformed_auth_header_rejected(self):
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email",
            json=_postmark_payload(),
            headers={"Authorization": "Basic not-valid-base64!!"},
        )
        assert resp.status_code == 401

    def test_correct_credentials_proceed(self, monkeypatch):
        monkeypatch.setattr(m, "_db_get_tenant_by_inbound_address", lambda addr: "tenant-acme")

        async def _fake_ingest(payload, **_kwargs):
            return _make_ingest_response(accepted=1)

        monkeypatch.setattr(m, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email",
            json=_postmark_payload(),
            headers=_basic_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "accepted"

    def test_missing_configured_credentials_dev_allows_through(self, monkeypatch):
        monkeypatch.delenv("POSTMARK_INBOUND_WEBHOOK_USER", raising=False)
        monkeypatch.delenv("POSTMARK_INBOUND_WEBHOOK_PASSWORD", raising=False)
        monkeypatch.setattr(m, "is_production", lambda: False)
        monkeypatch.setattr(m, "_db_get_tenant_by_inbound_address", lambda addr: "tenant-acme")

        async def _fake_ingest(payload, **_kwargs):
            return _make_ingest_response(accepted=1)

        monkeypatch.setattr(m, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        resp = client.post("/api/v1/webhooks/inbound-email", json=_postmark_payload())
        assert resp.status_code == 200

    def test_missing_configured_credentials_production_fails_closed(self, monkeypatch):
        monkeypatch.delenv("POSTMARK_INBOUND_WEBHOOK_USER", raising=False)
        monkeypatch.delenv("POSTMARK_INBOUND_WEBHOOK_PASSWORD", raising=False)
        monkeypatch.setattr(m, "is_production", lambda: True)

        client = TestClient(_build_app())
        resp = client.post("/api/v1/webhooks/inbound-email", json=_postmark_payload())
        assert resp.status_code == 503


# ---------------------------------------------------------------------------
# Parity with the /ingest/csv upload path
# ---------------------------------------------------------------------------


class TestCsvParity:
    def test_email_attachment_produces_same_events_as_direct_upload(self, monkeypatch):
        """The exact CSV bytes, parsed via the upload route's own function
        (parse_csv_rows) and via the email path, must yield identical events —
        proving the webhook doesn't reimplement/diverge from CSV ingestion."""
        direct_events, direct_errors, direct_warnings = parse_csv_rows(VALID_CSV, fallback_cte=None)

        monkeypatch.setattr(m, "_db_get_tenant_by_inbound_address", lambda addr: "tenant-acme")
        captured: dict = {}

        async def _fake_ingest(payload, **_kwargs):
            captured["payload"] = payload
            return _make_ingest_response(accepted=len(payload.events))

        monkeypatch.setattr(m, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email",
            json=_postmark_payload(),
            headers=_basic_auth_header(),
        )
        assert resp.status_code == 200

        email_events = captured["payload"].events
        assert len(email_events) == len(direct_events) == 1
        assert email_events[0].model_dump() == direct_events[0].model_dump()
        assert captured["payload"].source == "inbound_email"
        assert captured["payload"].tenant_id == "tenant-acme"
        assert not direct_errors
        # Same non-blocking KDE-completeness warning either way — proves the
        # email path runs through the identical validation, not a laxer copy.
        assert direct_warnings == ["Row 2: Missing KDEs for shipping: reference_document, tlc_source_reference"]

    def test_email_attachment_is_retained_as_an_ingestion_run_like_a_direct_upload(self, monkeypatch):
        """The attachment must reach ingest_events with the same SourceFileReceipt
        /ingest/csv builds for a direct upload (#3122): verbatim bytes, SHA-256,
        name, content type, and a record count that covers rows the parser
        rejected, so the run receipt accounts for every row of the file."""
        import hashlib

        csv_with_one_bad_row = (
            VALID_CSV + "shipping,,Organic Kale,500,lbs,Sunrise Farm,0614141000012,08:00:00,2026-04-01\n"
        )
        direct_events, direct_errors, _ = parse_csv_rows(csv_with_one_bad_row, fallback_cte=None)
        assert len(direct_events) == 1 and len(direct_errors) == 1  # the blank lot code is a parser rejection

        monkeypatch.setattr(m, "_db_get_tenant_by_inbound_address", lambda addr: "tenant-acme")
        captured: dict = {}

        async def _fake_ingest(payload, **kwargs):
            captured["kwargs"] = kwargs
            response = _make_ingest_response(accepted=len(payload.events))
            response.ingestion_run_id = "run-email-1"
            return response

        monkeypatch.setattr(m, "ingest_events", _fake_ingest)

        raw = csv_with_one_bad_row.encode("utf-8")
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email",
            json=_postmark_payload(
                attachments=[{"Name": "week-14.csv", "Content": _b64(csv_with_one_bad_row), "ContentType": "text/csv"}]
            ),
            headers=_basic_auth_header(),
        )
        assert resp.status_code == 200, resp.text

        receipt = captured["kwargs"]["source_file"]
        assert receipt.filename == "week-14.csv"
        assert receipt.raw_bytes == raw
        assert receipt.sha256 == hashlib.sha256(raw).hexdigest()
        assert receipt.content_type == "text/csv"
        # The run is attributed to the email-ingest identity, never to the
        # sender address: that stays on the inbound-email audit row.
        assert receipt.initiated_by == "email-ingest"
        assert "shipper@example.com" not in (receipt.initiated_by or "")
        assert receipt.record_count == 2 and receipt.parse_errors == direct_errors

        body = resp.json()
        assert body["status"] == "accepted"
        assert body["ingestion_run_id"] == "run-email-1"
        assert body["accepted"] == 1


# ---------------------------------------------------------------------------
# Tenant resolution
# ---------------------------------------------------------------------------


class TestTenantResolution:
    def test_original_recipient_preferred_over_to(self, monkeypatch):
        seen_addresses: list[str] = []

        def _lookup(addr):
            seen_addresses.append(addr)
            return "tenant-acme"

        monkeypatch.setattr(m, "_db_get_tenant_by_inbound_address", _lookup)

        async def _fake_ingest(payload, **_kwargs):
            return _make_ingest_response(accepted=1)

        monkeypatch.setattr(m, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        payload = _postmark_payload(
            to="Some Alias <alias@forwarding.example.com>",
            original_recipient="ingest+acme@inbound.regengine.co",
        )
        resp = client.post("/api/v1/webhooks/inbound-email", json=payload, headers=_basic_auth_header())
        assert resp.status_code == 200
        assert seen_addresses == ["ingest+acme@inbound.regengine.co"]

    def test_unknown_recipient_quarantined(self, monkeypatch):
        monkeypatch.setattr(m, "_db_get_tenant_by_inbound_address", lambda addr: None)
        ingest_calls: list = []

        async def _fake_ingest(payload, **_kwargs):
            ingest_calls.append(payload)
            return _make_ingest_response(accepted=1)

        monkeypatch.setattr(m, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email",
            json=_postmark_payload(to="nobody@inbound.regengine.co"),
            headers=_basic_auth_header(),
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "quarantined", "reason": "unknown_recipient"}
        assert ingest_calls == []
        rejections = rejlog.list_inbound_email_rejections(rejlog.UNRESOLVED_TENANT_KEY)
        assert len(rejections) == 1
        assert rejections[0]["reason"] == "unknown_recipient"
        assert rejections[0]["recipient"] == "nobody@inbound.regengine.co"

    def test_tenant_lookup_unavailable_propagates_not_quarantined(self, monkeypatch):
        """A DB blip during tenant resolution must not be indistinguishable
        from a genuinely unregistered recipient: it should raise so Postmark
        retries, not silently quarantine (and lose) the email."""

        def _boom(addr):
            raise m.TenantLookupUnavailable("database unavailable")

        monkeypatch.setattr(m, "_db_get_tenant_by_inbound_address", _boom)
        ingest_calls: list = []

        async def _fake_ingest(payload, **_kwargs):
            ingest_calls.append(payload)
            return _make_ingest_response(accepted=1)

        monkeypatch.setattr(m, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        with pytest.raises(m.TenantLookupUnavailable):
            client.post(
                "/api/v1/webhooks/inbound-email",
                json=_postmark_payload(),
                headers=_basic_auth_header(),
            )
        assert rejlog.list_inbound_email_rejections(rejlog.UNRESOLVED_TENANT_KEY) == []
        assert ingest_calls == []


class TestDbGetTenantByInboundAddress:
    """Direct coverage of the lookup helper's unavailable-vs-not-found split."""

    class _FakeSession:
        def __init__(self, row=None, raise_on_execute=None):
            self._row = row
            self._raise = raise_on_execute
            self.rolled_back = False
            self.closed = False

        def execute(self, stmt, params=None):
            if self._raise:
                raise self._raise
            return self

        def fetchone(self):
            return self._row

        def rollback(self):
            self.rolled_back = True

        def close(self):
            self.closed = True

    def test_no_db_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr(m, "get_db_safe", lambda: None)
        with pytest.raises(m.TenantLookupUnavailable):
            m._db_get_tenant_by_inbound_address("nobody@inbound.regengine.co")

    def test_query_exception_raises_unavailable_and_rolls_back(self, monkeypatch):
        session = self._FakeSession(raise_on_execute=RuntimeError("connection reset"))
        monkeypatch.setattr(m, "get_db_safe", lambda: session)
        with pytest.raises(m.TenantLookupUnavailable):
            m._db_get_tenant_by_inbound_address("nobody@inbound.regengine.co")
        assert session.rolled_back is True
        assert session.closed is True

    def test_found_row_returns_tenant_id(self, monkeypatch):
        session = self._FakeSession(row=("tenant-acme",))
        monkeypatch.setattr(m, "get_db_safe", lambda: session)
        assert m._db_get_tenant_by_inbound_address("ingest+acme@inbound.regengine.co") == "tenant-acme"

    def test_no_row_returns_none_not_raises(self, monkeypatch):
        session = self._FakeSession(row=None)
        monkeypatch.setattr(m, "get_db_safe", lambda: session)
        assert m._db_get_tenant_by_inbound_address("nobody@inbound.regengine.co") is None


# ---------------------------------------------------------------------------
# Malformed / unparseable emails never crash and are quarantined
# ---------------------------------------------------------------------------


class TestMalformedEmailQuarantine:
    def _seed_tenant(self, monkeypatch, tenant_id="tenant-acme"):
        monkeypatch.setattr(m, "_db_get_tenant_by_inbound_address", lambda addr: tenant_id)

    def test_invalid_json_body_quarantined(self):
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email",
            content=b"not json at all {{{",
            headers={**_basic_auth_header(), "Content-Type": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "quarantined"
        assert resp.json()["reason"] == "invalid_json"

    def test_missing_recipient_quarantined(self, monkeypatch):
        payload = _postmark_payload()
        payload["To"] = ""
        client = TestClient(_build_app())
        resp = client.post("/api/v1/webhooks/inbound-email", json=payload, headers=_basic_auth_header())
        assert resp.status_code == 200
        assert resp.json()["reason"] == "missing_recipient"

    def test_no_attachment_quarantined(self, monkeypatch):
        self._seed_tenant(monkeypatch)
        ingest_calls: list = []

        async def _fake_ingest(payload, **_kwargs):
            ingest_calls.append(payload)
            return _make_ingest_response(accepted=1)

        monkeypatch.setattr(m, "ingest_events", _fake_ingest)

        client = TestClient(_build_app())
        payload = _postmark_payload(attachments=[])
        resp = client.post("/api/v1/webhooks/inbound-email", json=payload, headers=_basic_auth_header())
        assert resp.status_code == 200
        assert resp.json()["reason"] == "no_csv_attachment"
        assert ingest_calls == []
        rejections = rejlog.list_inbound_email_rejections("tenant-acme")
        assert rejections[0]["reason"] == "no_csv_attachment"

    def test_non_csv_attachment_quarantined(self, monkeypatch):
        self._seed_tenant(monkeypatch)
        client = TestClient(_build_app())
        payload = _postmark_payload(
            attachments=[{"Name": "photo.png", "Content": _b64("binarydata"), "ContentType": "image/png"}]
        )
        resp = client.post("/api/v1/webhooks/inbound-email", json=payload, headers=_basic_auth_header())
        assert resp.status_code == 200
        assert resp.json()["reason"] == "no_csv_attachment"

    def test_corrupted_base64_attachment_quarantined(self, monkeypatch):
        self._seed_tenant(monkeypatch)
        client = TestClient(_build_app())
        payload = _postmark_payload(
            attachments=[{"Name": "shipment.csv", "Content": "not-valid-base64!!!", "ContentType": "text/csv"}]
        )
        resp = client.post("/api/v1/webhooks/inbound-email", json=payload, headers=_basic_auth_header())
        assert resp.status_code == 200
        assert resp.json()["reason"] == "attachment_decode_failed"

    def test_attachment_too_large_quarantined(self, monkeypatch):
        self._seed_tenant(monkeypatch)
        monkeypatch.setattr(m, "MAX_CSV_FILE_SIZE_BYTES", 10)
        client = TestClient(_build_app())
        payload = _postmark_payload()
        resp = client.post("/api/v1/webhooks/inbound-email", json=payload, headers=_basic_auth_header())
        assert resp.status_code == 200
        assert resp.json()["reason"] == "attachment_too_large"

    def test_csv_with_no_valid_rows_quarantined(self, monkeypatch):
        self._seed_tenant(monkeypatch)
        client = TestClient(_build_app())
        empty_csv = "traceability_lot_code,product_description\n"
        payload = _postmark_payload(
            attachments=[{"Name": "empty.csv", "Content": _b64(empty_csv), "ContentType": "text/csv"}]
        )
        resp = client.post("/api/v1/webhooks/inbound-email", json=payload, headers=_basic_auth_header())
        assert resp.status_code == 200
        assert resp.json()["reason"] == "no_valid_rows"

    def test_webhook_never_raises_on_completely_garbage_payload(self):
        """Belt-and-suspenders: any dict shape must 200 or a documented 401,
        never a 500 — a webhook that crashes on bad input triggers endless
        Postmark retries of a payload that will never succeed."""
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email",
            json={"totally": "unexpected", "shape": [1, 2, 3]},
            headers=_basic_auth_header(),
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Transient/infra failures are allowed to raise (so Postmark retries)
# ---------------------------------------------------------------------------


class TestTransientFailuresPropagate:
    def test_ingest_events_exception_is_not_swallowed_into_quarantine(self, monkeypatch):
        monkeypatch.setattr(m, "_db_get_tenant_by_inbound_address", lambda addr: "tenant-acme")

        async def _boom(payload, **_kwargs):
            raise RuntimeError("database unavailable")

        monkeypatch.setattr(m, "ingest_events", _boom)

        client = TestClient(_build_app())
        with pytest.raises(RuntimeError):
            client.post(
                "/api/v1/webhooks/inbound-email",
                json=_postmark_payload(),
                headers=_basic_auth_header(),
            )
        # Not recorded as a quarantine — this is a transient failure Postmark
        # should retry, not a permanent parsing rejection.
        assert rejlog.list_inbound_email_rejections("tenant-acme") == []


# ---------------------------------------------------------------------------
# Address registration + rejection listing (tenant self-service)
# ---------------------------------------------------------------------------


class TestAddressRegistration:
    def test_register_requires_valid_email(self):
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email/addresses",
            json={"inbound_address": "not-an-email"},
        )
        assert resp.status_code == 400

    def test_register_success(self, monkeypatch):
        class _FakeSession:
            def __init__(self):
                self.executed = []
                self.committed = False

            def execute(self, stmt, params=None):
                self.executed.append((str(stmt), dict(params or {})))

            def commit(self):
                self.committed = True

            def rollback(self):
                pass

            def close(self):
                pass

        session = _FakeSession()
        monkeypatch.setattr(m, "get_db_safe", lambda: session)

        client = TestClient(_build_app(principal_tenant="tenant-acme"))
        resp = client.post(
            "/api/v1/webhooks/inbound-email/addresses",
            json={"inbound_address": "ingest+acme@inbound.regengine.co"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "tenant-acme"
        assert body["inbound_address"] == "ingest+acme@inbound.regengine.co"
        assert session.committed is True

    def test_register_no_db_returns_503(self, monkeypatch):
        monkeypatch.setattr(m, "get_db_safe", lambda: None)
        client = TestClient(_build_app())
        resp = client.post(
            "/api/v1/webhooks/inbound-email/addresses",
            json={"inbound_address": "ingest+acme@inbound.regengine.co"},
        )
        assert resp.status_code == 503

    def test_list_rejections_scoped_to_caller_tenant(self):
        rejlog.record_inbound_email_rejection(
            tenant_id="tenant-acme", reason="no_csv_attachment", detail="d"
        )
        rejlog.record_inbound_email_rejection(
            tenant_id="tenant-other", reason="no_csv_attachment", detail="d"
        )
        client = TestClient(_build_app(principal_tenant="tenant-acme"))
        resp = client.get("/api/v1/webhooks/inbound-email/rejections")
        assert resp.status_code == 200
        body = resp.json()
        assert body["tenant_id"] == "tenant-acme"
        assert len(body["rejections"]) == 1


# ---------------------------------------------------------------------------
# Router surface
# ---------------------------------------------------------------------------


class TestRouterSurface:
    def test_prefix(self):
        assert m.router.prefix == "/api/v1/webhooks/inbound-email"

    def test_endpoints_registered(self):
        paths = {route.path for route in m.router.routes}
        assert "/api/v1/webhooks/inbound-email" in paths
        assert "/api/v1/webhooks/inbound-email/addresses" in paths
        assert "/api/v1/webhooks/inbound-email/rejections" in paths
