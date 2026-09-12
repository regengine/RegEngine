# Per-Label Metered Billing — Technical Design

Status: proposed
Branch: `feature/per-label-metered-billing`
Author context: written against `main`@`abbfd2f` (alembic head `c6a120b4e901`, v120)

## 1. Scope

Add an additive, opt-in per-unit metered billing layer on top of the existing
flat-tier plans (`growth` / `scale` / `enterprise`, `services/ingestion/app/stripe_billing/plans.py`).
It does not touch the checkout/subscription/webhook flow for flat tiers.

**Billable unit ("a label")**: one `TraceabilityEvent` that is durably accepted
into `fsma.traceability_events` — i.e. one call to
`CanonicalEventStore.persist_event` / `persist_events_batch`
(`services/shared/canonical_persistence/writer.py`) that inserts a **new** row
(`inserted is not None` / `event_id in inserted_event_ids`), not a replay that
resolves to `idempotent=True`. This is the actual acceptance path for every
production caller of the canonical writer (traced below) — there is no
separate "acceptance" event or table to key off.

## 2. Callers of the canonical writer (traced, not assumed)

```
grep -rn "CanonicalEventStore(" services --include=*.py
```

Production call sites, all going through `writer.py`'s `persist_event` /
`persist_events_batch`:

- `services/ingestion/app/webhook_router_v2/rules_eval.py:197-198` — webhook v2 CTE ingestion (`skip_chain_write=True`)
- `services/ingestion/app/webhook_compat.py:198-202` — legacy webhook compat shim
- `services/ingestion/app/canonical_router.py:301,489,534` — manual/API record creation + amendment
- `services/ingestion/app/epcis/persistence.py:892-898` — EPCIS ingestion
- `services/ingestion/app/remediation/service.py` — supplier remediation release-on-pass
- `services/admin/app/supplier_cte_service.py` — admin-initiated CTE writes
- `services/graph/app/routers/fsma/traceability.py` — graph-service writes

Six-plus call sites, one common choke point. **The hook belongs inside
`writer.py`, not at each call site** — that's the only place that sees every
accepted event exactly once, already holds the per-tenant advisory lock
(`_acquire_chain_lock`), and already runs inside the same DB transaction/session
the caller commits (`shared.database.get_db_session` commits once at request
end — see `services/shared/database.py:725-742`). Modifying 6+ call sites
would both violate "keep the diff focused" and risk missing a future 7th
caller.

## 3. Database schema (new `billing` schema)

New alembic migration:
`alembic/versions/20260912_ceb552c6d36d_v121_billing_usage_counters.py`
(`down_revision = "c6a120b4e901"` <!-- pragma: allowlist secret -->, current head; naming/format follows
`20260827_c1d4e8f20a37_v115_task_queue_tenantless_idempotency.py` and
`20260716_c7a1e5f2b9d4_v095_supplier_remediation_slice.py`: `op.execute`
raw DDL, `IF NOT EXISTS` everywhere, non-destructive `downgrade()`.)

No prior migration ever created a `billing` schema (checked: only `fsma`,
`audit`, `dlq`, `ingestion` schemas exist across `alembic/versions/*.py`).
Stripe subscription/customer state today lives entirely in Redis
(`services/ingestion/app/stripe_billing/state.py`) — this is the first
Postgres-durable billing state in the repo, which is why it gets its own
schema rather than living under `fsma`.

### 3.1 `billing.tenant_usage_event_ledger` — de-dupe guard

One row per **counted** event. This is the idempotency guard the spec asks
for, implemented the same way the codebase already de-dupes canonical
inserts (`ON CONFLICT ... DO NOTHING RETURNING`, see
`writer.py::_insert_canonical_event`) rather than a fragile "last event id"
scalar, which cannot safely de-dupe out-of-order or concurrent callers.

```sql
CREATE TABLE IF NOT EXISTS billing.tenant_usage_event_ledger (
    tenant_id           UUID NOT NULL,
    event_id            UUID NOT NULL,
    billing_period_start DATE NOT NULL,
    counted_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_tenant_usage_event_ledger_period
    ON billing.tenant_usage_event_ledger (tenant_id, billing_period_start);
```

`PRIMARY KEY (tenant_id, event_id)` — `event_id` is already the
canonical event's own UUID (`fsma.traceability_events.event_id`), so this is
"idempotent increment keyed by event id" verbatim. Calling
`increment_usage_for_event` twice for the same `event_id` (e.g. a retried
webhook after the DB commit but before the HTTP response reached the
caller) is a guaranteed no-op.

### 3.2 `billing.tenant_usage_counters` — aggregate, as specified

