"""Router for the Postmark inbound-parse webhook.

See ``DESIGN_email-ingestion.md`` section 9. Every rejection path (unmapped
recipient, oversized/wrong-type/undecodable attachment, zero valid CSV rows)
returns **200** with a structured body — provider webhooks retry on 5xx, so
turning a data-quality problem into a 5xx would just cause Postmark to
hammer us with identical retries. A missing/invalid ``Authorization`` header
(401, handled by ``verify_inbound_email_auth``), a client IP blocked after
repeated auth failures (429, same gate), DB unavailability (503), and
— since v122's claim-then-act idempotency fix — a concurrent delivery of the
same ``MessageID`` still being processed elsewhere (409, raised from
``process_inbound_email``) are the non-200 cases; all four are exactly the
kind of transient condition Postmark's retry-on-non-2xx contract is meant to
recover from.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from shared.database import get_db_session

from .auth import verify_inbound_email_auth
from .schemas import InboundEmailResult, PostmarkInboundPayload
from .service import process_inbound_email

router = APIRouter(prefix="/webhooks/email", tags=["Inbound Email"])


@router.post(
    "/inbound",
    response_model=InboundEmailResult,
    dependencies=[Depends(verify_inbound_email_auth)],
    summary="Postmark inbound-parse webhook",
)
async def receive_inbound_email(
    payload: PostmarkInboundPayload,
    db_session=Depends(get_db_session),
) -> InboundEmailResult:
    if db_session is None:
        # Genuine transient failure — the only case this endpoint 5xxs on,
        # so Postmark's retry-on-5xx actually helps instead of hammering a
        # dead DB with duplicate CSV ingestion.
        raise HTTPException(status_code=503, detail="Database unavailable")
    return await process_inbound_email(db_session, payload)
