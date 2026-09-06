"""Regression tests for #2902 — the batch write path silently dropped alerts.

Before the fix, ``store_events_batch`` read ``evt.get("alerts")``
(``batch.py:163``) and fed the result to ``_derive_validation_status``, but the
batch path contained **no** ``fsma.compliance_alerts`` INSERT at all — a
repo-wide grep over ``services/shared/cte_persistence/`` returned exactly one
alerts writer, the single-event path at ``writes.py:368``.

The consequence was a batch/single divergence on a data-integrity field: the
same event persisted through ``store_event`` produced ``validation_status
= 'warning'`` plus an alert row, while through ``store_events_batch`` it
produced ``'valid'`` and no row. ``validation_status`` feeds downstream
compliance scoring, so the divergence was durable loss of compliance evidence.

These tests pin the alert INSERT, the derived status, and the parity between
the two write paths. They also pin the lost-race guard: an alert must never be
written for an event whose ``cte_events`` INSERT lost the idempotency race,
which would leave the alert pointing at a row this writer never created (the
same orphan-row class of bug that #1307 fixed for ``fsma.hash_chain``).
"""

from __future__ import annotations

import re

from shared.cte_persistence.core import CTEPersistence

from tests.shared.test_cte_persistence_hardening import (
    FakeSession,
    _base_event,
    _FakeResult,
)

_ALERTS_INSERT = re.compile(r"INSERT INTO fsma\.compliance_alerts", re.IGNORECASE)

_INCOMPLETE_ROUTE = {
    "severity": "warning",
    "alert_type": "incomplete_route",
    "message": "Shipping/receiving event missing source or destination identifiers",
}


def _batch_session(*, insert_all: bool = True) -> FakeSession:
    """A FakeSession wired for one successful ``store_events_batch`` call."""
    session = FakeSession()
    session.add_rule(r"SELECT idempotency_key", _FakeResult(rows=[]))
    session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))

    def _insert(sql, params):
        if not insert_all:
            # Simulate losing the idempotency race for every row.
            return _FakeResult(rows=[])
        n = sum(1 for k in params if k.startswith("id_"))
        return _FakeResult(rows=[(params[f"id_{i}"],) for i in range(n)])

    session.add_rule(r"INSERT INTO fsma\.cte_events", _insert)
    return session


def _alert_inserts(session: FakeSession) -> list[tuple[str, dict]]:
    return [(sql, params) for sql, params in session.calls if _ALERTS_INSERT.search(sql)]


def _cte_event_insert_params(session: FakeSession) -> dict:
    for sql, params in session.calls:
        if re.search(r"INSERT INTO fsma\.cte_events", sql, re.IGNORECASE):
            return params
    raise AssertionError("no fsma.cte_events INSERT was issued")


# ---------------------------------------------------------------------------
# 1) The batch path must write the alert row at all
# ---------------------------------------------------------------------------


class TestBatchWritesComplianceAlerts_Issue2902:
    def test_batch_persists_compliance_alert_row(self):
        """An event carrying an alert must produce an fsma.compliance_alerts row.

        Pre-fix this asserts zero INSERTs — the batch path had no alerts
        writer whatsoever.
        """
        session = _batch_session()
        p = CTEPersistence(session=session)

        results = p.store_events_batch(
            tenant_id="t-1",
            events=[_base_event(alerts=[dict(_INCOMPLETE_ROUTE)])],
        )

        inserts = _alert_inserts(session)
        assert len(inserts) == 1, (
            f"batch path must INSERT the generated compliance alert; got {len(inserts)} alert INSERTs"
        )
        _sql, params = inserts[0]
        assert params["event_id"] == results[0].event_id
        assert params["tenant_id"] == "t-1"
        assert params["severity"] == "warning"
        assert params["message"] == _INCOMPLETE_ROUTE["message"]

    def test_batch_derives_warning_status_from_alerts(self):
        """validation_status must be 'warning', not the unearned 'valid'."""
        session = _batch_session()
        p = CTEPersistence(session=session)

        p.store_events_batch(
            tenant_id="t-1",
            events=[_base_event(alerts=[dict(_INCOMPLETE_ROUTE)])],
        )

        assert _cte_event_insert_params(session)["vs_0"] == "warning"

    def test_batch_with_no_alerts_writes_no_alert_row(self):
        """The writer must stay silent when there is genuinely nothing to say."""
        session = _batch_session()
        p = CTEPersistence(session=session)

        p.store_events_batch(tenant_id="t-1", events=[_base_event()])

        assert _alert_inserts(session) == []
        assert _cte_event_insert_params(session)["vs_0"] == "valid"

    def test_batch_writes_one_row_per_alert_per_event(self):
        """Two events, two alerts each → four rows, each keyed to its own event."""
        session = _batch_session()
        p = CTEPersistence(session=session)

        alerts = [
            dict(_INCOMPLETE_ROUTE),
            {"severity": "warning", "alert_type": "missing_kde", "message": "second"},
        ]
        results = p.store_events_batch(
            tenant_id="t-1",
            events=[
                _base_event(traceability_lot_code="TLC-A", alerts=[dict(a) for a in alerts]),
                _base_event(traceability_lot_code="TLC-B", alerts=[dict(a) for a in alerts]),
            ],
        )

        inserts = _alert_inserts(session)
        assert len(inserts) == 4
        written = {(p_["event_id"], p_["message"]) for _s, p_ in inserts}
        assert written == {
            (results[0].event_id, _INCOMPLETE_ROUTE["message"]),
            (results[0].event_id, "second"),
            (results[1].event_id, _INCOMPLETE_ROUTE["message"]),
            (results[1].event_id, "second"),
        }