```sql
CREATE TABLE IF NOT EXISTS billing.tenant_usage_counters (
    tenant_id             UUID NOT NULL,
    billing_period_start  DATE NOT NULL,
    billing_period_end    DATE NOT NULL,
    unit_count            BIGINT NOT NULL DEFAULT 0,
    last_reported_count   BIGINT NOT NULL DEFAULT 0,
    last_reported_at      TIMESTAMPTZ,
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, billing_period_start)
);
```

- `unit_count`: total accepted labels this period (ground truth for
  `GET /api/v1/billing/usage`).
- `last_reported_count` / `last_reported_at`: high-water mark of what has
  already been pushed to Stripe, so `report_tenant_usage_to_stripe` sends
  only the *delta* and is itself safe to re-run (see §5).

RLS: enabled with `FORCE ROW LEVEL SECURITY` and the same
`get_tenant_context()` predicate used by the v095 remediation slice
(`_tenant_rls` helper in
`20260716_c7a1e5f2b9d4_v095_supplier_remediation_slice.py`), reused verbatim
for both tables. Regular application code paths (usage increment inside
`persist_event`, the `/billing/usage` read) already run with
`set_tenant_guc` set for the request's tenant; the periodic Stripe-reporting
job (no HTTP request/tenant context) sets it explicitly per tenant it
iterates, same pattern as `create_ingestion_run`.

### 3.3 Billing period definition (deviation — see §7)

`billing_period_start`/`_end` are **UTC calendar-month boundaries**
(`date_trunc('month', now())` .. next month), not the tenant's actual Stripe
subscription anchor day. Rationale in §7.

## 4. Usage-tracking module

New file: `services/ingestion/app/stripe_billing/usage.py`, added to the
package's existing re-export + monkeypatch-propagation machinery in
`services/ingestion/app/stripe_billing/__init__.py` (the `_ATTR_TO_SUBMODULE`
dict and `_PatchableModule`), matching how `customers.py`/`state.py`/etc. are
already wired for `monkeypatch.setattr(stripe_billing, "...", fake)` in
existing tests.

```python
# services/ingestion/app/stripe_billing/usage.py
from __future__ import annotations

from datetime import date, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import text

def _current_billing_period(as_of: Optional[date] = None) -> tuple[date, date]:
    """UTC calendar-month bucket. See DESIGN doc §3.3 for why not the
    Stripe subscription anchor."""
    ...

def increment_usage_for_event(
    session: Session,
    *,
    tenant_id: str,
    event_id: str,
    event_timestamp,  # datetime — determines which period bucket
) -> bool:
    """Idempotently count one accepted label event toward the tenant's
    current-period usage.

    Must be called with the tenant's RLS GUC already set on `session`
    (the caller — `persist_event`/`persist_events_batch` — already does
    this). Runs two statements in the caller's existing transaction:

      1. INSERT INTO billing.tenant_usage_event_ledger (...)
         ON CONFLICT (tenant_id, event_id) DO NOTHING
         RETURNING event_id
      2. Only if (1) returned a row:
         INSERT INTO billing.tenant_usage_counters
             (tenant_id, billing_period_start, billing_period_end, unit_count)
         VALUES (:tid, :start, :end, 1)
         ON CONFLICT (tenant_id, billing_period_start)
         DO UPDATE SET unit_count = tenant_usage_counters.unit_count + 1,
                        updated_at = now()

    Returns True if this call incremented the counter, False if the event
    was already counted (idempotent no-op). Never raises for a duplicate;
    only propagates real DB errors, so a failure here rolls back the
    caller's whole persist_event transaction (label counted <=> event
    persisted, atomically — no drift between the two).
    """
```

### 4.1 Wiring into `writer.py`

In `CanonicalEventStore.persist_event`, immediately after the block that
resolves `inserted = self._insert_canonical_event(event)` to a genuine new
row (i.e. `inserted is not None`, not the `existing` idempotent-replay
branches which `return` early above it) and before the `return
CanonicalStoreResult(...)` at the end of the method:

```python
if self.meter_usage:
    from app.stripe_billing.usage import increment_usage_for_event  # local import, avoids ingestion->shared coupling at module load

    increment_usage_for_event(
        self.session,
        tenant_id=tenant_id,
        event_id=str(event.event_id),
        event_timestamp=event.event_timestamp,
    )
```

