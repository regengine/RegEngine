"""WS-1b (#1335) — FDA export v1 legacy/canonical reader contract, data-free.

The v1 recall export is the compliance-critical FDA reader (21 CFR
1.1455). These tests pin the parts of the legacy ≡ canonical contract
that need no records: the twin builders and fetchers share a signature,
unfiltered queries scope to the tenant only, empty row sets convert to
an empty export, and the canonical read flag defaults OFF.
"""

from __future__ import annotations

import inspect

NO_FILTERS = dict(
    product=None,
    location=None,
    tlc=None,
    event_type=None,
    start_date=None,
    end_date=None,
)


class TestExportV1Contract:
    def test_where_clause_builders_share_a_signature(self):
        from services.ingestion.app.fda_export.queries import (
            build_recall_where_clause,
            build_recall_where_clause_canonical,
        )

        assert inspect.signature(build_recall_where_clause) == inspect.signature(build_recall_where_clause_canonical)

    def test_fetchers_share_a_signature(self):
        from services.ingestion.app.fda_export.queries import (
            fetch_recall_events,
            fetch_recall_events_canonical,
        )

        assert inspect.signature(fetch_recall_events) == inspect.signature(fetch_recall_events_canonical)

    def test_unfiltered_builders_bind_only_the_tenant(self):
        from services.ingestion.app.fda_export.queries import (
            build_recall_where_clause,
            build_recall_where_clause_canonical,
        )

        for builder in (build_recall_where_clause, build_recall_where_clause_canonical):
            where, params = builder(tenant_id="", **NO_FILTERS)
            assert params == {"tid": ""}
            assert "e.tenant_id = :tid" in where

    def test_empty_rows_yield_empty_export(self):
        from services.ingestion.app.fda_export.queries import rows_to_event_dicts

        assert rows_to_event_dicts([]) == []

    def test_canonical_read_flag_defaults_off(self, monkeypatch):
        from services.ingestion.app.fda_export.queries import (
            FDA_EXPORT_V1_READ_CANONICAL_ENV,
            export_v1_reads_canonical,
        )

        monkeypatch.delenv(FDA_EXPORT_V1_READ_CANONICAL_ENV, raising=False)
        assert export_v1_reads_canonical() is False
