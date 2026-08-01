"""#2708: seed-state marker disambiguates deny-all reads from unseeded tenants.

Pre-fix, an RLS deny-all EMPTY read on ``obligations`` (0 rows, no
exception) was indistinguishable from an unseeded tenant and routed the
obligation dimension to the 50-point "rules not loaded" assumed default.
With the v106 ``fsma.tenant_seed_state`` marker, zero live rows that
contradict the marker poison the dimension (``obligation_data_error``).
"""

from __future__ import annotations

from types import SimpleNamespace

from app.compliance_score import _query_scoring_data
from sqlalchemy.exc import OperationalError

from services.ingestion.tests.test_compliance_score_1342 import _RouteSession, _row


def _routes(obligation_count_row, marker_row=None):
    """Routes for a full _query_scoring_data pass with configurable
    obligations count and seed-marker rows."""
    route = {
        "fsma.cte_events\n            WHERE": _row(5, 3, ["harvesting"]),
        "obligation_cte_rules ocr": _row(None),
        "fsma.cte_kdes": _row(10, 10),
        "fsma.hash_chain\n            WHERE": _row(5, 5, "x"),
        "LAG(sequence_num)": _row(0),
        "EXTRACT(HOUR": _row(0),
        "FROM obligations WHERE tenant_id": obligation_count_row,
        "checkable_rules AS": _row(5, 5),
        "fsma.compliance_alerts": _row(0),
        "food_traceability_list": _row(3),
        "fsma.tenant_seed_state": marker_row,
    }
    return route


def _patch_chain(monkeypatch):
    class _FakePersistence:
        def __init__(self, s):
            pass

        def verify_chain(self, tid):
            return SimpleNamespace(valid=True, errors=[])

    import shared.cte_persistence as cte_pkg

    monkeypatch.setattr(cte_pkg, "CTEPersistence", _FakePersistence)


class TestSeedMarkerCrossCheck:
    def test_marker_contradiction_poisons_dimension(self, monkeypatch):
        """Zero obligations + marker saying 12 were seeded → fail closed."""
        _patch_chain(monkeypatch)
        session = _RouteSession(route=_routes(_row(0), marker_row=_row(12)))

        data = _query_scoring_data(session, "t1")

        assert data["obligation_count"] == 0
        assert data["obligation_data_error"] is True

    def test_no_marker_keeps_unseeded_default(self, monkeypatch):
        """Zero obligations + no marker row = genuinely unseeded tenant."""
        _patch_chain(monkeypatch)
        session = _RouteSession(route=_routes(_row(0), marker_row=None))

        data = _query_scoring_data(session, "t1")

        assert data["obligation_count"] == 0
        assert not data.get("obligation_data_error")

    def test_zero_count_marker_is_no_signal(self, monkeypatch):
        """A marker recording 0 seeded obligations corroborates nothing."""
        _patch_chain(monkeypatch)
        session = _RouteSession(route=_routes(_row(0), marker_row=_row(0)))

        data = _query_scoring_data(session, "t1")

        assert not data.get("obligation_data_error")

    def test_marker_read_failure_is_no_signal(self, monkeypatch):
        """Marker read errors log + rollback but never poison on their own."""
        _patch_chain(monkeypatch)
        session = _RouteSession(
            route=_routes(_row(0)),
            raise_on={"fsma.tenant_seed_state": OperationalError("x", None, Exception())},
        )

        data = _query_scoring_data(session, "t1")

        assert not data.get("obligation_data_error")
        assert session.rolled_back >= 1

    def test_marker_not_consulted_when_obligations_exist(self, monkeypatch):
        """Non-zero obligations read → the marker query never runs."""
        _patch_chain(monkeypatch)
        session = _RouteSession(route=_routes(_row(7), marker_row=_row(12)))

        data = _query_scoring_data(session, "t1")

        assert data["obligation_count"] == 7
        assert not any("tenant_seed_state" in sql for sql in session.executed)
