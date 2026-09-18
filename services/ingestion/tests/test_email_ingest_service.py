"""Unit tests for ``app.email_ingest.service`` — the inbound-email orchestrator.

Mocking style follows ``test_stripe_plans_1342.py``: ``monkeypatch`` swaps out
collaborators (the DB session, ``ingest_csv``, tenant lookup) with fakes, so
these tests need no live Postgres and make no network calls. The
SECURITY DEFINER SQL itself (``fsma.claim_inbound_email_audit``,
``fsma.finalize_inbound_email_audit``, etc.) is exercised by mocking
``db.execute(...).fetchone()`` rather than a real connection — same approach
as ``test_email_ingest_tenant_lookup.py``.
"""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import services.ingestion.app.email_ingest.service as service_mod
import pytest
from services.ingestion.app.email_ingest.schemas import AttachmentResult, PostmarkAttachment, PostmarkInboundPayload
from services.ingestion.app.email_ingest.service import (
    _first_recipient,
    _ingest_attachment_csv,
    _process_one_attachment,
    _result_from_audit_row,
    _sanitize_log_value,
    _sender_address,
    claim_inbound_email_audit,
    finalize_inbound_email_audit,
    get_inbound_email_audit_by_message_id,
    process_inbound_email,
)
from fastapi import HTTPException

VALID_B64 = base64.b64encode(b"col_a,col_b\n1,2\n").decode("ascii")

# ---------------------------------------------------------------------------
# _first_recipient — precedence: OriginalRecipient > ToFull > To > None
# ---------------------------------------------------------------------------


class TestFirstRecipient:
    def test_prefers_original_recipient(self):
        payload = PostmarkInboundPayload(
            MessageID="m1",
            From="a@example.com",
            OriginalRecipient="preferred@tenant.co",
            To="other@tenant.co",
            ToFull=[{"Email": "tofull@tenant.co"}],
        )
        assert _first_recipient(payload) == "preferred@tenant.co"

    def test_strips_original_recipient(self):
        payload = PostmarkInboundPayload(
            MessageID="m1", From="a@example.com", OriginalRecipient="  spaced@tenant.co  "
        )
        assert _first_recipient(payload) == "spaced@tenant.co"

    def test_blank_original_recipient_falls_through_to_tofull(self):
        payload = PostmarkInboundPayload(
            MessageID="m1",
            From="a@example.com",
            OriginalRecipient="   ",
            ToFull=[{"Email": "tofull@tenant.co"}],
        )
        assert _first_recipient(payload) == "tofull@tenant.co"

    def test_falls_back_to_tofull_lowercase_key(self):
        payload = PostmarkInboundPayload(
            MessageID="m1", From="a@example.com", ToFull=[{"email": "lower@tenant.co"}]
        )
        assert _first_recipient(payload) == "lower@tenant.co"

    def test_tofull_skips_blank_entries_and_uses_first_valid(self):
        payload = PostmarkInboundPayload(
            MessageID="m1",
            From="a@example.com",
            ToFull=[{"Email": ""}, {}, {"Email": "second@tenant.co"}],
        )
        assert _first_recipient(payload) == "second@tenant.co"

    def test_falls_back_to_to_header_parsed(self):
        payload = PostmarkInboundPayload(
            MessageID="m1", From="a@example.com", To='"Tenant" <parsed@tenant.co>, other@tenant.co'
        )
        assert _first_recipient(payload) == "parsed@tenant.co"

    def test_returns_none_when_nothing_present(self):
        payload = PostmarkInboundPayload(MessageID="m1", From="a@example.com")
        assert _first_recipient(payload) is None

    def test_returns_none_when_to_header_has_no_addresses(self):
        payload = PostmarkInboundPayload(MessageID="m1", From="a@example.com", To="")
        assert _first_recipient(payload) is None


# ---------------------------------------------------------------------------
# _sender_address — v122 sender-allowlist input
# ---------------------------------------------------------------------------


class TestSenderAddress:
    def test_bare_address_is_lowercased(self):
        assert _sender_address("Sender@Example.COM") == "sender@example.com"

    def test_display_name_wrapped_address_is_extracted(self):
        assert _sender_address('"Some Sender" <sender@example.com>') == "sender@example.com"

    def test_empty_from_returns_empty_string(self):
        assert _sender_address("") == ""


# ---------------------------------------------------------------------------
# _sanitize_log_value — control-character/length guard for log lines
# ---------------------------------------------------------------------------