`CanonicalEventStore.__init__` gains a new keyword, defaulting to `True`:
`def __init__(self, session, dual_write=True, skip_chain_write=False, meter_usage=True)`.
Default-on is deliberate: usage is tracked for **every** tenant regardless of
opt-in (cheap: two indexed upserts), so a tenant can be switched onto metered
billing later and `GET /billing/usage` immediately reflects real historical
usage for the current period — no backfill job needed. Whether that usage is
ever **reported to Stripe** is gated separately, at the reporting layer
(§5), by the tenant's opt-in flag. `meter_usage=False` exists only for tests
that construct a store without the ingestion app's `usage` module importable
(e.g. `services/shared/tests/test_canonical_persistence_chain_race_1300.py`,
which lives outside `services/ingestion` and must not gain a hard import
dependency on it).

`persist_events_batch` gets the equivalent loop, iterating only
`inserted_events` (the ones that actually landed, per the existing
`inserted_event_ids` set) — never `lost_race_events`, which the winning
concurrent writer already counted.

`services/shared/canonical_persistence/__init__.py` re-exports
`CanonicalEventStore` unchanged; no signature callers outside tests pass
`meter_usage` explicitly, so this is additive and backward compatible.

### 4.2 Why not call Stripe from inside `persist_event`

`persist_event` runs inside the request's DB transaction, holding a
per-tenant advisory lock. A live Stripe API call there would (a) hold the
lock and the transaction open for the duration of a third-party HTTP round
trip, and (b) turn a Stripe outage into an ingestion outage. Every existing
"talk to an external system after a canonical write" concern in this file
already avoids this — see `migration.stage_graph_sync`, which defers the
Neo4j publish to a SQLAlchemy `after_commit` hook specifically to keep
`persist_event` free of synchronous external calls. Usage counting follows
the same discipline: the DB increment is synchronous and local (§4), the
Stripe push is a separate, out-of-band function (§5).

## 5. Stripe reporting function

Pinned SDK: `stripe==15.5.1` (`requirements.lock`). Confirmed on this
checkout's venv: `stripe.SubscriptionItem.create_usage_record` **does not
exist** in this SDK version — the legacy usage-record API is gone. The
current API is the Billing Meters API: `stripe.billing.MeterEvent.create(
event_name: str, payload: dict[str, str], identifier: str | None, timestamp:
int | None)`. Verified by introspecting
`stripe.params.billing.MeterEventCreateParams` in the pinned package. This
is what the reporting function must use — not a guess from stale Stripe
docs.

New file: `services/ingestion/app/stripe_billing/usage_reporting.py`.

```python
"""Pushes accumulated per-tenant label usage to Stripe's Billing Meters API."""

from __future__ import annotations

import os
from typing import Optional

import stripe
import structlog
from sqlalchemy.orm import Session

from . import state as _state_mod
from .plans import METERED_ADDONS

logger = structlog.get_logger("stripe-billing.usage")

METER_EVENT_NAME = "regengine_label_events"  # must match the Meter configured in the Stripe Dashboard


def report_tenant_usage_to_stripe(session: Session, tenant_id: str) -> Optional[dict]:
    """Report this tenant's un-reported current-period usage to Stripe.

    No-ops (returns None) if the tenant is not opted into metered billing
    or has no linked Stripe customer. Safe to call repeatedly / on a
    schedule: only the (unit_count - last_reported_count) delta is ever
    sent, and the Stripe call carries a stable `identifier` derived from
    the counter's new cumulative value, so a retried call after a
    successful-but-unacknowledged Stripe response is deduplicated
    Stripe-side too (24h idempotency window on `identifier`).
    """
```

Body outline:

1. `mapping = _state_mod._get_subscription_mapping(tenant_id)`; bail if
   `mapping.get("metered_billing_enabled") != "true"` or no `customer_id`.
2. Read the current-period row from `billing.tenant_usage_counters`
   (`SELECT unit_count, last_reported_count, billing_period_start FROM
   billing.tenant_usage_counters WHERE tenant_id = :tid AND
   billing_period_start = :period_start FOR UPDATE`) — row-locked so two
   concurrent reporting runs for the same tenant can't both read the same
   pre-report `unit_count` and double-report the delta.
3. `delta = unit_count - last_reported_count`; if `delta <= 0`, return
   `None` (nothing new, or a defensive floor against a corrected/negative
   count).
4. `stripe.billing.MeterEvent.create(event_name=METER_EVENT_NAME,
   payload={"stripe_customer_id": customer_id, "value": str(delta)},
   identifier=f"{tenant_id}:{billing_period_start.isoformat()}:{unit_count}")`.
5. On success, `UPDATE billing.tenant_usage_counters SET
   last_reported_count = :unit_count, last_reported_at = now() WHERE
   tenant_id = :tid AND billing_period_start = :period_start` in the same
   transaction, then commit.
