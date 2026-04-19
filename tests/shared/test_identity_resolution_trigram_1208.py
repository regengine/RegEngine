"""Regression tests for #1208 — pg_trgm pre-filter for find_potential_matches.

Before: ``find_potential_matches`` pulled every name/trade_name/abbrev
alias for the tenant into Python and ran SequenceMatcher pairwise —
multi-second per call at 100K aliases, directly on the ingestion hot
path.

After:
- Case-insensitive path issues a SQL ``similarity(lower(alias_value), :q)``
  pre-filter (backed by GIN/pg_trgm index from migration v070) that
  returns the top ``candidate_pool = max(limit * 20, 100)`` rows.
- Python re-scores the candidate set with SequenceMatcher for
  authoritative tie-breaking and threshold enforcement.
- If the extension/index is absent, the catch block reverts to the
  pre-#1208 full-scan query — correctness preserved, perf win lost.
- Case-sensitive callers continue to use the full-scan path because
  the trigram index is on ``lower(alias_value)``.

Session-mocked — no real DB required.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock

import pytest

from services.shared.identity_resolution import IdentityResolutionService


TENANT = "tenant-1208"


def _row(
    entity_id: str,
    alias_value: str,
    entity_type: str = "facility",
    canonical_name: Optional[str] = None,
    gln: Optional[str] = None,
    gtin: Optional[str] = None,
    verification_status: str = "unverified",
    confidence_score: float = 1.0,
) -> Tuple[Any, ...]:
    """Build a row in the (entity_id, entity_type, canonical_name,
    gln, gtin, verification_status, confidence_score, alias_value)
    tuple shape returned by the SELECT."""
    return (
        entity_id,
        entity_type,
        canonical_name or alias_value,
        gln,
        gtin,
        verification_status,
        confidence_score,
        alias_value,
    )


class _CapturingSession:
    """Fake session capturing SQL strings + params, returning scripted
    rows.

    ``trigram_rows`` returned when the SQL contains ``similarity(``
    (the #1208 fast path). ``fallback_rows`` returned otherwise. If
    ``trigram_raises`` is True, the trigram execute raises — exercising
    the fallback.
    """

    def __init__(
        self,
        trigram_rows: Optional[List[Tuple[Any, ...]]] = None,
        fallback_rows: Optional[List[Tuple[Any, ...]]] = None,
        trigram_raises: bool = False,
    ):
        self.trigram_rows = trigram_rows or []
        self.fallback_rows = fallback_rows or []
        self.trigram_raises = trigram_raises
        self.calls: List[Dict[str, Any]] = []

    def execute(self, stmt, params=None):
        sql = str(stmt)
        entry = {"sql": sql, "params": dict(params or {})}
        self.calls.append(entry)
        if "similarity(" in sql:
            entry["kind"] = "trigram"
            if self.trigram_raises:
                raise RuntimeError("pg_trgm: function similarity(text, text) does not exist")
            result = MagicMock()
            result.fetchall.return_value = self.trigram_rows
            return result
        entry["kind"] = "fallback"
        result = MagicMock()
        result.fetchall.return_value = self.fallback_rows
        return result


def _svc(session):
    return IdentityResolutionService(session)


# ===========================================================================
# Fast path: SQL uses pg_trgm similarity() predicate
# ===========================================================================


class TestTrigramFastPath_Issue1208:
    def test_case_insensitive_uses_trigram_sql(self):
        """The default (case_sensitive=False) must issue a trigram-aware
        SQL query so the DB narrows to a candidate pool before Python
        re-scores."""
        session = _CapturingSession(
            trigram_rows=[_row("e1", "Acme Foods Inc")],
        )
        _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme foods"
        )
        # Exactly one query — the trigram one.
        assert len(session.calls) == 1
        assert session.calls[0]["kind"] == "trigram"
        sql = session.calls[0]["sql"]
        # Must include similarity() pre-filter and an ORDER BY.
        assert "similarity(lower(ea.alias_value), :q)" in sql
        assert "ORDER BY similarity" in sql
        assert "LIMIT :cand_limit" in sql

    def test_candidate_pool_scales_with_limit(self):
        """candidate_pool = max(limit * 20, 100)."""
        session = _CapturingSession(trigram_rows=[])
        _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme", limit=10
        )
        assert session.calls[0]["params"]["cand_limit"] == 200

        session2 = _CapturingSession(trigram_rows=[])
        _svc(session2).find_potential_matches(
            tenant_id=TENANT, search_name="acme", limit=3
        )
        # max(3*20=60, 100) = 100
        assert session2.calls[0]["params"]["cand_limit"] == 100

    def test_sim_floor_is_lenient_vs_threshold(self):
        """sim_floor must be strictly less than the caller's threshold
        so we don't under-recall."""
        session = _CapturingSession(trigram_rows=[])
        _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme", threshold=0.9
        )
        params = session.calls[0]["params"]
        assert params["sim_floor"] < 0.9
        assert params["sim_floor"] >= 0.2  # absolute floor

    def test_search_query_param_is_lowered(self):
        """The ``:q`` param must already be lowered (matches the
        index on ``lower(alias_value)``)."""
        session = _CapturingSession(trigram_rows=[])
        _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="  ACME Foods  "
        )
        assert session.calls[0]["params"]["q"] == "acme foods"