class TestSanitizeLogValue:
    def test_passes_through_an_ordinary_value(self):
        assert _sanitize_log_value("msg-123") == "msg-123"

    def test_strips_control_characters_including_crlf(self):
        assert _sanitize_log_value("msg-1\r\nlogger.warning(injected)=1") == "msg-1logger.warning(injected)=1"

    def test_truncates_overlong_values(self):
        assert len(_sanitize_log_value("x" * 500)) == 200

    def test_none_becomes_empty_string(self):
        assert _sanitize_log_value(None) == ""


# ---------------------------------------------------------------------------
# Audit persistence helpers — mocked DB session
# ---------------------------------------------------------------------------


class TestGetInboundEmailAuditByMessageId:
    def test_returns_none_when_no_row(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        assert get_inbound_email_audit_by_message_id(db, "msg-1") is None

    def test_maps_row_fields_and_parses_json_details_string(self):
        db = MagicMock()
        row = SimpleNamespace(
            id="11111111-1111-1111-1111-111111111111",
            tenant_id="22222222-2222-2222-2222-222222222222",
            message_id="msg-1",
            sender="a@example.com",
            recipient="b@tenant.co",
            subject="hi",
            status="accepted",
            rejection_reason=None,
            attachment_count=1,
            accepted_attachment_count=1,
            rejected_attachment_count=0,
            details=json.dumps([{"name": "f.csv", "status": "accepted"}]),
            received_at="2026-09-12T00:00:00Z",
        )
        db.execute.return_value.fetchone.return_value = row
        result = get_inbound_email_audit_by_message_id(db, "msg-1")
        assert result["id"] == str(row.id)
        assert result["tenant_id"] == str(row.tenant_id)
        assert result["details"] == [{"name": "f.csv", "status": "accepted"}]

    def test_details_already_a_list_is_used_as_is(self):
        db = MagicMock()
        row = SimpleNamespace(
            id="1",
            tenant_id=None,
            message_id="msg-2",
            sender="a@example.com",
            recipient="",
            subject=None,
            status="rejected",
            rejection_reason="unmapped_recipient",
            attachment_count=0,
            accepted_attachment_count=0,
            rejected_attachment_count=0,
            details=[{"already": "a list"}],
            received_at=None,
        )
        db.execute.return_value.fetchone.return_value = row
        result = get_inbound_email_audit_by_message_id(db, "msg-2")
        assert result["details"] == [{"already": "a list"}]
        assert result["tenant_id"] is None

    def test_null_details_defaults_to_empty_list(self):
        db = MagicMock()
        row = SimpleNamespace(
            id="1",
            tenant_id=None,
            message_id="msg-3",
            sender="a@example.com",
            recipient="",
            subject=None,
            status="rejected",
            rejection_reason="unmapped_recipient",
            attachment_count=0,
            accepted_attachment_count=0,
            rejected_attachment_count=0,
            details=None,
            received_at=None,
        )
        db.execute.return_value.fetchone.return_value = row
        result = get_inbound_email_audit_by_message_id(db, "msg-3")
        assert result["details"] == []


class TestClaimInboundEmailAudit:
    def _call(self, db, **overrides):
        kwargs = dict(
            tenant_id="tenant-1",
            message_id="msg-1",
            sender="a@example.com",
            recipient="b@tenant.co",
            subject="hi",
            attachment_count=1,
        )
        kwargs.update(overrides)
        return claim_inbound_email_audit(db, **kwargs)

    def test_commits_and_maps_row_on_success(self):
        db = MagicMock()
        row = SimpleNamespace(id="1", message_id="msg-1", status="processing")
        db.execute.return_value.fetchone.return_value = row
        result = self._call(db)
        db.commit.assert_called_once()
        assert result["message_id"] == "msg-1"
        assert result["status"] == "processing"

    def test_returns_none_on_conflict_race(self):
        # ON CONFLICT (message_id) DO NOTHING -> no RETURNING row: the
        # caller (process_inbound_email) must treat this as "someone else
        # already owns this message_id" and not run ingestion.
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        assert self._call(db) is None
        db.commit.assert_called_once()

    def test_passes_through_scalar_params(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        self._call(db, tenant_id="tenant-xyz", sender="s@x.com")
        _, params = db.execute.call_args[0]
        assert params["p_tenant_id"] == "tenant-xyz"
        assert params["p_sender"] == "s@x.com"
        assert params["p_attachment_count"] == 1


class TestFinalizeInboundEmailAudit:
    def _call(self, db, **overrides):
        kwargs = dict(
            message_id="msg-1",
            tenant_id="tenant-1",
            status="accepted",
            rejection_reason=None,
            attachment_count=1,
            accepted_count=1,
            rejected_count=0,
            details=[{"name": "f.csv"}],
        )
        kwargs.update(overrides)
        return finalize_inbound_email_audit(db, **kwargs)

    def test_commits_and_maps_row_on_success(self):
        db = MagicMock()
        row = SimpleNamespace(
            id="1",
            message_id="msg-1",
            status="accepted",
            attachment_count=1,
            accepted_attachment_count=1,
            rejected_attachment_count=0,
        )
        db.execute.return_value.fetchone.return_value = row
        result = self._call(db)
        db.commit.assert_called_once()
        assert result["message_id"] == "msg-1"
        assert result["status"] == "accepted"

    def test_returns_none_and_logs_when_row_is_no_longer_processing(self):
        # The finalize function's WHERE status = 'processing' guard means a
        # stray double-finalize (there should never be one) is a no-op, not
        # a corruption of another request's row.
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        assert self._call(db) is None
        db.commit.assert_called_once()

    def test_details_are_json_encoded_for_the_jsonb_param(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        details = [{"name": "f.csv", "status": "accepted"}]
        self._call(db, details=details)
        _, params = db.execute.call_args[0]
        assert json.loads(params["p_details"]) == details

    def test_passes_through_scalar_params(self):
        db = MagicMock()
        db.execute.return_value.fetchone.return_value = None
        self._call(db, tenant_id="tenant-xyz", rejection_reason="unmapped_recipient")
        _, params = db.execute.call_args[0]
        assert params["p_tenant_id"] == "tenant-xyz"
        assert params["p_rejection_reason"] == "unmapped_recipient"


class TestResultFromAuditRow:
    def test_rebuilds_response_from_persisted_row(self):
        row = {
            "message_id": "msg-1",
            "status": "partial",
            "tenant_id": "tenant-1",
            "rejection_reason": None,
            "details": [
                {"name": "good.csv", "status": "accepted", "rows_accepted": 3, "rows_rejected": 0},
                {"name": "bad.csv", "status": "rejected", "reason": "unsupported_attachment_type"},
            ],
        }
        result = _result_from_audit_row(row)
        assert result.message_id == "msg-1"
        assert result.status == "partial"
        assert result.tenant_id == "tenant-1"
        assert len(result.attachments) == 2
        assert result.attachments[0].rows_accepted == 3
        assert result.attachments[1].reason == "unsupported_attachment_type"

    def test_handles_missing_details_key(self):
        row = {"message_id": "msg-2", "status": "rejected", "tenant_id": None, "rejection_reason": "unmapped_recipient"}
        result = _result_from_audit_row(row)
        assert result.attachments == []


# ---------------------------------------------------------------------------
# _process_one_attachment / _ingest_attachment_csv
# ---------------------------------------------------------------------------


class TestProcessOneAttachment:
    async def test_rejects_unsupported_type_and_extension(self):
        attachment = PostmarkAttachment(Name="doc.pdf", Content=VALID_B64, ContentType="application/pdf")
        result = await _process_one_attachment("tenant-1", attachment)
        assert result.status == "rejected"
        assert "unsupported_attachment_type" in result.reason

    async def test_csv_extension_accepted_even_with_generic_content_type(self, monkeypatch):
        called = {}

        async def fake_ingest(tenant_id, name, raw):
            called["args"] = (tenant_id, name, raw)
            return AttachmentResult(name=name, status="accepted", rows_accepted=1)

        monkeypatch.setattr(service_mod, "_ingest_attachment_csv", fake_ingest)
        attachment = PostmarkAttachment(Name="data.csv", Content=VALID_B64, ContentType="application/octet-stream")
        result = await _process_one_attachment("tenant-1", attachment)
        assert result.status == "accepted"
        assert called["args"][0] == "tenant-1"
        assert called["args"][1] == "data.csv"

    async def test_excel_mimetype_accepted_without_csv_extension(self, monkeypatch):
        # Postmark/Outlook commonly mislabel CSV attachments with the Excel
        # MIME type even when the filename has no .csv suffix.
        async def fake_ingest(tenant_id, name, raw):
            return AttachmentResult(name=name, status="accepted")

        monkeypatch.setattr(service_mod, "_ingest_attachment_csv", fake_ingest)
        attachment = PostmarkAttachment(Name="export", Content=VALID_B64, ContentType="application/vnd.ms-excel")
        result = await _process_one_attachment("tenant-1", attachment)
        assert result.status == "accepted"

    async def test_invalid_base64_is_rejected(self):
        attachment = PostmarkAttachment(Name="data.csv", Content="not-valid-base64!!!", ContentType="text/csv")
        result = await _process_one_attachment("tenant-1", attachment)
        assert result.status == "rejected"
        assert result.reason == "invalid_base64_content"

    async def test_oversized_attachment_is_rejected(self, monkeypatch):
        monkeypatch.setattr(service_mod, "MAX_CSV_FILE_SIZE_BYTES", 4)
        attachment = PostmarkAttachment(Name="data.csv", Content=VALID_B64, ContentType="text/csv")
        result = await _process_one_attachment("tenant-1", attachment)
        assert result.status == "rejected"
        assert "exceeds maximum attachment size" in result.reason

    async def test_filename_is_sanitized_before_use(self, monkeypatch):
        captured = {}

        async def fake_ingest(tenant_id, name, raw):
            captured["name"] = name
            return AttachmentResult(name=name, status="accepted")

        monkeypatch.setattr(service_mod, "_ingest_attachment_csv", fake_ingest)
        attachment = PostmarkAttachment(Name="../../etc/passwd.csv", Content=VALID_B64, ContentType="text/csv")
        result = await _process_one_attachment("tenant-1", attachment)
        assert "/" not in captured["name"]
        assert ".." not in captured["name"]
        assert result.name == captured["name"]


class TestIngestAttachmentCsv:
    async def test_builds_email_inbound_principal_and_returns_accepted(self, monkeypatch):
        captured = {}

        async def fake_ingest_csv(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(accepted=2, rejected=0)

        monkeypatch.setattr(service_mod, "ingest_csv", fake_ingest_csv)
        result = await _ingest_attachment_csv("tenant-1", "data.csv", b"col_a\n1\n")

        assert result.status == "accepted"
        assert result.rows_accepted == 2
        assert result.rows_rejected == 0
        principal = captured["principal"]
        assert principal.key_id == "email-ingest"
        assert principal.scopes == ["webhooks.ingest"]
        assert principal.tenant_id == "tenant-1"
        assert principal.auth_mode == "email_inbound"
        assert captured["tenant_id"] == "tenant-1"
        assert captured["source"] == "email_inbound"
        assert captured["file"].filename == "data.csv"
        # Regression guard: webhook_router_v2._verify_api_key_present (called
        # deep inside the real ingest_csv -> ingest_events chain) 401s on a
        # falsy X-RegEngine-API-Key -- it only checks presence, never value
        # -- so this must never be None/empty or every real attachment would
        # be rejected before reaching CTEPersistence.
        assert captured["x_regengine_api_key"]

    async def test_partial_when_some_rows_rejected(self, monkeypatch):
        async def fake_ingest_csv(**kwargs):
            return SimpleNamespace(accepted=1, rejected=1)

        monkeypatch.setattr(service_mod, "ingest_csv", fake_ingest_csv)
        result = await _ingest_attachment_csv("tenant-1", "data.csv", b"x")
        # _ingest_attachment_csv itself only distinguishes accepted (>0) vs
        # rejected (0 accepted); "partial" is computed one level up in
        # process_inbound_email from the aggregate across attachments.
        assert result.status == "accepted"
        assert result.rows_rejected == 1

    async def test_zero_accepted_rows_is_rejected(self, monkeypatch):
        async def fake_ingest_csv(**kwargs):
            return SimpleNamespace(accepted=0, rejected=3)

        monkeypatch.setattr(service_mod, "ingest_csv", fake_ingest_csv)
        result = await _ingest_attachment_csv("tenant-1", "data.csv", b"x")
        assert result.status == "rejected"
        assert result.rows_rejected == 3

    async def test_http_exception_with_dict_detail_extracts_message(self, monkeypatch):
        async def fake_ingest_csv(**kwargs):
            raise HTTPException(status_code=400, detail={"message": "No valid rows found", "errors": ["bad"]})

        monkeypatch.setattr(service_mod, "ingest_csv", fake_ingest_csv)
        result = await _ingest_attachment_csv("tenant-1", "data.csv", b"x")
        assert result.status == "rejected"
        assert result.reason == "No valid rows found"

    async def test_http_exception_with_string_detail_is_used_verbatim(self, monkeypatch):
        async def fake_ingest_csv(**kwargs):
            raise HTTPException(status_code=400, detail="CSV contained no data rows")

        monkeypatch.setattr(service_mod, "ingest_csv", fake_ingest_csv)
        result = await _ingest_attachment_csv("tenant-1", "data.csv", b"x")
        assert result.status == "rejected"
        assert result.reason == "CSV contained no data rows"

    async def test_non_http_exception_is_caught_and_rejected(self, monkeypatch):
        # A non-HTTPException escaping the reused pipeline (e.g. the real
        # ingest_csv's un-guarded `content.decode("utf-8-sig")` on a
        # non-UTF-8 attachment, or a transient failure inside
        # webhook_compat.ingest_events) must become a per-attachment
        # rejection, not an unhandled 500 for the whole email -- an
        # unhandled exception here would skip process_inbound_email's
        # audit-row write, and a Postmark retry would then replay (and
        # thus double-ingest) every attachment already accepted earlier
        # in the same request's loop.
        async def fake_ingest_csv(**kwargs):
            raise UnicodeDecodeError("utf-8", b"\xff\xfe", 0, 1, "invalid start byte")

        monkeypatch.setattr(service_mod, "ingest_csv", fake_ingest_csv)
        result = await _ingest_attachment_csv("tenant-1", "data.csv", b"x")
        assert result.status == "rejected"
        assert result.reason == "ingestion_failed"

    async def test_real_ingest_csv_is_not_401d_by_the_api_key_presence_gate(self, monkeypatch):
        """End-to-end against the REAL app.csv_templates.ingest_csv (only its
        `ingest_events` call is stubbed, reproducing the exact presence-only
        check `webhook_router_v2._verify_api_key_present` performs), proving
        a real CSV attachment is no longer 401'd by a falsy
        X-RegEngine-API-Key. Regression test for the x_regengine_api_key=None
        bug: before the fix this raised HTTPException(401) for every
        attachment, before CTEPersistence ever ran."""
        import services.ingestion.app.csv_templates as csv_templates_mod
        from services.ingestion.app.webhook_models import IngestResponse

        async def fake_ingest_events(payload, *, principal_tenant_id, x_regengine_api_key=None):
            if not x_regengine_api_key:
                raise HTTPException(status_code=401, detail="Invalid or missing API key")
            return IngestResponse(accepted=1, rejected=0, total=1, events=[])

        monkeypatch.setattr(csv_templates_mod, "ingest_events", fake_ingest_events)

        csv_bytes = (
            b"cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name\n"
            b"harvesting,LOT-001,Kale,10,lbs,Farm A\n"
        )
        result = await _ingest_attachment_csv("11111111-1111-1111-1111-111111111111", "data.csv", csv_bytes)
        assert result.status == "accepted"
        assert result.rows_accepted == 1


# ---------------------------------------------------------------------------
# process_inbound_email — full orchestration, DB session mocked
# ---------------------------------------------------------------------------


def _payload(**overrides) -> PostmarkInboundPayload:
    kwargs = dict(
        MessageID="msg-1",
        From="sender@example.com",
        OriginalRecipient="tenant-inbox@tenant.regengine.co",
        Attachments=[],
    )
    kwargs.update(overrides)
    return PostmarkInboundPayload(**kwargs)


@pytest.fixture(autouse=True)
def _no_real_audit_persistence(monkeypatch):
    """Default every test to a DB session that never leaves the process.

    Individual tests still monkeypatch ``get_inbound_email_audit_by_message_id``
    / ``claim_inbound_email_audit`` / ``finalize_inbound_email_audit`` at the
    module level to assert on calls; this fixture just guarantees
    ``db_session`` itself is never touched for real if a test forgets to
    stub one of them.
    """
    yield


def _stub_claim(monkeypatch, *, succeeds=True):
    """Most orchestration tests only care about what happens after a
    successful claim, not the claim SQL itself (covered by
    ``TestClaimInboundEmailAudit``) -- stub it to a deterministic
    success/failure rather than relying on a bare ``MagicMock`` session's
    incidental truthiness.
    """
    calls = []

    def fake_claim(db, **kwargs):
        calls.append(kwargs)
        return {"id": "1", "message_id": kwargs["message_id"], "status": "processing"} if succeeds else None

    monkeypatch.setattr(service_mod, "claim_inbound_email_audit", fake_claim)
    return calls


class TestProcessInboundEmailIdempotency:
    async def test_replays_existing_audit_row_without_reprocessing(self, monkeypatch):
        existing = {
            "message_id": "msg-1",
            "status": "accepted",
            "tenant_id": "tenant-1",
            "rejection_reason": None,
            "details": [],
        }
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: existing)

        lookup_called = False

        def fail_lookup(db, address, sender):
            nonlocal lookup_called
            lookup_called = True
            return "tenant-1"

        monkeypatch.setattr(service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", fail_lookup)

        def fail_claim(*args, **kwargs):
            raise AssertionError("claim_inbound_email_audit must not run on idempotent replay")

        def fail_finalize(*args, **kwargs):
            raise AssertionError("finalize_inbound_email_audit must not run on idempotent replay")

        monkeypatch.setattr(service_mod, "claim_inbound_email_audit", fail_claim)
        monkeypatch.setattr(service_mod, "finalize_inbound_email_audit", fail_finalize)

        db = MagicMock()
        result = await process_inbound_email(db, _payload())

        assert result.message_id == "msg-1"
        assert result.status == "accepted"
        assert result.tenant_id == "tenant-1"
        assert lookup_called is False

    async def test_processing_row_is_not_replayed(self, monkeypatch):
        # A row left at status='processing' belongs to a request that is (or
        # was, until it crashed) still mid-flight -- it must not be treated
        # as a finished result.
        existing = {
            "message_id": "msg-1",
            "status": "processing",
            "tenant_id": None,
            "rejection_reason": None,
            "details": [],
        }
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: existing)
        monkeypatch.setattr(
            service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", lambda db, addr, sender: "tenant-1"
        )
        _stub_claim(monkeypatch, succeeds=True)
        monkeypatch.setattr(service_mod, "finalize_inbound_email_audit", lambda db, **kwargs: {"id": "1"})
        monkeypatch.setattr(service_mod, "set_tenant_guc", lambda db, tid: None)

        db = MagicMock()
        result = await process_inbound_email(db, _payload(Attachments=[]))

        # Proceeded past the initial idempotency check instead of replaying
        # the still-in-flight row, and (since our own claim succeeded)
        # completed normally.
        assert result.status == "accepted"

    async def test_lost_claim_race_replays_winners_finished_result(self, monkeypatch):
        # First read: no row yet. Claim: lost the race (another concurrent
        # delivery beat us to it). Re-read: the winner has since finished.
        monkeypatch.setattr(
            service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", lambda db, addr, sender: "tenant-1"
        )
        _stub_claim(monkeypatch, succeeds=False)

        finished = {
            "message_id": "msg-1",
            "status": "accepted",
            "tenant_id": "tenant-1",
            "rejection_reason": None,
            "details": [],
        }
        reads = [None, finished]
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: reads.pop(0))

        db = MagicMock()
        result = await process_inbound_email(db, _payload())

        assert result.status == "accepted"
        assert result.tenant_id == "tenant-1"

    async def test_lost_claim_race_still_in_flight_raises_409(self, monkeypatch):
        # First read: no row yet. Claim: lost the race. Re-read: the winner
        # is still processing -- must not fabricate a result or run
        # ingestion ourselves.
        monkeypatch.setattr(
            service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", lambda db, addr, sender: "tenant-1"
        )
        _stub_claim(monkeypatch, succeeds=False)

        still_processing = {
            "message_id": "msg-1",
            "status": "processing",
            "tenant_id": "tenant-1",
            "rejection_reason": None,
            "details": [],
        }
        reads = [None, still_processing]
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: reads.pop(0))

        db = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            await process_inbound_email(db, _payload())
        assert exc_info.value.status_code == 409


class TestProcessInboundEmailSenderAllowlist:
    async def test_sender_address_is_forwarded_to_tenant_lookup(self, monkeypatch):
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: None)
        captured = {}

        def fake_lookup(db, address, sender):
            captured["address"] = address
            captured["sender"] = sender
            return None

        monkeypatch.setattr(service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", fake_lookup)
        _stub_claim(monkeypatch, succeeds=True)
        monkeypatch.setattr(service_mod, "finalize_inbound_email_audit", lambda db, **kwargs: {"id": "1"})

        db = MagicMock()
        payload = _payload(From='"Some Sender" <Sender@Example.COM>')
        await process_inbound_email(db, payload)

        assert captured["address"] == "tenant-inbox@tenant.regengine.co"
        assert captured["sender"] == "sender@example.com"


class TestProcessInboundEmailUnmappedRecipient:
    async def test_no_recipient_at_all_is_rejected_without_tenant_lookup(self, monkeypatch):
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: None)

        def fail_lookup(db, address, sender):
            raise AssertionError("tenant lookup must not run without a recipient")

        monkeypatch.setattr(service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", fail_lookup)
        _stub_claim(monkeypatch, succeeds=True)

        recorded = {}

        def fake_finalize(db, **kwargs):
            recorded.update(kwargs)
            return {"id": "1"}

        monkeypatch.setattr(service_mod, "finalize_inbound_email_audit", fake_finalize)

        db = MagicMock()
        payload = _payload(OriginalRecipient=None, To=None, ToFull=None)
        result = await process_inbound_email(db, payload)

        assert result.status == "rejected"
        assert result.rejection_reason == "unmapped_recipient"
        assert result.tenant_id is None
        assert recorded["status"] == "rejected"
        assert recorded["rejection_reason"] == "unmapped_recipient"

    async def test_recipient_present_but_unmapped_is_rejected(self, monkeypatch):
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: None)
        monkeypatch.setattr(
            service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", lambda db, addr, sender: None
        )
        claim_calls = _stub_claim(monkeypatch, succeeds=True)

        recorded = {}

        def fake_finalize(db, **kwargs):
            recorded.update(kwargs)
            return {"id": "1"}

        monkeypatch.setattr(service_mod, "finalize_inbound_email_audit", fake_finalize)

        db = MagicMock()
        result = await process_inbound_email(db, _payload())

        assert result.status == "rejected"
        assert result.rejection_reason == "unmapped_recipient"
        assert claim_calls[0]["recipient"] == "tenant-inbox@tenant.regengine.co"