6. `stripe.error.StripeError` is caught, logged
   (`stripe_usage_report_failed`), and re-raised to the caller — the
   `last_reported_count` update never happens on failure, so the next run
   naturally retries the same delta (idempotent via the `identifier`).

### 5.1 Invocation

Spec doesn't require a scheduler; the design keeps this a plain, testable
function plus a thin internal trigger, and documents the production wiring
point rather than building it now (see §7 deviations):

- `POST /api/v1/billing/usage/report` (internal/admin permission
  `billing.usage.report`) — calls `report_tenant_usage_to_stripe` for the
  calling/target tenant. Useful for manual reconciliation and for tests
  hitting the route directly.
- Documented follow-up: a periodic job in `services/scheduler/service.py`
  (which already runs APScheduler-style jobs — see
  `services/scheduler/README.md` and `test_fsma_nightly_sync_wired.py`)
  iterating all tenants with `metered_billing_enabled = "true"` and calling
  `report_tenant_usage_to_stripe` for each, e.g. hourly. Left out of this
  slice per "keep the diff focused on your feature only" — wiring a new
  scheduler job touches a different service's job registry and is
  separable from the metering core.

## 6. API surface

All additions go into the **existing** `stripe_billing` router
(`services/ingestion/app/stripe_billing/routes.py`, prefix
`/api/v1/billing`, already mounted in `services/ingestion/main.py:453`) — no
`main.py` changes needed. Concretely: `GET /api/v1/billing/usage` (the spec
text says `GET /billing/usage`; every sibling endpoint in this router
already lives under `/api/v1/billing/...`, e.g. `/api/v1/billing/invoices`,
so the metering endpoint follows that existing prefix rather than
introducing a second bare `/billing` path).

### 6.1 `GET /api/v1/billing/usage`

```python
@router.get("/usage", response_model=UsageResponse, summary="Get current-period label usage")
async def get_usage(
    tenant_id: Optional[str] = Query(default=None, description="Optional tenant assertion; must match the credential"),
    x_tenant_id: Optional[str] = Header(default=None, alias="X-Tenant-ID"),
    principal: IngestionPrincipal = Depends(require_permission("billing.usage.read")),
    db_session=Depends(get_db_session),
) -> UsageResponse:
```

Resolves tenant via `_helpers_mod._resolve_tenant_context` (same
cross-tenant-IDOR guard as every other endpoint in this file), sets the RLS
GUC (`shared.tenant_context.set_tenant_guc`), reads the current-period row
from `billing.tenant_usage_counters` (zero-row default: `unit_count=0`), and
returns:

```python
class UsageResponse(BaseModel):
    tenant_id: str
    billing_period_start: str
    billing_period_end: str
    unit_count: int
    metered_billing_enabled: bool
    plan: str  # existing flat-tier plan, from _get_subscription_mapping
```

(`UsageResponse` added to `services/ingestion/app/stripe_billing/models.py`
next to `SubscriptionStatus`.)

### 6.2 Opt-in flag

Extends `plans.py` with a metered add-on definition, following the exact
shape of the existing `PLANS` entries (`stripe_price_env_monthly` etc.):

```python
# services/ingestion/app/stripe_billing/plans.py
METERED_ADDONS: dict[str, dict[str, Any]] = {
    "label_events": {
        "id": "label_events",
        "name": "Per-Label Metering",
        "stripe_price_env": "STRIPE_PRICE_METERED_LABEL_EVENTS",
        "meter_event_name": "regengine_label_events",
        "unit_label": "label event",
    },
}
```

