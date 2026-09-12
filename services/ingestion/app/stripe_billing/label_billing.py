"""Per-label FSMA 204 traceability billing (v121).

RegEngine's Stripe integration has only ever sold flat-rate subscription
plans (``PLANS`` in ``plans.py``) -- nothing has priced traceability output
per label/unit. This module adds that: one row in ``fsma.label_charges``
per ``fsma.cte_events.id`` actually billed, claimed via
``INSERT ... ON CONFLICT DO NOTHING`` so a retried ingest can never charge
the same label twice. The pattern mirrors the claim-then-patch approach
already used for ``fsma.cte_events`` itself
(``services/shared/cte_persistence/batch.py``).
"""

from __future__ import annotations

import dataclasses
from typing import Any, Optional

import stripe
import structlog
from sqlalchemy import text

from .customers import _get_existing_customer_id
from .helpers import _configure_stripe

logger = structlog.get_logger("stripe-billing.label")

STATUS_CHARGED = "charged"
STATUS_NO_CUSTOMER = "no_stripe_customer"
STATUS_FAILED = "failed"


@dataclasses.dataclass
class LabelChargeResult:
    charge_id: str
    tenant_id: str
    cte_event_id: str
    amount_cents: int
    status: str
    stripe_invoice_item_id: Optional[str]
    # True if this call claimed (created) the charge row; False if it
    # already existed -- i.e. this was an idempotent replay that did not
    # touch Stripe again.
    claimed: bool


def _claim_charge_row(session: Any, tenant_id: str, cte_event_id: str, amount_cents: int) -> tuple[str, bool]:
    """Atomically claim the (tenant_id, cte_event_id) charge slot.

    ``UNIQUE (tenant_id, cte_event_id)`` on ``fsma.label_charges`` is the
    actual idempotency guarantee -- it holds under concurrent retries, not
    just sequential ones -- so the DO NOTHING branch below always wins a
    race rather than merely detecting one after the fact.
    """
    inserted = session.execute(
        text("""
            INSERT INTO fsma.label_charges (tenant_id, cte_event_id, amount_cents, status)
            VALUES (:tenant_id, :cte_event_id, :amount_cents, 'pending')
            ON CONFLICT (tenant_id, cte_event_id) DO NOTHING
            RETURNING id
        """),
        {"tenant_id": tenant_id, "cte_event_id": cte_event_id, "amount_cents": amount_cents},
    ).fetchone()
    if inserted is not None:
        return str(inserted[0]), True

    existing = session.execute(
        text("""
            SELECT id FROM fsma.label_charges
            WHERE tenant_id = :tenant_id AND cte_event_id = :cte_event_id
        """),
        {"tenant_id": tenant_id, "cte_event_id": cte_event_id},
    ).fetchone()
    return str(existing[0]), False


def charge_for_label(
    session: Any,
    tenant_id: str,
    cte_event_id: str,
    amount_cents: int,
) -> LabelChargeResult:
    """Charge ``amount_cents`` for one accepted traceability label.

    Idempotent: calling this twice for the same (tenant_id, cte_event_id)
    charges Stripe at most once -- the second call finds the row already
    claimed and returns it unchanged (``claimed=False``) without any Stripe
    call. The caller is responsible for committing ``session``.

    A tenant with no Stripe customer yet (e.g. a sandbox/trial tenant) is
    recorded as ``STATUS_NO_CUSTOMER`` rather than raising, so a tenant
    still in onboarding never breaks label ingestion.
    """
    charge_id, claimed = _claim_charge_row(session, tenant_id, cte_event_id, amount_cents)
    if not claimed:
        row = session.execute(
            text("SELECT status, stripe_invoice_item_id FROM fsma.label_charges WHERE id = :id"),
            {"id": charge_id},
        ).fetchone()
        return LabelChargeResult(
            charge_id=charge_id,
            tenant_id=tenant_id,
            cte_event_id=cte_event_id,
            amount_cents=amount_cents,
            status=row[0] if row else STATUS_CHARGED,
            stripe_invoice_item_id=row[1] if row else None,
            claimed=False,
        )

    customer_id = _get_existing_customer_id(tenant_id)
    if not customer_id:
        session.execute(
            text("UPDATE fsma.label_charges SET status = :status WHERE id = :id"),
            {"status": STATUS_NO_CUSTOMER, "id": charge_id},
        )
        logger.info("label_charge_skipped_no_customer", tenant_id=tenant_id, cte_event_id=cte_event_id)
        return LabelChargeResult(
            charge_id=charge_id,
            tenant_id=tenant_id,
            cte_event_id=cte_event_id,
            amount_cents=amount_cents,
            status=STATUS_NO_CUSTOMER,
            stripe_invoice_item_id=None,
            claimed=True,
        )

    try:
        _configure_stripe()
        invoice_item = stripe.InvoiceItem.create(
            customer=customer_id,
            amount=amount_cents,
            currency="usd",
            description=f"FSMA 204 per-label traceability charge (event {cte_event_id})",
        )
        if isinstance(invoice_item, dict):
            invoice_item_id = str(invoice_item.get("id") or "")
        else:
            invoice_item_id = str(getattr(invoice_item, "id", "") or "")
    except stripe.error.StripeError as exc:
        session.execute(
            text(
                "UPDATE fsma.label_charges "
                "SET status = :status, stripe_customer_id = :customer_id, error_message = :error "
                "WHERE id = :id"
            ),
            {"status": STATUS_FAILED, "customer_id": customer_id, "error": str(exc), "id": charge_id},
        )
        logger.error(
            "label_charge_stripe_failed",
            tenant_id=tenant_id,
            cte_event_id=cte_event_id,
            error=str(exc),
        )
        return LabelChargeResult(
            charge_id=charge_id,
            tenant_id=tenant_id,
            cte_event_id=cte_event_id,
            amount_cents=amount_cents,
            status=STATUS_FAILED,
            stripe_invoice_item_id=None,
            claimed=True,
        )

    session.execute(
        text(
            "UPDATE fsma.label_charges "
            "SET status = :status, stripe_customer_id = :customer_id, "
            "stripe_invoice_item_id = :invoice_item_id, charged_at = now() "
            "WHERE id = :id"
        ),
        {
            "status": STATUS_CHARGED,
            "customer_id": customer_id,
            "invoice_item_id": invoice_item_id,
            "id": charge_id,
        },
    )
    return LabelChargeResult(
        charge_id=charge_id,
        tenant_id=tenant_id,
        cte_event_id=cte_event_id,
        amount_cents=amount_cents,
        status=STATUS_CHARGED,
        stripe_invoice_item_id=invoice_item_id,
        claimed=True,
    )


def get_label_charge(session: Any, tenant_id: str, cte_event_id: str) -> Optional[dict]:
    """Return the persisted charge row for one label, or ``None``.

    This is the queryable record proving per-label pricing is real: the
    amount charged, its status, and (once charged) the Stripe invoice item
    id it produced.
    """
    row = session.execute(
        text(
            "SELECT id, amount_cents, currency, status, stripe_invoice_item_id, created_at, charged_at "
            "FROM fsma.label_charges WHERE tenant_id = :tenant_id AND cte_event_id = :cte_event_id"
        ),
        {"tenant_id": tenant_id, "cte_event_id": cte_event_id},
    ).fetchone()
    if row is None:
        return None
    return {
        "id": str(row[0]),
        "amount_cents": row[1],
        "currency": row[2],
        "status": row[3],
        "stripe_invoice_item_id": row[4],
        "created_at": row[5],
        "charged_at": row[6],
    }