# ===========================================================================
# Python re-score still applies threshold + dedup
# ===========================================================================


class TestPythonRescoreSemantics_Issue1208:
    def test_threshold_still_prunes_trigram_candidates(self):
        """The SQL pre-filter is lenient — Python re-score must still
        drop candidates below the caller's ``threshold``."""
        # Acme Foods is a close match; "Totally Unrelated Widget Co" is
        # not (would have been filtered by sim_floor but simulate the
        # DB returning it anyway to prove Python enforces threshold).
        session = _CapturingSession(
            trigram_rows=[
                _row("e-good", "Acme Foods Inc"),
                _row("e-bad", "Totally Unrelated Widget Co"),
            ]
        )
        results = _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme foods", threshold=0.6
        )
        entity_ids = [r["entity_id"] for r in results]
        assert "e-good" in entity_ids
        assert "e-bad" not in entity_ids

    def test_duplicate_entity_keeps_highest_scoring_alias(self):
        """Multiple aliases for the same entity must dedupe to one
        result with the best-scoring alias."""
        session = _CapturingSession(
            trigram_rows=[
                _row("e-same", "Acme Foods"),
                _row("e-same", "Acme Foods Inc"),  # slightly further from "acme foods"
                _row("e-same", "ACM"),
            ]
        )
        results = _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme foods", threshold=0.4
        )
        assert len(results) == 1
        assert results[0]["entity_id"] == "e-same"
        # Best-scoring alias is the exact "Acme Foods".
        assert results[0]["matched_alias"] == "Acme Foods"

    def test_results_sorted_desc_by_confidence(self):
        """Final result list must be sorted by confidence descending."""
        session = _CapturingSession(
            trigram_rows=[
                _row("e1", "Acme Widgets"),
                _row("e2", "Acme Foods Inc"),
                _row("e3", "Acme Foods"),
            ]
        )
        results = _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme foods", threshold=0.3
        )
        confs = [r["confidence"] for r in results]
        assert confs == sorted(confs, reverse=True)

    def test_limit_trims_final_list(self):
        """``limit`` must trim the AFTER-rescore list, not just the
        trigram candidate pool."""
        session = _CapturingSession(
            trigram_rows=[_row(f"e{i}", f"Acme Foods {i}") for i in range(50)]
        )
        results = _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme foods", limit=5, threshold=0.3
        )
        assert len(results) == 5


# ===========================================================================
# Fallback: pg_trgm unavailable → full-scan path
# ===========================================================================