`POST /api/v1/billing/usage/opt-in` (permission `billing.usage.manage`,
admin/operator only via `_enforce_admin_or_operator`, mirroring the invoice
endpoints' role gate):

1. Resolve tenant + existing `customer_id`/`subscription_id` from
   `_state_mod._get_subscription_mapping` — 400 if the tenant has no active
   flat-tier subscription yet (metering is an add-on, not a standalone
   plan, per spec item 6).
2. `stripe.SubscriptionItem.create(subscription=subscription_id,
   price=os.getenv("STRIPE_PRICE_METERED_LABEL_EVENTS"))` — attaches the
   metered Price as a second subscription item alongside the tenant's flat
   Price, same way Stripe recommends combining a flat + metered item on one
   subscription.
3. `_state_mod._store_subscription_mapping(tenant_id, {..., existing
   mapping fields ..., "metered_billing_enabled": "true",
   "metered_subscription_item_id": item.id})` — merged into the same Redis
   hash the flat-tier flow already uses, not a new store.
4. A parallel `DELETE /api/v1/billing/usage/opt-in` removes the
   subscription item and flips the flag off (kept for symmetry /
   completeness of the slice; not explicitly required by the spec but
   trivial given the above).

## 7. Deviations from the literal spec, and why

1. **Table split**: spec suggested one table
   (`billing.tenant_usage_counters` with a `last_event_id_counted`-style
   guard). Implemented as two tables (`tenant_usage_event_ledger` +
   `tenant_usage_counters`) because a single scalar "last event id" cannot
   safely de-dupe concurrent or out-of-order callers (two of the 6+ writer
   call sites can race under the per-tenant advisory lock scope, and
   `persist_events_batch` inserts many events per call, not one) — the
   `ON CONFLICT (tenant_id, event_id) DO NOTHING` ledger is the same
   idiom already used for the canonical events table itself
   (`writer.py::_insert_canonical_event`), so it's consistent with
   codebase precedent, not a novel pattern.

2. **Billing period = UTC calendar month, not the Stripe subscription
   anchor.** The Redis subscription mapping
   (`services/ingestion/app/stripe_billing/state.py`) stores
   `current_period_end` but never a `current_period_start`, and that field
   is only refreshed opportunistically (on webhook delivery or a GET that
   happens to call `stripe.Subscription.retrieve`) — it is not a reliable
   local source of the tenant's true billing anchor at arbitrary times.
   Rather than make `/billing/usage` depend on a live Stripe read (adding
   latency/failure modes to a GET) or invent brittle local anchor-tracking,
   this design reports a UTC-calendar-month bucket for local display and
   idempotency purposes. It does not affect what Stripe actually bills:
   the Meter Events pushed to Stripe are plain incremental values with no
   period metadata attached from our side — **Stripe's own meter
   aggregates them into the customer's real invoice period**, so the
   authoritative billed quantity is always correct regardless of how we
   bucket locally. The only user-visible effect is that `/billing/usage`'s
   "current period" boundary may not exactly match the invoice date for a
   tenant whose Stripe billing anchor isn't the 1st of the month. Flagged
   here rather than silently shipped; tightening this (deriving the bucket
   from the real subscription anchor) is a follow-up that doesn't change
   the schema.

3. **No scheduler wiring.** `report_tenant_usage_to_stripe` and its
   `/usage/report` trigger endpoint are built and independently testable,
   but registering a periodic job in `services/scheduler/service.py` is
   left as a documented follow-up rather than done here, per "keep the
   diff focused on your feature only" — that file belongs to a different
   service's job registry and touching it is a separable change.

4. **Endpoint path**: `/api/v1/billing/usage` instead of the spec's literal
   `/billing/usage`, to match every sibling endpoint already on this
   router (`/api/v1/billing/invoices`, `/api/v1/billing/subscription/...`).
   `GET /billing/plans` is the one existing bare-`/billing` path, and it's
   explicitly a legacy/compat alias (`include_in_schema=False`) wired
   separately in `main.py:455-457) — not the pattern to extend.

## 8. Testing plan (monkeypatch-based, no live DB/Stripe — matches
   `test_stripe_plans_1342.py` style)

- `services/ingestion/tests/test_billing_usage_core.py`:
  - `increment_usage_for_event` called twice with the same `event_id` only
    increments once (in-memory/sqlite session or a mocked `session.execute`
    call-count assertion, consistent with how
    `test_canonical_persistence_chain_race_1300.py` exercises `writer.py`
    without a live Postgres).
  - `persist_events_batch` with `meter_usage=True` increments once per
    element of `inserted_event_ids`, zero times for `lost_race_events`.
- `services/ingestion/tests/test_billing_usage_reporting.py`:
  - `report_tenant_usage_to_stripe`: monkeypatch `stripe.billing.MeterEvent.create`
    (module-level patch on `usage_reporting.stripe`, following the
    `stripe_billing.stripe` monkeypatch-propagation pattern in
    `services/ingestion/app/stripe_billing/__init__.py`) to assert the
    payload/`identifier`, that `last_reported_count` only advances on
    success, and that a `stripe.error.StripeError` leaves
    `last_reported_count` untouched.
  - `GET /api/v1/billing/usage` and the opt-in endpoints: FastAPI
    `TestClient` with `app.dependency_overrides[_get_db_session]` and
    `require_permission` overridden the way `test_webhook_router_v2_1342.py`
    /`test_canonical_router_1342.py` already do for this app.

## 9. New dependencies

None. `stripe==15.5.1` (already pinned) has everything needed
(`stripe.billing.MeterEvent`, `stripe.SubscriptionItem`). No change to
`requirements.in` / `requirements.lock`.
