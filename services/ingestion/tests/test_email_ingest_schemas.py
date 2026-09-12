"""Unit tests for ``app.email_ingest.schemas``.

Covers the Postmark inbound-webhook payload models: required fields,
``extra="ignore"`` tolerance for provider fields we don't model, and the
default shapes of the two response models.
"""

from __future__ import annotations

import pytest
from app.email_ingest.schemas import (
    AttachmentResult,
    InboundEmailResult,
    PostmarkAttachment,
    PostmarkInboundPayload,
)
from pydantic import ValidationError


class TestPostmarkAttachment:
    def test_required_fields_parse(self):
        att = PostmarkAttachment(Name="data.csv", Content="YWJj", ContentType="text/csv")
        assert att.Name == "data.csv"
        assert att.Content == "YWJj"
        assert att.ContentType == "text/csv"
        assert att.ContentLength is None

    def test_content_length_optional_field_parses(self):
        att = PostmarkAttachment(Name="data.csv", Content="YWJj", ContentType="text/csv", ContentLength=3)
        assert att.ContentLength == 3

    def test_unknown_postmark_fields_are_ignored(self):
        # Postmark's real payload includes fields we don't model
        # (e.g. ContentID for inline images) — extra="ignore" must
        # tolerate them rather than rejecting the whole webhook.
        att = PostmarkAttachment(
            Name="data.csv",
            Content="YWJj",
            ContentType="text/csv",
            ContentID="cid:1234",
        )
        assert not hasattr(att, "ContentID")

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            PostmarkAttachment(Name="data.csv", ContentType="text/csv")


class TestPostmarkInboundPayload:
    def test_minimal_payload_parses(self):
        payload = PostmarkInboundPayload(MessageID="msg-1", From="sender@example.com")
        assert payload.MessageID == "msg-1"
        assert payload.From == "sender@example.com"
        assert payload.To is None
        assert payload.ToFull is None
        assert payload.OriginalRecipient is None
        assert payload.Subject is None
        assert payload.TextBody is None
        assert payload.Attachments == []

    def test_full_payload_parses_with_attachments(self):
        payload = PostmarkInboundPayload(
            MessageID="msg-2",
            From="sender@example.com",
            To="recipient@tenant.regengine.co",
            ToFull=[{"Email": "recipient@tenant.regengine.co", "Name": "Tenant"}],
            OriginalRecipient="recipient@tenant.regengine.co",
            Subject="CTE upload",
            TextBody="see attached",
            Attachments=[{"Name": "data.csv", "Content": "YWJj", "ContentType": "text/csv"}],
        )
        assert payload.OriginalRecipient == "recipient@tenant.regengine.co"
        assert len(payload.Attachments) == 1
        assert isinstance(payload.Attachments[0], PostmarkAttachment)

    def test_unknown_postmark_fields_are_ignored(self):
        # Real Postmark payloads carry many fields we never reference
        # (Cc, Headers, HtmlBody, ContentLength, SpamScore, ...) — a
        # provider payload change that only adds fields must never 422.
        payload = PostmarkInboundPayload(
            MessageID="msg-3",
            From="sender@example.com",
            Cc="other@example.com",
            HtmlBody="<p>hi</p>",
            Headers=[{"Name": "X-Spam-Score", "Value": "0.1"}],
        )
        assert not hasattr(payload, "Cc")
        assert not hasattr(payload, "HtmlBody")

    def test_missing_required_field_raises(self):
        with pytest.raises(ValidationError):
            PostmarkInboundPayload(From="sender@example.com")


class TestResponseModels:
    def test_attachment_result_defaults(self):
        result = AttachmentResult(name="data.csv", status="accepted")
        assert result.reason is None
        assert result.rows_accepted == 0
        assert result.rows_rejected == 0

    def test_inbound_email_result_defaults(self):
        result = InboundEmailResult(message_id="msg-1", status="rejected")
        assert result.tenant_id is None
        assert result.rejection_reason is None
        assert result.attachments == []
