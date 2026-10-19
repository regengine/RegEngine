"""Pydantic models for the inbound-email ingestion slice.

``PostmarkAttachment`` / ``PostmarkInboundPayload`` model Postmark's inbound
webhook JSON shape (``From``, ``Subject``, ``TextBody``,
``Attachments: [{Name, Content, ContentType}]``) — see
``DESIGN_email-ingestion.md`` section 4. ``extra="ignore"`` on both models
means Postmark fields we don't use (``Cc``, ``Headers``, ``HtmlBody``,
``ContentLength``, etc.) are silently tolerated rather than rejected, so a
provider payload change that only adds fields never breaks this endpoint.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class PostmarkAttachment(BaseModel):
    """One entry of Postmark's inbound ``Attachments`` array."""

    Name: str
    Content: str  # base64-encoded attachment bytes
    ContentType: str
    ContentLength: Optional[int] = None

    model_config = ConfigDict(extra="ignore")


class PostmarkInboundPayload(BaseModel):
    """Postmark inbound-parse webhook body.

    Recipient extraction prefers ``OriginalRecipient`` (Postmark's documented
    field for "which of the inbound stream's addresses this was sent to"),
    then the first address in ``ToFull``, then falls back to parsing ``To`` —
    see ``service._first_recipient``.
    """

    # Non-empty: the audit table keys idempotency on MessageID, so an empty
    # value would make unrelated emails collide and replay each other's
    # recorded results. Rejected at the boundary with a 422.
    MessageID: str = Field(min_length=1)
    From: str
    To: Optional[str] = None
    ToFull: Optional[List[Dict[str, Any]]] = None
    OriginalRecipient: Optional[str] = None
    Subject: Optional[str] = None
    TextBody: Optional[str] = None
    Attachments: List[PostmarkAttachment] = Field(default_factory=list)

    model_config = ConfigDict(extra="ignore")


class AttachmentResult(BaseModel):
    """Per-attachment outcome, stored verbatim in ``inbound_email_audit.details``."""

    name: str
    status: str  # "accepted" | "rejected"
    reason: Optional[str] = None
    rows_accepted: int = 0
    rows_rejected: int = 0


class InboundEmailResult(BaseModel):
    """Response body for ``POST /webhooks/email/inbound``."""

    message_id: str
    status: str  # "accepted" | "partial" | "rejected"
    tenant_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    attachments: List[AttachmentResult] = Field(default_factory=list)
