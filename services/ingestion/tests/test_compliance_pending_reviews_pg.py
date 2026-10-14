"""Pending-review counts run against the real exception and rule tables, tested on live Postgres.

``GET /api/v1/compliance/pending-reviews/{tenant_id}`` counts events with an
unresolved failed critical rule. The count skips an event once a resolved or
waived exception case links it. ``fsma.exception_cases.linked_event_ids`` is
``UUID[]`` (V045) and ``fsma.rule_evaluations.event_id`` is ``UUID`` (V044).
The containment predicate was written as

    ec.linked_event_ids @> ARRAY[re.event_id]::text[]

Postgres has no ``uuid[] @> text[]`` operator, so it rejected the statement
with "operator does not exist: uuid[] @> text[]". The handler's broad
``except`` then turned the error into HTTP 503 for every tenant on every
call. Before #2705 the same ``except`` returned HTTP 200 with
``pending_reviews=0``, which hid the error. The request-workflow blocker
check (``shared/request_workflow/assembly.py``) has always used the correct
form, ``ec.linked_event_ids @> ARRAY[re.event_id]``.

The unit tests in ``test_compliance_score_1342.py`` route a fake session on
SQL substrings and never parse the SQL, so they passed throughout. This
module runs the real handler against a real cluster at alembic head. Each
scenario runs twice:

* ``superuser``: as the migration owner, which bypasses RLS. Only the
  statement's own ``tenant_id`` predicates keep other tenants out.
* ``runtime_role``: as ``regengine``, the NOBYPASSRLS role the app connects
  as, with ``app.tenant_id`` set. FORCE RLS applies, as in production.

Runs in ``backend-ci.yml``'s ``ingestion-full-suite`` job, in the step
"Run ingestion live-Postgres tests against alembic head". That step uses the
alembic-head ``remediation_test`` database with ``REGENGINE_REQUIRE_DB=1``,
so an unreachable database fails the step instead of skipping (#2530). The
job's main xdist step and the per-service ``Test ingestion`` job also collect
this module. They set no ``REMEDIATION_TEST_SUPERUSER_DSN``, so it skips
there by design, as it does locally when no migrated Postgres is reachable.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from shared.db_url import sync_postgres_url

service_dir = Path(__file__).parent.parent
sys.path.insert(0, str(service_dir))

DSN = os.environ.get(
    "REMEDIATION_TEST_SUPERUSER_DSN",
    "postgresql://regengine:regengine@localhost:55432/regengine",  # pragma: allowlist secret — throwaway scratch-DB role
)

RUNTIME_ROLE = "regengine"
READERS = ("superuser", "runtime_role")


def _schema_ready(dsn: str) -> bool:
    """True when a migrated database carrying the tables the endpoint counts is up."""
    from sqlalchemy import create_engine, text

    try:
        engine = create_engine(sync_postgres_url(dsn), pool_pre_ping=True)
        with engine.connect() as conn:
            found = conn.execute(
                text(
                    "SELECT to_regclass('fsma.rule_evaluations') IS NOT NULL "
                    "AND to_regclass('fsma.rule_definitions') IS NOT NULL "
                    "AND to_regclass('fsma.exception_cases') IS NOT NULL "
                    "AND to_regclass('fsma.request_cases') IS NOT NULL"
                )
            ).scalar()
        engine.dispose()
        return bool(found)
    except Exception:
        return False


_DB_READY = _schema_ready(DSN)

if not _DB_READY and os.environ.get("REGENGINE_REQUIRE_DB") == "1":
    raise RuntimeError(f"REGENGINE_REQUIRE_DB=1 but no migrated Postgres is reachable at {DSN!r} — refusing to skip.")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _DB_READY, reason="migrated Postgres with fsma schema not available"),
]


@pytest.fixture()
def conn(monkeypatch):
    """A connection whose transaction is rolled back, with the handler's sessions bound to it.

    Seeded rows are never committed. The handler's session runs in a
    savepoint of this transaction, sees the seeded rows, and the whole
    transaction is rolled back at teardown. ``get_pending_reviews`` imports
    ``SessionLocal`` from ``shared.database`` at call time, so the attribute
    is patched there.
    """
    import shared.database as db_mod
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(sync_postgres_url(DSN))
    with engine.connect() as connection:
        outer = connection.begin()
        monkeypatch.setattr(
            db_mod,
            "SessionLocal",
            sessionmaker(bind=connection, join_transaction_mode="create_savepoint"),
        )
        try:
            yield connection
        finally:
            outer.rollback()
    engine.dispose()


# ---------------------------------------------------------------------------
# Seeding helpers. They run as the connecting superuser, before any role switch.
# ---------------------------------------------------------------------------


def _seed_rule(conn, severity: str) -> str:
    """A rule definition (rule definitions are global, not per tenant)."""
    from sqlalchemy import text

    rule_id = str(uuid.uuid4())
    conn.execute(
        text(
            """
            INSERT INTO fsma.rule_definitions
                (rule_id, rule_version, title, severity, category, failure_reason_template)
            VALUES (:rule_id, 1, :title, :severity, 'kde_presence', 'pytest pending-reviews rule failed')
            """
        ),
        {"rule_id": rule_id, "title": f"pytest pending-reviews {severity} {rule_id}", "severity": severity},
    )
    return rule_id


def _seed_evaluation(conn, tenant_id: str, event_id: str, rule_id: str, result: str = "fail") -> None:
    from sqlalchemy import text

    conn.execute(
        text(
            """
            INSERT INTO fsma.rule_evaluations (tenant_id, event_id, rule_id, rule_version, result, why_failed)
            VALUES (:tenant_id, :event_id, :rule_id, 1, :result, 'pytest pending-reviews')
            """
        ),
        {"tenant_id": tenant_id, "event_id": event_id, "rule_id": rule_id, "result": result},
    )


def _seed_exception(conn, tenant_id: str, status: str, event_ids: list) -> None:
    """An exception case linking ``event_ids``, bound the way ``exception_queue.create_exception`` binds them."""
    from sqlalchemy import text

    conn.execute(
        text(
            """
            INSERT INTO fsma.exception_cases (tenant_id, severity, status, linked_event_ids)
            VALUES (:tenant_id, 'critical', :status, CAST(:event_ids AS uuid[]))
            """
        ),
        {"tenant_id": tenant_id, "status": status, "event_ids": event_ids},
    )


def _new_id() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Reading through the real handler
# ---------------------------------------------------------------------------


def _read_as(conn, reader: str, tenant_id: str) -> None:
    """Switch the rest of the transaction to ``reader`` and bind the tenant GUC, as the request path does."""
    from shared.tenant_context import set_tenant_guc
    from sqlalchemy import text

    if reader == "runtime_role":
        if not conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": RUNTIME_ROLE}).scalar():
            pytest.fail(f"{RUNTIME_ROLE} role not present — this database is not prod-shaped")
        conn.execute(text(f"SET LOCAL ROLE {RUNTIME_ROLE}"))
        assert conn.execute(text("SELECT current_user")).scalar() == RUNTIME_ROLE
    set_tenant_guc(conn, tenant_id)


def _pending_reviews(tenant_id: str, caplog) -> dict:
    """Call the endpoint coroutine. A 503 fails the test and names the logged database error."""
    from app import compliance_score as cs
    from fastapi import HTTPException

    with caplog.at_level(logging.ERROR, logger="compliance-score"):
        try:
            return asyncio.run(cs.get_pending_reviews(tenant_id, ctx=SimpleNamespace(tenant_id=tenant_id)))
        except HTTPException as exc:
            logged = [
                record.getMessage().splitlines()[0] for record in caplog.records if record.name == "compliance-score"
            ]
            pytest.fail(f"GET /pending-reviews returned HTTP {exc.status_code} ({exc.detail!r}); logged: {logged}")


# ---------------------------------------------------------------------------
# One failed critical evaluation, linked by one exception case of each status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reader", READERS)
@pytest.mark.parametrize(
    ("status", "still_pending"),
    [
        ("resolved", False),
        ("waived", False),
        ("open", True),
        ("in_review", True),
        ("awaiting_supplier", True),
    ],
)
def test_an_exception_case_clears_a_critical_failure_only_once_resolved_or_waived(
    conn, caplog, reader, status, still_pending
):
    """A resolved or waived case linking the event clears it. An unresolved one leaves it pending."""
    tenant_id, event_id = _new_id(), _new_id()
    critical_rule = _seed_rule(conn, "critical")
    _seed_evaluation(conn, tenant_id, event_id, critical_rule)
    _seed_exception(conn, tenant_id, status, [event_id])
    _read_as(conn, reader, tenant_id)

    body = _pending_reviews(tenant_id, caplog)

    unresolved = 0 if status in ("resolved", "waived") else 1
    assert body["breakdown"] == {
        "unresolved_exceptions": unresolved,
        "identity_reviews": 0,
        "active_requests": 0,
        "critical_failures": 1 if still_pending else 0,
    }
    assert body["pending_reviews"] == unresolved + (1 if still_pending else 0)
    assert body["tenant_id"] == tenant_id
    assert body["db_available"] is True


# ---------------------------------------------------------------------------
# A mixed tenant, next to another tenant whose rows would change every count
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reader", READERS)
def test_critical_failures_count_each_uncleared_event_once_for_the_tenant_only(conn, caplog, reader):
    """Only failed critical evaluations count, each event once, and only another case of the same tenant clears one."""
    tenant_id, other_tenant_id = _new_id(), _new_id()
    critical_rule, second_critical_rule = _seed_rule(conn, "critical"), _seed_rule(conn, "critical")
    warning_rule = _seed_rule(conn, "warning")

    resolved_event, waived_event, open_event, bare_event = (_new_id() for _ in range(4))
    twice_failed_event, warning_event, passed_event, cleared_elsewhere_event = (_new_id() for _ in range(4))

    # Still pending (3): an open case, no case, and two failed critical rules on one event.
    _seed_evaluation(conn, tenant_id, open_event, critical_rule)
    _seed_exception(conn, tenant_id, "open", [open_event])
    _seed_evaluation(conn, tenant_id, bare_event, critical_rule)
    _seed_evaluation(conn, tenant_id, twice_failed_event, critical_rule)
    _seed_evaluation(conn, tenant_id, twice_failed_event, second_critical_rule)
    # Still pending (1): resolved, but by ANOTHER tenant's case. Only a case of the same tenant clears an event.
    _seed_evaluation(conn, tenant_id, cleared_elsewhere_event, critical_rule)
    _seed_exception(conn, other_tenant_id, "resolved", [cleared_elsewhere_event])

    # Cleared: a resolved case linking the event among others, and a waived case.
    _seed_evaluation(conn, tenant_id, resolved_event, critical_rule)
    _seed_exception(conn, tenant_id, "resolved", [_new_id(), resolved_event, _new_id()])
    _seed_evaluation(conn, tenant_id, waived_event, critical_rule)
    _seed_exception(conn, tenant_id, "waived", [waived_event])

    # Never counted: a warning-severity failure and a passed critical evaluation.
    _seed_evaluation(conn, tenant_id, warning_event, warning_rule)
    _seed_evaluation(conn, tenant_id, passed_event, critical_rule, result="pass")

    # The other tenant: a lost tenant filter would add these to every count.
    for _ in range(5):
        _seed_evaluation(conn, other_tenant_id, _new_id(), critical_rule)
    _seed_exception(conn, other_tenant_id, "open", [_new_id()])

    _read_as(conn, reader, tenant_id)

    body = _pending_reviews(tenant_id, caplog)

    assert body["breakdown"] == {
        "unresolved_exceptions": 1,  # the open case on open_event
        "identity_reviews": 0,
        "active_requests": 0,
        "critical_failures": 4,  # open_event, bare_event, twice_failed_event, cleared_elsewhere_event
    }
    assert body["pending_reviews"] == 5


@pytest.mark.parametrize("reader", READERS)
def test_a_tenant_with_no_rows_gets_zero_counts_not_an_error(conn, caplog, reader):
    """Zero counts while another tenant has failures and cases."""
    other_tenant_id, other_event = _new_id(), _new_id()
    _seed_evaluation(conn, other_tenant_id, other_event, _seed_rule(conn, "critical"))
    _seed_exception(conn, other_tenant_id, "open", [other_event])
    tenant_id = _new_id()
    _read_as(conn, reader, tenant_id)

    body = _pending_reviews(tenant_id, caplog)

    assert body["pending_reviews"] == 0
    assert body["breakdown"] == {
        "unresolved_exceptions": 0,
        "identity_reviews": 0,
        "active_requests": 0,
        "critical_failures": 0,
    }
