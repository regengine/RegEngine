"""WS-1b (#1335) — chain-verification cutover contract, data-free.

Pins the parts of the legacy/canonical chain-verifier cutover that need no
records:

* both result types expose the ``.valid``/``.errors`` surface the consumers
  (compliance_score, FDA export handlers) rely on;
* ``CHAIN_VERIFY_READ_CANONICAL`` defaults ON (#3039) and ``0`` rolls back;
* ``_verify_chain_for_export`` routes to the legacy verifier on rollback;
* chain hashing of empty input is deterministic.
"""

from __future__ import annotations

import inspect


class TestChainVerifyContract:
    def test_both_result_types_expose_consumer_surface(self):
        from shared.canonical_persistence.verification import CanonicalChainVerification
        from shared.cte_persistence.models import ChainVerification

        for result_type in (ChainVerification, CanonicalChainVerification):
            assert "valid" in result_type.__slots__
            assert "errors" in result_type.__slots__

    def test_canonical_is_the_default_and_zero_rolls_back(self, monkeypatch):
        from shared.canonical_persistence.verification import (
            CHAIN_VERIFY_READ_CANONICAL_ENV,
            chain_verify_reads_canonical,
        )

        monkeypatch.delenv(CHAIN_VERIFY_READ_CANONICAL_ENV, raising=False)
        assert chain_verify_reads_canonical() is True, "#3039: canonical must be the no-env default"

        monkeypatch.setenv(CHAIN_VERIFY_READ_CANONICAL_ENV, "0")
        assert chain_verify_reads_canonical() is False

    def test_export_helper_signature(self):
        from services.ingestion.app.fda_export.queries import _verify_chain_for_export

        assert list(inspect.signature(_verify_chain_for_export).parameters) == [
            "persistence",
            "db_session",
            "tenant_id",
        ]

    def test_export_helper_uses_legacy_verifier_on_rollback(self, monkeypatch):
        from services.ingestion.app.fda_export.queries import _verify_chain_for_export

        calls = []
        sentinel = object()

        class _Persistence:
            def verify_chain(self, tenant_id):
                calls.append(tenant_id)
                return sentinel

        monkeypatch.setenv("CHAIN_VERIFY_READ_CANONICAL", "0")
        assert _verify_chain_for_export(_Persistence(), None, "") is sentinel
        assert calls == [""]

    def test_empty_input_chain_hash_is_deterministic(self):
        from shared.cte_persistence import compute_chain_hash

        first = compute_chain_hash("", None)
        assert first == compute_chain_hash("", None)
        assert len(first) == 64
        assert set(first) <= set("0123456789abcdef")
