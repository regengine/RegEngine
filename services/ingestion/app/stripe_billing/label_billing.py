"""Per-label FSMA 204 traceability billing (v121).

RegEngine's Stripe integration has only ever sold flat-rate subscription
plans (``PLANS`` in ``plans.py``) -- nothing has priced traceability output
per label/unit. This module adds that: one row in ``fsma.label_charges``
per ``fsma.cte_events.id`` actually billed, claimed via
``INSERT ... ON CONFLICT DO NOTHING`` so a retried ingest can never charge
the same label twice. The pattern mirrors the claim-then-patch approach
already used for ``fsma.cte_events`` itself
(``services/shared/cte_persistence/batch.py``).

Deliberately NOT participating in the caller's ambient request session:
``charge_for_label`` opens and commits its own short-lived DB session
(``shared.database.get_db_safe``) for the claim, independent of whatever
transaction the ingest request is running. Stripe's ``InvoiceItem.create``
is a real, irreversible external side effect -- if the claim row lived in
the same still-open transaction as the rest of the request, a later
rollback anywhere else in that request (an unrelated event in the batch
failing, the request 500ing) would erase the claim while the Stripe charge
already happened, and a retry would charge again. Committing the claim in
its own transaction *before* Stripe is ever called closes that gap.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Callable, Optional

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


def _default_session() -> Any:
    from shared.database import get_db_safe

    return get_db_safe()


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
    tenant_id: str,
    cte_event_id: str,
    amount_cents: int,
    *,
    session_factory: Optional[Callable[[], Any]] = None,
) -> LabelChargeResult:
    """Charge ``amount_cents`` for one accepted traceability label.

    Idempotent: calling this twice for the same (tenant_id, cte_event_id)
    charges Stripe at most once -- the second call finds the row already
    claimed (committed by the first call before it ever touched Stripe)
    and returns it unchanged (``claimed=False``).

    A tenant with no Stripe customer yet (e.g. a sandbox/trial tenant) is
    recorded as ``STATUS_NO_CUSTOMER`` rather than raising, so a tenant
    still in onboarding never breaks label ingestion.

    ``session_factory`` overrides how the DB session is obtained (tests
    inject a fake); production uses ``shared.database.get_db_safe``.
    """
    session = (session_factory or _default_session)()
    if session is None:
        raise RuntimeError("label billing DB session unavailable")

    try:
        charge_id, claimed = _claim_charge_row(session, tenant_id, cte_event_id, amount_cents)
        # Durable BEFORE any Stripe call -- see module docstring. Once this
        # commits, no later rollback anywhere else can un-claim this label.
        session.commit()

        if not claimed:
            row = session.execute(
                text("SELECT amount_cents, status, stripe_invoice_item_id FROM fsma.label_charges WHERE id = :id"),
                {"id": charge_id},
            ).fetchone()
            return LabelChargeResult(
                charge_id=charge_id,
                tenant_id=tenant_id,
                cte_event_id=cte_event_id,
                # The persisted amount, not this call's argument -- if
                # PRICE_PER_LABEL_CENTS changed since the first attempt, the
                # Stripe item (and any charge) was created at the OLD price.
                amount_cents=row[0] if row else amount_cents,
                status=row[1] if row else STATUS_CHARGED,
                stripe_invoice_item_id=row[2] if row else None,
                claimed=False,
            )

        # Everything from here on is best-effort in the sense that ANY
        # failure -- customer lookup, Stripe config, the Stripe call itself,
        # a non-Stripe SDK error -- must leave the claim in a terminal,
        # visible STATUS_FAILED state rather than stuck 'pending' forever.
        # A 'pending' row is indistinguishable from "in progress" to every
        # later caller (the `not claimed` branch above returns it as-is,
        # with no retry), so an uncaught exception here would silently and
        # permanently lose the charge.
        try:
            customer_id = _get_existing_customer_id(tenant_id)
            if not customer_id:
                session.execute(
                    text("UPDATE fsma.label_charges SET status = :status WHERE id = :id"),
                    {"status": STATUS_NO_CUSTOMER, "id": charge_id},
                )
                session.commit()
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
        except Exception as exc:  # noqa: BLE001 -- see comment above: any failure must reach STATUS_FAILED
            session.execute(
                text("UPDATE fsma.label_charges SET status = :status, error_message = :error WHERE id = :id"),
                {"status": STATUS_FAILED, "error": str(exc), "id": charge_id},
            )
            session.commit()
            logger.error(
                "label_charge_failed",
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
        session.commit()
        return LabelChargeResult(
            charge_id=charge_id,
            tenant_id=tenant_id,
            cte_event_id=cte_event_id,
            amount_cents=amount_cents,
            status=STATUS_CHARGED,
            stripe_invoice_item_id=invoice_item_id,
            claimed=True,
        )
    finally:
        session.close()


def get_label_charge(session: Any, tenant_id: str, cte_event_id: str) -> Optional[dict]:
    """Return the persisted charge row for one label, or ``None``.

    This is the queryable record proving per-label pricing is real: the
    amount charged, its status, and (once charged) the Stripe invoice item
    id it produced. Read-only, so (unlike ``charge_for_label``) it is safe
    to run against the caller's ambient session.
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
