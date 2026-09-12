"""Tests for v121 -- per-label FSMA 204 traceability billing.

Covers the three things that make "we price per label" a real claim rather
than a marketing line: a label is charged the configured per-unit rate
exactly once, charging is idempotent under retry (processing the same
label twice must not double-charge), and the charge is queryable back as a
DB record. All Stripe calls are mocked -- no live or test-mode Stripe key
is used, matching the existing convention in tests/billing/.
"""

from __future__ import annotations

import uuid
from unittest.mock import patch

from services.ingestion.app.stripe_billing import (
    STATUS_CHARGED,
    STATUS_NO_CUSTOMER,
    charge_for_label,
    get_label_charge,
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"
EVENT_ID = "22222222-2222-2222-2222-222222222222"


class _Result:
    def __init__(self, rows=None):
        self._rows = rows or []

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakeLabelChargesSession:
    """In-memory stand-in for ``fsma.label_charges``.

    Enforces the same key semantics as the real
    ``UNIQUE (tenant_id, cte_event_id)`` constraint: a second INSERT for a
    key already present is a no-op, exactly like ``ON CONFLICT DO NOTHING``
    on Postgres. No live database needed -- this exercises the real
    claim-then-patch logic in ``label_billing.py``, just against an
    in-memory table instead of Postgres.
    """

    def __init__(self):
        self.rows: dict[tuple[str, str], dict] = {}
        self.insert_calls = 0

    def execute(self, stmt, params=None):
        sql = str(getattr(stmt, "text", stmt))
        params = params or {}

        if "INSERT INTO fsma.label_charges" in sql:
            self.insert_calls += 1
            key = (params["tenant_id"], params["cte_event_id"])
            if key in self.rows:
                return _Result(rows=[])
            row_id = str(uuid.uuid4())
            self.rows[key] = {
                "id": row_id,
                "amount_cents": params["amount_cents"],
                "currency": "usd",
                "status": "pending",
                "stripe_customer_id": None,
                "stripe_invoice_item_id": None,
                "created_at": "2026-09-12T00:00:00Z",
                "charged_at": None,
            }
            return _Result(rows=[(row_id,)])

        if sql.strip().startswith("SELECT id FROM fsma.label_charges"):
            key = (params["tenant_id"], params["cte_event_id"])
            row = self.rows.get(key)
            return _Result(rows=[(row["id"],)] if row else [])

        if "SELECT status, stripe_invoice_item_id" in sql:
            row = self._row_by_id(params["id"])
            return _Result(rows=[(row["status"], row["stripe_invoice_item_id"])] if row else [])

        if "SELECT id, amount_cents, currency, status" in sql:
            key = (params["tenant_id"], params["cte_event_id"])
            row = self.rows.get(key)
            if not row:
                return _Result(rows=[])
            return _Result(
                rows=[
                    (
                        row["id"],
                        row["amount_cents"],
                        row["currency"],
                        row["status"],
                        row["stripe_invoice_item_id"],
                        row["created_at"],
                        row["charged_at"],
                    )
                ]
            )

        if "stripe_invoice_item_id = :invoice_item_id" in sql:
            row = self._row_by_id(params["id"])
            row["status"] = params["status"]
            row["stripe_customer_id"] = params["customer_id"]
            row["stripe_invoice_item_id"] = params["invoice_item_id"]
            row["charged_at"] = "2026-09-12T00:00:01Z"
            return _Result()

        if "error_message" in sql:
            row = self._row_by_id(params["id"])
            row["status"] = params["status"]
            row["stripe_customer_id"] = params["customer_id"]
            return _Result()

        if sql.strip().startswith("UPDATE fsma.label_charges SET status = :status WHERE id"):
            row = self._row_by_id(params["id"])
            row["status"] = params["status"]
            return _Result()

        raise AssertionError(f"unexpected SQL in fake session: {sql}")

    def _row_by_id(self, row_id):
        for row in self.rows.values():
            if row["id"] == row_id:
                return row
        return None


@patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"})
@patch("services.ingestion.app.stripe_billing.stripe")
@patch(
    "services.ingestion.app.stripe_billing.label_billing._get_existing_customer_id",
    return_value="cus_test_123",
)
def test_charge_for_label_charges_exactly_once(_mock_get_customer, mock_stripe):
    """A label gets charged the configured per-unit rate exactly once."""
    mock_stripe.InvoiceItem.create.return_value = {"id": "ii_test_1"}
    session = _FakeLabelChargesSession()

    result = charge_for_label(session, tenant_id=TENANT_ID, cte_event_id=EVENT_ID, amount_cents=10)

    assert result.status == STATUS_CHARGED
    assert result.amount_cents == 10
    assert result.stripe_invoice_item_id == "ii_test_1"
    assert result.claimed is True
    mock_stripe.InvoiceItem.create.assert_called_once_with(
        customer="cus_test_123",
        amount=10,
        currency="usd",
        description=f"FSMA 204 per-label traceability charge (event {EVENT_ID})",
    )


@patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"})
@patch("services.ingestion.app.stripe_billing.stripe")
@patch(
    "services.ingestion.app.stripe_billing.label_billing._get_existing_customer_id",
    return_value="cus_test_123",
)
def test_charge_for_label_idempotent_under_retry(_mock_get_customer, mock_stripe):
    """Processing the same label twice must not double-charge."""
    mock_stripe.InvoiceItem.create.return_value = {"id": "ii_test_2"}
    session = _FakeLabelChargesSession()

    first = charge_for_label(session, tenant_id=TENANT_ID, cte_event_id=EVENT_ID, amount_cents=10)
    second = charge_for_label(session, tenant_id=TENANT_ID, cte_event_id=EVENT_ID, amount_cents=10)

    assert mock_stripe.InvoiceItem.create.call_count == 1, "retry must not call Stripe a second time"
    assert session.insert_calls == 2, "both attempts try to claim the row; only the first should win"
    assert first.claimed is True
    assert second.claimed is False
    assert second.charge_id == first.charge_id
    assert second.status == STATUS_CHARGED
    assert second.stripe_invoice_item_id == "ii_test_2"


@patch("services.ingestion.app.stripe_billing.stripe")
@patch(
    "services.ingestion.app.stripe_billing.label_billing._get_existing_customer_id",
    return_value=None,
)
def test_charge_for_label_skips_stripe_without_customer(_mock_get_customer, mock_stripe):
    """A tenant with no Stripe customer yet never triggers a Stripe call."""
    session = _FakeLabelChargesSession()

    result = charge_for_label(session, tenant_id=TENANT_ID, cte_event_id=EVENT_ID, amount_cents=10)

    assert result.status == STATUS_NO_CUSTOMER
    mock_stripe.InvoiceItem.create.assert_not_called()


@patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_123"})
@patch("services.ingestion.app.stripe_billing.stripe")
@patch(
    "services.ingestion.app.stripe_billing.label_billing._get_existing_customer_id",
    return_value="cus_test_123",
)
def test_label_charge_is_queryable(_mock_get_customer, mock_stripe):
    """The per-label price is queryable back as a DB record."""
    mock_stripe.InvoiceItem.create.return_value = {"id": "ii_test_3"}
    session = _FakeLabelChargesSession()

    charge_for_label(session, tenant_id=TENANT_ID, cte_event_id=EVENT_ID, amount_cents=17)
    record = get_label_charge(session, tenant_id=TENANT_ID, cte_event_id=EVENT_ID)

    assert record is not None
    assert record["amount_cents"] == 17
    assert record["status"] == STATUS_CHARGED
    assert record["stripe_invoice_item_id"] == "ii_test_3"
