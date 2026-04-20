"""Regression tests for NLP pipeline tenant scoping (#1122).

Before this fix:

  * ``FSMAExtractor.extract(text, document_id, pdf_bytes)`` had no
    ``tenant_id`` parameter. Callers could not propagate the tenant
    through the extractor so the result envelope was tenant-less.
  * ``FSMAExtractionResult`` had no ``tenant_id`` field.
  * ``services/nlp/app/consumer.py``'s ``_retry_counts`` cache was
    keyed by raw ``doc_id``. Two tenants that published documents
    with the same ``doc_id`` shared a retry-count bucket — tenant A's
    3rd retry DLQ'd tenant B's first attempt. That's a cross-tenant
    availability bug with DLQ leakage.
  * Outbound Kafka keys were ``doc_id.encode()``, not
    ``f"{tenant_id}:{doc_id}".encode()`` — so partition routing could
    not separate tenants and sticky-partition order across tenants
    was scrambled.

These tests lock in the tenant-aware behavior across all four
boundaries and will fail loudly if anyone re-introduces the
tenant-blind paths.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import UUID

import pytest

# Ensure repo root is importable so ``services.nlp.app.*`` resolves.
_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


TENANT_A = str(UUID("11111111-1111-1111-1111-111111111111"))
TENANT_B = str(UUID("22222222-2222-2222-2222-222222222222"))


# ---------------------------------------------------------------------------
# Retry-count scoping (consumer.py:68-72 before fix)
# ---------------------------------------------------------------------------


class TestRetryCountScopedByTenant:
    """Two tenants with the same ``doc_id`` must never share a retry bucket.

    The fix moves the key from ``doc_id`` to ``f"{tenant_id}:{doc_id}"`` so
    each tenant has its own retry counter. Interleaving is impossible.
    """

    def test_retry_count_scoped_by_tenant(self):
        """Incrementing (tenantA, doc1) twice and (tenantB, doc1) twice must
        produce two independent counters, each equal to 2."""
        from services.nlp.app.consumer import _retry_counts, _retry_key_for

        _retry_counts.clear() if hasattr(_retry_counts, "clear") else None

        key_a = _retry_key_for(TENANT_A, "doc1")
        key_b = _retry_key_for(TENANT_B, "doc1")

        # Simulate two retries from each tenant.
        for _ in range(2):
            _retry_counts[key_a] = _retry_counts.get(key_a, 0) + 1
            _retry_counts[key_b] = _retry_counts.get(key_b, 0) + 1

        assert _retry_counts[key_a] == 2, (
            "tenant A retry counter was shared with tenant B — cross-tenant "
            "DLQ leakage regression"
        )
        assert _retry_counts[key_b] == 2, (
            "tenant B retry counter was shared with tenant A — cross-tenant "
            "DLQ leakage regression"
        )
        # And the keys are different objects.
        assert key_a != key_b
        assert key_a.startswith(TENANT_A)
        assert key_b.startswith(TENANT_B)

    def test_retry_key_format_is_tenant_colon_doc(self):
        """Format contract — ``f"{tenant_id}:{doc_id}"``."""
        from services.nlp.app.consumer import _retry_key_for

        assert _retry_key_for(TENANT_A, "doc-xyz") == f"{TENANT_A}:doc-xyz"
        assert _retry_key_for(TENANT_B, "doc-xyz") == f"{TENANT_B}:doc-xyz"

    def test_retry_key_falls_back_to_sentinel_when_tenant_missing(self):
        """Defense in depth — callers hitting DLQ pre-tenant must not collide
        with any legitimate tenant's bucket."""
        from services.nlp.app.consumer import _retry_key_for

        sentinel_key = _retry_key_for(None, "doc1")
        # Must not look like a real UUID tenant prefix.
        assert sentinel_key == "NO_TENANT:doc1"
        try:
            UUID(sentinel_key.split(":", 1)[0])
        except ValueError:
            pass
        else:
            pytest.fail("Sentinel prefix must not parse as a UUID")


# ---------------------------------------------------------------------------
# Extractor signature (FSMAExtractor.extract)
# ---------------------------------------------------------------------------


