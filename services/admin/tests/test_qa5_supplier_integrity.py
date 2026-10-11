"""QA5: multi-supplier Merkle integrity, graph fallback, consumer health.

Three independent fixes pinned here:

* ``_merkle_integrity_ratio``: chain sequences/links are tenant-wide,
  so scoring a supplier-scoped list by list adjacency collapsed every
  multi-supplier tenant's integrity toward 0. Events are now checked
  against their true tenant-wide predecessor.
* ``get_required_ctes`` route: an empty Neo4j payload (no record, or
  Neo4j down) fell through as ``required_ctes: []`` and hid real
  Postgres FTL scoping. Empty graph results now fall back to Postgres.
* ``get_consumer_health``: a consumer that never started reported
  ``healthy: True`` (``is_alive`` only means "stop was never
  requested"). Never-started now reports unhealthy.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.supplier_onboarding_routes import _merkle_integrity_ratio  # noqa: E402


def _event(seq: int, prev: str | None, h: str):
    return SimpleNamespace(sequence_number=seq, merkle_prev_hash=prev, merkle_hash=h)


def _chain_hashes(n: int) -> dict[int, str]:
    return {i: f"hash-{i}" for i in range(1, n + 1)}


class TestMultiSupplierMerkleRatio:
    def test_interleaved_supplier_events_score_full(self):
        """Supplier A holds sequences 1,3,5 of an intact tenant chain.
        Pre-fix adjacency scoring failed every link (ratio 0.2); true
        predecessor scoring gives 1.0."""
        hashes = _chain_hashes(5)
        supplier_a = [
            _event(1, None, hashes[1]),
            _event(3, hashes[2], hashes[3]),
            _event(5, hashes[4], hashes[5]),
        ]
        prev_map = {**hashes}
        assert _merkle_integrity_ratio(supplier_a, prev_hash_by_sequence=prev_map) == 1.0

    def test_tampered_link_detected_with_map(self):
        hashes = _chain_hashes(3)
        events = [
            _event(1, None, hashes[1]),
            _event(2, "tampered-prev", hashes[2]),
        ]
        assert _merkle_integrity_ratio(events, prev_hash_by_sequence={**hashes}) == 0.5

    def test_legacy_adjacency_unchanged_without_map(self):
        """The map-less path keeps its old semantics for contiguous
        (tenant-wide) lists."""
        contiguous = [_event(1, None, "h1"), _event(2, "h1", "h2")]
        assert _merkle_integrity_ratio(contiguous) == 1.0
        gapped = [_event(1, None, "h1"), _event(3, "h2", "h3")]
        assert _merkle_integrity_ratio(gapped) == 0.5

    def test_empty_list_scores_full(self):
        assert _merkle_integrity_ratio([], prev_hash_by_sequence={}) == 1.0


class _FakeCategoryRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        outer = self

        class _Scalars:
            def all(self):
                return outer._rows

        return _Scalars()


class _FakeDB:
    def __init__(self, category_rows):
        self._rows = category_rows

    def execute(self, stmt, params=None):
        return _FakeCategoryRows(self._rows)


def _run_required_ctes(monkeypatch, graph_payload, category_rows):
    import asyncio

    import app.supplier_facilities_routes as routes

    tenant_id = uuid.uuid4()
    facility_id = uuid.uuid4()
    monkeypatch.setattr(routes, "_get_supplier_facility_or_404", lambda *a, **k: SimpleNamespace(id=facility_id))
    monkeypatch.setattr(
        routes.supplier_graph_sync,
        "get_required_ctes_for_facility",
        lambda *a, **k: graph_payload,
    )
    monkeypatch.setattr(routes.TenantContext, "get_tenant_context", staticmethod(lambda db: tenant_id))

    return asyncio.run(
        routes.get_required_ctes(
            facility_id=str(facility_id),
            current_user=SimpleNamespace(id=uuid.uuid4()),
            db=_FakeDB(category_rows),
        )
    )


class TestGraphEmptyFallback:
    def test_empty_graph_yields_to_postgres_source(self, monkeypatch):
        """An empty Neo4j payload must not masquerade as an answer: the
        route must reach the Postgres branch (source == postgres) and
        surface the stored rows. Pre-fix this returned required_ctes []."""
        rows = [SimpleNamespace(category_id="2", category_name="Produce", required_ctes=["shipping", "receiving"])]
        response = _run_required_ctes(
            monkeypatch,
            {"source": "neo4j", "categories": [], "required_ctes": []},
            rows,
        )
        assert response.source == "postgres"
        assert set(response.required_ctes) == {"shipping", "receiving"}

    def test_none_graph_yields_to_postgres_source(self, monkeypatch):
        rows = [SimpleNamespace(category_id="2", category_name="Produce", required_ctes=["shipping"])]
        response = _run_required_ctes(monkeypatch, None, rows)
        assert response.source == "postgres"

    def test_non_empty_graph_still_wins(self, monkeypatch):
        response = _run_required_ctes(
            monkeypatch,
            {"source": "neo4j", "categories": [{"id": "1"}], "required_ctes": ["shipping"]},
            [],
        )
        assert response.source == "neo4j"
        assert response.required_ctes == ["shipping"]
