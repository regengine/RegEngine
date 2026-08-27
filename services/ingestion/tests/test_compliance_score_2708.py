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


# ---------------------------------------------------------------------------
# #2960: a chain that FAILED cryptographic verification must earn no
# export-readiness credit and must never render "FDA export ready".
# ---------------------------------------------------------------------------


class TestExportReadinessChainVerificationFailed:
    """The export-readiness chain branch handled ``chain_verified is True``
    (+40) and ``chain_verification_error`` (verification could not RUN — no
    credit, "fail closed"), then fell through to a sequence-gap check that
    awarded +30 for any chain with rows and no gaps.

    ``chain_verified is False`` — verification RAN and returned invalid —
    had no arm, so it landed on the gap check. Hash tampering rewrites
    payloads without deleting rows, so ``chain_gaps == 0`` holds for
    exactly the case that arm exists to catch: the "safe" fallback fired
    on the unsafe input, the dimension reached 90, and the detail string
    read the literal "FDA export ready" next to an issue claiming the
    chain was "not cryptographically verified" — which is the opposite of
    what happened.
    """

    @staticmethod
    def _tampered_data(**overrides):
        from services.ingestion.tests.test_compliance_score_1342 import _base_data

        data = _base_data(
            chain_verified=False,
            chain_verification_errors=["hash mismatch at sequence 7"],
            chain_length=10,
            # The load-bearing detail: tampering leaves the sequence
            # contiguous, so the old fallback predicate was satisfied.
            chain_gaps=0,
        )
        data.pop("chain_verification_error", None)
        data.update(overrides)
        return data

    def test_failed_verification_earns_no_export_credit(self):
        from app.compliance_score import _compute_scores

        scores = _compute_scores(self._tampered_data())
        score, detail = scores["export_readiness"]

        # Pre-fix this was 90 (30 chain + 30 KDEs + 30 CTE types).
        assert score == 0, f"a failed chain verification must earn no export credit, got {score}"
        assert "FDA export ready" not in detail

    def test_issue_text_distinguishes_failed_from_not_performed(self):
        from app.compliance_score import _compute_scores

        _, detail = _compute_scores(self._tampered_data())["export_readiness"]

        assert "FAILED" in detail, detail
        assert "chain not cryptographically verified" not in detail, (
            "a chain that WAS verified and failed must not be described as unverified"
        )

    def test_verification_could_not_run_is_still_distinct(self):
        """The pre-existing ``chain_verification_error`` arm is unchanged:
        verification that could not RUN still reports 'unavailable', not
        'FAILED'.
        """
        from app.compliance_score import _compute_scores

        data = self._tampered_data(chain_verified=None)
        data["chain_verification_error"] = "connection refused"

        _, detail = _compute_scores(data)["export_readiness"]
        assert "chain verification unavailable" in detail
        assert "FAILED" not in detail

    def test_intact_verified_chain_is_unaffected(self):
        """Regression guard: the happy path still reaches FDA-export-ready."""
        from app.compliance_score import _compute_scores

        from services.ingestion.tests.test_compliance_score_1342 import _base_data

        score, detail = _compute_scores(_base_data(chain_verified=True))["export_readiness"]
        assert score >= 80
        assert detail == "FDA export ready"

    def test_tamper_is_still_reported_by_the_chain_dimension(self):
        """The same response must keep saying TAMPER DETECTED — this fix
        changes the export dimension only.
        """
        from app.compliance_score import _compute_scores

        chain_score, chain_detail = _compute_scores(self._tampered_data())["chain_integrity"]
        assert "TAMPER DETECTED" in chain_detail
        assert chain_score < 100