class TestExtractorCarriesTenantId:
    """Extract result must carry the tenant_id the caller supplied."""

    def test_extraction_result_carries_tenant_id(self):
        """``FSMAExtractor.extract(..., tenant_id="tA")`` → result.tenant_id == "tA"."""
        from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

        extractor = FSMAExtractor()
        result = extractor.extract(
            text=(
                "BILL OF LADING\n"
                "Shipper: Foo Inc.\n"
                "Lot: 00012345678901LOT-A\n"
                "Ship Date: 01/15/2025\n"
                "Quantity: 10 cases\n"
            ),
            document_id="d1",
            tenant_id=TENANT_A,
        )
        assert result.tenant_id == TENANT_A

    def test_extractor_raises_on_empty_tenant_id(self):
        """Empty string tenant_id → ValueError(E_MISSING_TENANT_ID).

        Required per #1122 — callers must make an explicit tenant decision.
        Silent fallback to "default" / "unknown" is precisely the pattern
        that created the bug.
        """
        from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

        extractor = FSMAExtractor()
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(text="any", document_id="d1", tenant_id="")
        assert "E_MISSING_TENANT_ID" in str(exc_info.value)

    def test_extractor_raises_on_whitespace_tenant_id(self):
        """Whitespace is not a tenant id."""
        from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

        extractor = FSMAExtractor()
        with pytest.raises(ValueError) as exc_info:
            extractor.extract(text="any", document_id="d1", tenant_id="   ")
        assert "E_MISSING_TENANT_ID" in str(exc_info.value)

    def test_extractor_requires_tenant_id_as_kwarg(self):
        """``tenant_id`` is keyword-only (not positional) so every caller has
        to name it — prevents an accidental positional swap."""
        from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

        extractor = FSMAExtractor()
        # Positional passthrough must fail because we marked it keyword-only.
        with pytest.raises(TypeError):
            extractor.extract("any text", "d1", TENANT_A)  # type: ignore[misc]

    def test_to_graph_event_includes_tenant_id(self):
        """Routed envelope must carry tenant_id so downstream consumers
        (graph.update) enforce scoping without re-reading Kafka headers."""
        from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

        extractor = FSMAExtractor()
        result = extractor.extract(
            text="no meaningful content", document_id="d1", tenant_id=TENANT_A
        )
        graph_event = extractor.to_graph_event(result)
        assert graph_event["tenant_id"] == TENANT_A


# ---------------------------------------------------------------------------
# Missing tenant_id on inbound event → DLQ with sentinel error code
# ---------------------------------------------------------------------------


class TestMissingTenantOnEventRaises:
    """Kafka inbound event payload without tenant_id must hit DLQ with
    ``E_MISSING_TENANT_ID`` — never silently process."""

    def test_resolve_tenant_returns_none_when_event_missing_tenant_id(self):
        """``_resolve_tenant_id`` is the consumer's gate — when both header
        and payload are absent it must return ``(None, reason)``."""
        from services.nlp.app.consumer import _resolve_tenant_id

        resolved, reason = _resolve_tenant_id(
            header_tenant_id=None, payload_tenant_id=None
        )
        assert resolved is None
        assert reason is not None
        assert "no_tenant_id" in reason.lower()

    def test_fsma_extractor_raises_e_missing_tenant_id(self):
        """The extractor-level guard: a direct caller who forgets tenant_id
        gets the sentinel error code the consumer also emits."""
        from services.nlp.app.extractors.fsma_extractor import FSMAExtractor

        with pytest.raises(ValueError, match="E_MISSING_TENANT_ID"):
            FSMAExtractor().extract(
                text="x", document_id="d1", tenant_id=None  # type: ignore[arg-type]
            )

    def test_run_fsma_extractor_short_circuits_on_missing_tenant(self):
        """The consumer-level guard: ``_run_fsma_extractor`` must NOT call
        the extractor or the producer when tenant_id is falsy — it returns an
        error summary so the outer DLQ path fires."""
        from services.nlp.app import consumer as consumer_mod

        mock_extractor = MagicMock()
        mock_producer = MagicMock()

        summary = consumer_mod._run_fsma_extractor(
            text="doc text",
            doc_id="d1",
            doc_hash="h1",
            producer=mock_producer,
            tenant_id="",  # type: ignore[arg-type]
            kafka_headers=[],
        )
        assert summary["status"] == "error"
        mock_producer.send.assert_not_called()
        mock_extractor.extract.assert_not_called()


# ---------------------------------------------------------------------------
# Kafka producer key format
# ---------------------------------------------------------------------------