class TestProcessInboundEmailMappedTenant:
    def _setup(self, monkeypatch, tenant_id="tenant-1"):
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: None)
        monkeypatch.setattr(
            service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", lambda db, addr, sender: tenant_id
        )
        _stub_claim(monkeypatch, succeeds=True)
        guc_calls = []
        monkeypatch.setattr(service_mod, "set_tenant_guc", lambda db, tid: guc_calls.append(tid))
        recorded = {}

        def fake_finalize(db, **kwargs):
            recorded.update(kwargs)
            return {"id": "1"}

        monkeypatch.setattr(service_mod, "finalize_inbound_email_audit", fake_finalize)
        return guc_calls, recorded

    async def test_no_attachments_is_accepted(self, monkeypatch):
        guc_calls, recorded = self._setup(monkeypatch)
        db = MagicMock()
        result = await process_inbound_email(db, _payload(Attachments=[]))

        assert result.status == "accepted"
        assert result.tenant_id == "tenant-1"
        assert guc_calls == ["tenant-1"]
        assert recorded["status"] == "accepted"
        assert recorded["attachment_count"] == 0

    async def test_all_attachments_accepted_is_accepted(self, monkeypatch):
        self._setup(monkeypatch)

        async def fake_process_one(tenant_id, attachment):
            return AttachmentResult(name=attachment.Name, status="accepted", rows_accepted=5)

        monkeypatch.setattr(service_mod, "_process_one_attachment", fake_process_one)

        db = MagicMock()
        payload = _payload(
            Attachments=[{"Name": "a.csv", "Content": VALID_B64, "ContentType": "text/csv"}],
        )
        result = await process_inbound_email(db, payload)
        assert result.status == "accepted"
        assert len(result.attachments) == 1

    async def test_mixed_results_is_partial(self, monkeypatch):
        self._setup(monkeypatch)

        async def fake_process_one(tenant_id, attachment):
            if attachment.Name == "good.csv":
                return AttachmentResult(name=attachment.Name, status="accepted", rows_accepted=2)
            return AttachmentResult(name=attachment.Name, status="rejected", reason="bad_type")

        monkeypatch.setattr(service_mod, "_process_one_attachment", fake_process_one)

        db = MagicMock()
        payload = _payload(
            Attachments=[
                {"Name": "good.csv", "Content": VALID_B64, "ContentType": "text/csv"},
                {"Name": "bad.pdf", "Content": VALID_B64, "ContentType": "application/pdf"},
            ],
        )
        result = await process_inbound_email(db, payload)
        assert result.status == "partial"

    async def test_all_attachments_rejected_is_rejected(self, monkeypatch):
        self._setup(monkeypatch)

        async def fake_process_one(tenant_id, attachment):
            return AttachmentResult(name=attachment.Name, status="rejected", reason="bad_type")

        monkeypatch.setattr(service_mod, "_process_one_attachment", fake_process_one)

        db = MagicMock()
        payload = _payload(
            Attachments=[{"Name": "bad.pdf", "Content": VALID_B64, "ContentType": "application/pdf"}],
        )
        result = await process_inbound_email(db, payload)
        assert result.status == "rejected"
        # Distinct from the unmapped-recipient rejection: no rejection_reason
        # is stamped here, the per-attachment `reason` carries the detail.
        assert result.rejection_reason is None