# ---------------------------------------------------------------------------
# 2) Parity with the single-event path (writes.py)
# ---------------------------------------------------------------------------


class TestBatchSingleAlertParity_Issue2902:
    """Identical input through either write path must persist identically.

    The divergence #2902 describes is the whole defect: which internal code
    path ran (batch vs the per-event fallback the router drops to when the
    batch INSERT raises) must not change what lands in the database.
    """

    def _single_session(self) -> FakeSession:
        session = FakeSession()
        session.add_rule(r"SELECT id FROM fsma\.cte_events", _FakeResult(rows=[]))
        session.add_rule(r"FROM fsma\.hash_chain", _FakeResult(rows=[]))
        session.add_rule(r"SELECT id, sha256_hash", _FakeResult(rows=[]))
        return session

    def test_alert_row_columns_match_single_event_path(self):
        batch_session = _batch_session()
        CTEPersistence(session=batch_session).store_events_batch(
            tenant_id="t-1",
            events=[_base_event(alerts=[dict(_INCOMPLETE_ROUTE)])],
        )

        single_session = self._single_session()
        CTEPersistence(session=single_session).store_event(
            tenant_id="t-1",
            event_type="harvesting",
            traceability_lot_code="TLC-1",
            product_description="Lettuce",
            quantity=10.0,
            unit_of_measure="kg",
            event_timestamp="2026-04-15T12:00:00Z",
            kdes={"farm_name": "Acme"},
            alerts=[dict(_INCOMPLETE_ROUTE)],
        )

        batch_inserts = _alert_inserts(batch_session)
        single_inserts = _alert_inserts(single_session)
        assert len(batch_inserts) == len(single_inserts) == 1

        batch_params = dict(batch_inserts[0][1])
        single_params = dict(single_inserts[0][1])
        # Each path creates its own event; both anchors must bind that event.
        assert batch_params.pop("cte_event_id") == batch_params.pop("event_id")
        assert single_params.pop("cte_event_id") == single_params.pop("event_id")
        assert batch_params == single_params, "batch and single-event alert rows must carry identical columns"

    def test_unknown_alert_type_is_mapped_the_same_way(self):
        """``incomplete_route`` is not in the writer's accepted alert_type set.

        The single-event path folds unknown types to ``missing_kde``; the batch
        path must fold them identically or the two paths write different
        ``alert_type`` values for the same input.
        """
        session = _batch_session()
        CTEPersistence(session=session).store_events_batch(
            tenant_id="t-1",
            events=[_base_event(alerts=[dict(_INCOMPLETE_ROUTE)])],
        )
        assert _alert_inserts(session)[0][1]["alert_type"] == "missing_kde"

    def test_known_alert_type_is_preserved(self):
        """``chain_break`` is accepted and must survive verbatim.

        compliance_score.py filters on ``alert_type = 'chain_break'`` to count
        open obligation gaps, so folding this one would erase the signal.
        """
        session = _batch_session()
        CTEPersistence(session=session).store_events_batch(
            tenant_id="t-1",
            events=[
                _base_event(
                    alerts=[
                        {
                            "severity": "warning",
                            "alert_type": "chain_break",
                            "message": "Obligation not met",
                        }
                    ]
                )
            ],
        )
        assert _alert_inserts(session)[0][1]["alert_type"] == "chain_break"


# ---------------------------------------------------------------------------
# 3) Fail closed — no alert rows for events this writer did not insert
# ---------------------------------------------------------------------------


class TestBatchAlertsSkipNonInsertedEvents_Issue2902:
    def test_lost_race_event_gets_no_alert_row(self):
        """A row that lost the ON CONFLICT race must not get an alert.

        ``store_events_batch`` reconciles lost-race rows to the *winner's*
        event_id (#1248). Writing our alert against our own discarded uuid
        would leave an alert pointing at a row that does not exist — the
        orphan-row bug #1307 fixed for fsma.hash_chain.
        """
        session = _batch_session(insert_all=False)
        session.add_rule(
            r"SELECT idempotency_key, id, sha256_hash",
            _FakeResult(rows=[]),
        )
        CTEPersistence(session=session).store_events_batch(
            tenant_id="t-1",
            events=[_base_event(alerts=[dict(_INCOMPLETE_ROUTE)])],
        )

        assert _alert_inserts(session) == [], (
            "no alert row may be written for an event whose cte_events INSERT did not land"
        )

    def test_rejected_event_gets_no_alert_row(self):
        """A rejected event writes no KDEs and no chain row — nor alerts.

        A 'critical' alert drives validation_status to 'rejected'
        (core._REJECT_SEVERITIES). The event row is still written for audit,
        but the batch path must not also emit an alert row the single-event
        path would never produce for a rejected write.
        """
        session = _batch_session()
        CTEPersistence(session=session).store_events_batch(
            tenant_id="t-1",
            events=[
                _base_event(
                    alerts=[
                        {
                            "severity": "critical",
                            "alert_type": "chain_break",
                            "message": "hard fail",
                        }
                    ]
                )
            ],
        )

        assert _cte_event_insert_params(session)["vs_0"] == "rejected"
        assert _alert_inserts(session) == []