class TestKafkaMessageKeyIncludesTenantId:
    """Outbound Kafka keys must be ``f"{tenant_id}:{doc_id}"``.

    Partitioning on raw ``doc_id`` means two tenants publishing the same
    doc_id land on the same partition — cross-tenant ordering collisions
    and a breakage of tenant isolation.
    """

    def test_kafka_key_helper_format(self):
        """Format contract — ``f"{tenant_id}:{doc_id}"``."""
        from services.nlp.app.consumer import _kafka_key_for

        assert _kafka_key_for(TENANT_A, "doc1") == f"{TENANT_A}:doc1"
        assert _kafka_key_for(TENANT_B, "doc1") == f"{TENANT_B}:doc1"

    def test_run_fsma_extractor_sends_tenant_scoped_kafka_key(self):
        """`_run_fsma_extractor` must pass ``f"{tenant}:{doc}"`` as the key."""
        from services.nlp.app import consumer as consumer_mod

        mock_extractor = MagicMock()
        result = MagicMock()
        result.ctes = [MagicMock()]
        result.review_required = False
        mock_extractor.extract.return_value = result
        mock_extractor.route_extraction.return_value = {
            "topic": "graph.update",
            "payload": {"event_type": "fsma.extraction"},
            "routed_at": "2026-04-20T00:00:00Z",
        }
        mock_producer = MagicMock()

        from unittest.mock import patch

        with patch.object(
            consumer_mod, "_get_fsma_extractor", return_value=mock_extractor
        ):
            consumer_mod._run_fsma_extractor(
                text="doc",
                doc_id="doc1",
                doc_hash="h1",
                producer=mock_producer,
                tenant_id=TENANT_A,
                kafka_headers=[],
            )

        mock_producer.send.assert_called_once()
        kwargs = mock_producer.send.call_args.kwargs
        key = kwargs.get("key")
        assert key == f"{TENANT_A}:doc1", (
            f"expected tenant-scoped key, got {key!r} — #1122 regression"
        )

    def test_kafka_key_differs_across_tenants_with_same_doc_id(self):
        """Two tenants + same doc_id must yield different Kafka keys.

        This is the primary partition-routing guarantee — without it, the
        two tenants' events end up on the same partition and can't be
        separated by key alone.
        """
        from services.nlp.app.consumer import _kafka_key_for

        key_a = _kafka_key_for(TENANT_A, "shared-doc")
        key_b = _kafka_key_for(TENANT_B, "shared-doc")
        assert key_a != key_b
        assert key_a.startswith(TENANT_A)
        assert key_b.startswith(TENANT_B)

    def test_route_extraction_high_confidence_uses_tenant_scoped_key(self):
        """``_route_extraction`` emitting to ``graph.update`` must also use
        the tenant-scoped key."""
        from services.nlp.app import consumer as consumer_mod
        from shared.schemas import ExtractionPayload, ObligationType

        extraction = ExtractionPayload(
            subject="s",
            action="must",
            object=None,
            obligation_type=ObligationType.MUST,
            thresholds=[],
            jurisdiction=None,
            confidence_score=0.99,  # high tier
            source_text="x",
            source_offset=0,
            attributes={},
        )
        mock_producer = MagicMock()
        consumer_mod._route_extraction(
            extraction,
            doc_id="doc1",
            doc_hash="h1",
            source_url="http://example.com/doc",
            producer=mock_producer,
            tenant_id=TENANT_A,
        )
        mock_producer.send.assert_called_once()
        key = mock_producer.send.call_args.kwargs.get("key")
        assert key == f"{TENANT_A}:doc1"

    def test_route_extraction_review_tier_uses_tenant_scoped_key(self):
        """Review queue emit must also be tenant-scoped."""
        from services.nlp.app import consumer as consumer_mod
        from shared.schemas import ExtractionPayload, ObligationType

        extraction = ExtractionPayload(
            subject="s",
            action="must",
            object=None,
            obligation_type=ObligationType.MUST,
            thresholds=[],
            jurisdiction=None,
            confidence_score=0.50,  # below medium → HITL
            source_text="x",
            source_offset=0,
            attributes={},
        )
        mock_producer = MagicMock()
        consumer_mod._route_extraction(
            extraction,
            doc_id="doc1",
            doc_hash="h1",
            source_url="http://example.com/doc",
            producer=mock_producer,
            tenant_id=TENANT_B,
        )
        mock_producer.send.assert_called_once()
        key = mock_producer.send.call_args.kwargs.get("key")
        assert key == f"{TENANT_B}:doc1"