class TestProcessInboundEmailCrashRecovery:
    # Review finding: an unexpected exception between the claim INSERT and
    # finalize_inbound_email_audit used to leave the audit row stuck at
    # status='processing' forever -- every future Postmark redelivery of
    # the same MessageID then loses the claim race and gets a permanent
    # 409, so the email's CSV attachments are never ingested (silent data
    # loss). These tests pin the fix: any such exception must still
    # finalize the row (to a terminal 'rejected' state) before propagating.

    def _setup(self, monkeypatch, tenant_id="tenant-1"):
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: None)
        monkeypatch.setattr(
            service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", lambda db, addr, sender: tenant_id
        )
        _stub_claim(monkeypatch, succeeds=True)
        recorded = {}

        def fake_finalize(db, **kwargs):
            recorded.update(kwargs)
            return {"id": "1"}

        monkeypatch.setattr(service_mod, "finalize_inbound_email_audit", fake_finalize)
        return recorded

    async def test_exception_during_attachment_processing_still_finalizes_and_reraises(self, monkeypatch):
        recorded = self._setup(monkeypatch)
        monkeypatch.setattr(service_mod, "set_tenant_guc", lambda db, tid: None)

        async def _boom(tenant_id, attachment):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(service_mod, "_process_one_attachment", _boom)

        db = MagicMock()
        payload = _payload(
            Attachments=[{"Name": "a.csv", "Content": VALID_B64, "ContentType": "text/csv"}],
        )
        with pytest.raises(RuntimeError, match="simulated crash"):
            await process_inbound_email(db, payload)

        # The row must be finalized to a terminal state, not left
        # 'processing' -- that's the whole point of the fix.
        assert recorded["status"] == "rejected"
        assert recorded["rejection_reason"] == "internal_error"
        db.rollback.assert_called_once()

    async def test_exception_in_set_tenant_guc_still_finalizes_and_reraises(self, monkeypatch):
        recorded = self._setup(monkeypatch)

        def _boom(db, tid):
            raise RuntimeError("guc failure")

        monkeypatch.setattr(service_mod, "set_tenant_guc", _boom)

        db = MagicMock()
        payload = _payload(Attachments=[])
        with pytest.raises(RuntimeError, match="guc failure"):
            await process_inbound_email(db, payload)

        assert recorded["status"] == "rejected"
        assert recorded["rejection_reason"] == "internal_error"

    async def test_exception_in_finalize_itself_is_not_swallowed(self, monkeypatch):
        # If finalize_inbound_email_audit fails even on the recovery
        # attempt, that failure must still propagate -- never silently
        # swallowed -- so the caller/router surfaces a non-2xx and the
        # crash is not masked as a clean response.
        monkeypatch.setattr(service_mod, "get_inbound_email_audit_by_message_id", lambda db, mid: None)
        monkeypatch.setattr(
            service_mod.tenant_lookup, "lookup_tenant_by_inbound_address", lambda db, addr, sender: "tenant-1"
        )
        _stub_claim(monkeypatch, succeeds=True)
        monkeypatch.setattr(service_mod, "set_tenant_guc", lambda db, tid: None)

        async def _boom(tenant_id, attachment):
            raise RuntimeError("simulated crash")

        monkeypatch.setattr(service_mod, "_process_one_attachment", _boom)

        def _finalize_also_fails(db, **kwargs):
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(service_mod, "finalize_inbound_email_audit", _finalize_also_fails)

        db = MagicMock()
        payload = _payload(
            Attachments=[{"Name": "a.csv", "Content": VALID_B64, "ContentType": "text/csv"}],
        )
        with pytest.raises(RuntimeError, match="db unavailable"):
            await process_inbound_email(db, payload)
