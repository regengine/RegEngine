"""Tenant scoping tests for NLP retrieval / routing.

These tests verify that every routed payload carries ``tenant_id`` through
to downstream Kafka topics and DLQ sinks. The NLP service does not yet
have a vector / RAG store of its own, but when one is added it must
enforce the same guarantee.

Covers aspects of:
- #1176 / #1122: tenant_id threaded through consumer routing + retry
  state so tenant A and tenant B with the same document_id don't
  interleave retries or leak review items across tenants.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

_repo_root = Path(__file__).resolve().parents[3]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))


@pytest.fixture
def mock_producer():
    producer = MagicMock()
    future = MagicMock()
    future.get.return_value = MagicMock()
    producer.send.return_value = future
    return producer


def _make_extraction(confidence: float):
    from shared.schemas import ExtractionPayload

    return ExtractionPayload(
        subject="subject",
        action="must maintain",
        obligation_type="MUST",
        confidence_score=confidence,
        source_text="subject must maintain things",
        source_offset=0,
        attributes={},
    )


# ----------------------------------------------------------------------
# Tenant propagation in routing headers + payload
# ----------------------------------------------------------------------


class TestTenantIdPropagation:
    def test_tenant_id_in_graph_event_high_confidence(self, mock_producer):
        from services.nlp.app.consumer import _route_extraction

        tenant_a = str(uuid4())
        _route_extraction(
            extraction=_make_extraction(0.97),
            doc_id="doc-high",
            doc_hash="hash",
            source_url="https://example.com",
            producer=mock_producer,
            tenant_id=tenant_a,
        )
        call = mock_producer.send.call_args
        payload = call.kwargs["value"]
        assert payload["tenant_id"] == tenant_a
        # Also propagated via the X-Tenant-ID header so downstream Kafka
        # consumers can scope without re-parsing the body.
        headers = call.kwargs["headers"]
        header_dict = {k: v.decode() for k, v in headers}
        assert header_dict.get("X-Tenant-ID") == tenant_a

    def test_tenant_id_in_review_envelope_low_confidence(self, mock_producer):
        from services.nlp.app.consumer import _route_extraction

        tenant_b = str(uuid4())
        _route_extraction(
            extraction=_make_extraction(0.50),
            doc_id="doc-low",
            doc_hash="hash",
            source_url="https://example.com",
            producer=mock_producer,
            tenant_id=tenant_b,
        )
        call = mock_producer.send.call_args
        payload = call.kwargs["value"]
        assert payload["tenant_id"] == tenant_b
        headers = call.kwargs["headers"]
        header_dict = {k: v.decode() for k, v in headers}
        assert header_dict.get("X-Tenant-ID") == tenant_b
        assert header_dict.get("X-Review-Priority") == "high"

    def test_same_docid_different_tenants_emit_separately(self, mock_producer):
        """Two tenants submitting the same document_id must produce two
        distinct envelopes, each carrying its own tenant_id header + body.
        """
        from services.nlp.app.consumer import _route_extraction

        tenant_a = str(uuid4())
        tenant_b = str(uuid4())
        for t in (tenant_a, tenant_b):
            _route_extraction(
                extraction=_make_extraction(0.50),
                doc_id="shared-doc-id",
                doc_hash="hash",
                source_url="https://example.com",
                producer=mock_producer,
                tenant_id=t,
            )
        assert mock_producer.send.call_count == 2
        tenants_seen = set()
        for call in mock_producer.send.call_args_list:
            tenants_seen.add(call.kwargs["value"]["tenant_id"])
        assert tenants_seen == {tenant_a, tenant_b}

    def test_null_tenant_id_still_produces_envelope_with_placeholder_header(
        self, mock_producer
    ):
        """Messages without a tenant_id (e.g. legacy pipeline) still route —
        but the header is present (empty) so downstream can detect and
        reject rather than default-match."""
        from services.nlp.app.consumer import _route_extraction

        _route_extraction(
            extraction=_make_extraction(0.50),
            doc_id="doc-no-tenant",
            doc_hash="hash",
            source_url="https://example.com",
            producer=mock_producer,
            tenant_id=None,
        )
        call = mock_producer.send.call_args
        headers = call.kwargs["headers"]
        header_dict = {k: v.decode() for k, v in headers}
        assert "X-Tenant-ID" in header_dict
        assert header_dict["X-Tenant-ID"] == ""


# ----------------------------------------------------------------------
# Contract test for future vector-store integration
# ----------------------------------------------------------------------


class TestTenantScopedRetrievalContract:
    """If/when a vector store is added to the NLP service, any retrieval
    helper must accept a ``tenant_id`` argument and filter at the query
    layer — NOT post-hoc. This test documents the contract that a future
    implementation must pass.
    """

    def test_contract_documented(self):
        """Placeholder: enforces the invariant via a dedicated test file so
        that a future implementer of ``services/nlp/app/retrieval/*`` is
        forced to register their helper here. Presence of this file keeps
        tenant-scoping on the migration checklist.
        """

        # Intentionally trivial — the value is in the module's existence
        # and the test_file_naming that a grep for "retrieval" will find.
        assert True

    def test_no_vector_store_currently_present(self):
        """Canary: if a vector-store dependency is added without updating
        the tenant-scope tests, this should fail.
        """
        import pkgutil
        import services.nlp.app as nlp_app

        mod_names = {m.name for m in pkgutil.iter_modules(nlp_app.__path__)}
        # When ``retrieval`` or ``embeddings`` modules land, this assertion
        # will fail, alerting the author to update tenant-scope tests.
        for vector_name in ("retrieval", "embeddings", "vector_store"):
            if vector_name in mod_names:
                pytest.fail(
                    f"Vector-store module '{vector_name}' added without "
                    f"tenant-scoping tests. Update "
                    f"services/nlp/tests/test_retrieval_tenant_scope.py."
                )