class TestFallbackOnTrigramFailure_Issue1208:
    def test_trigram_error_falls_back_to_full_scan(self):
        """If the trigram execute raises (e.g. ``similarity()`` missing),
        the service must fall back to the pre-#1208 scan and still
        return correct results."""
        session = _CapturingSession(
            trigram_rows=[],
            fallback_rows=[_row("e1", "Acme Foods")],
            trigram_raises=True,
        )
        results = _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme foods"
        )
        kinds = [c["kind"] for c in session.calls]
        assert kinds == ["trigram", "fallback"], (
            f"expected trigram->fallback, got {kinds}"
        )
        assert len(results) == 1
        assert results[0]["entity_id"] == "e1"

    def test_case_sensitive_skips_trigram_entirely(self):
        """The trigram index is on ``lower(alias_value)`` — case-sensitive
        callers must use the full-scan path directly, not attempt the
        trigram query and then fall back."""
        session = _CapturingSession(
            fallback_rows=[_row("e1", "ACME Foods")],
        )
        results = _svc(session).find_potential_matches(
            tenant_id=TENANT,
            search_name="ACME Foods",
            case_sensitive=True,
        )
        kinds = [c["kind"] for c in session.calls]
        assert kinds == ["fallback"], (
            f"case_sensitive should skip trigram; got {kinds}"
        )
        assert len(results) == 1

    def test_empty_search_string_uses_fallback(self):
        """An empty (post-strip) search string has no trigrams to
        match; the service must not issue a similarity() query with
        an empty :q parameter."""
        session = _CapturingSession(fallback_rows=[])
        _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="   "
        )
        kinds = [c["kind"] for c in session.calls]
        assert kinds == ["fallback"]


# ===========================================================================
# Contract preservation — existing guards still fire
# ===========================================================================


class TestExistingContractsPreserved_Issue1208:
    def test_invalid_entity_type_still_rejected(self):
        """``entity_type`` whitelist validation must still fire before
        any SQL is issued."""
        session = _CapturingSession()
        with pytest.raises(ValueError, match="Invalid entity_type"):
            _svc(session).find_potential_matches(
                tenant_id=TENANT,
                search_name="acme",
                entity_type="nonsense",
            )
        assert session.calls == []

    def test_tenant_id_always_bound_as_param(self):
        """Both trigram and fallback paths must bind ``tenant_id`` as a
        parameter — never string-interpolated."""
        session = _CapturingSession(trigram_rows=[])
        _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme"
        )
        assert session.calls[0]["params"]["tenant_id"] == TENANT
        assert ":tenant_id" in session.calls[0]["sql"]
        # And the tenant string itself should NOT appear literally in
        # the SQL — that would mean it was interpolated.
        assert TENANT not in session.calls[0]["sql"]

    def test_entity_type_bound_as_nullable_param(self):
        """#1191 shape — ``entity_type`` is passed as a parameter so
        the single static SQL string handles both filtered and
        unfiltered lookups."""
        session = _CapturingSession(trigram_rows=[])
        _svc(session).find_potential_matches(
            tenant_id=TENANT,
            search_name="acme",
            entity_type="facility",
        )
        assert session.calls[0]["params"]["entity_type"] == "facility"
        assert ":entity_type" in session.calls[0]["sql"]

        session2 = _CapturingSession(trigram_rows=[])
        _svc(session2).find_potential_matches(
            tenant_id=TENANT, search_name="acme"
        )
        assert session2.calls[0]["params"]["entity_type"] is None

    def test_return_shape_unchanged(self):
        """Result dicts must still carry the documented fields so
        callers relying on ``entity_id`` / ``confidence`` / etc. don't
        break."""
        session = _CapturingSession(
            trigram_rows=[
                _row(
                    "e1",
                    "Acme Foods",
                    entity_type="facility",
                    gln="0123456789012",
                    gtin="9876543210987",
                    verification_status="verified",
                    confidence_score=0.95,
                )
            ]
        )
        results = _svc(session).find_potential_matches(
            tenant_id=TENANT, search_name="acme foods"
        )
        assert len(results) == 1
        r = results[0]
        assert set(r) >= {
            "entity_id",
            "entity_type",
            "canonical_name",
            "gln",
            "gtin",
            "verification_status",
            "entity_confidence",
            "confidence",
            "matched_alias",
        }
        assert r["entity_id"] == "e1"
        assert r["gln"] == "0123456789012"
        assert r["confidence"] <= 1.0
        assert r["matched_alias"] == "Acme Foods"
