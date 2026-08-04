"""Tests for the live dual-write parity verifier (``scripts/verify_canonical_parity_live.py``).

The verifier is the artifact that replaces the WS-1 calendar soak with a
quantitative verdict (#1335), so its own failure modes have to be pinned:

* it must be structurally incapable of writing (``assert_read_only``);
* it must never report success on zero rows — the classic false-green;
* it must distinguish a legacy orphan (HARD, #1277) from a canonical-only
  row (EXPECTED, ``dual_write=False`` paths);
* the SQL it builds must implement the ``dual_write_legacy`` mapping, not a
  paraphrase of it.

The first three are pure-function tests that need no database and run
everywhere. The last is a live-Postgres test using the same acquisition
contract as ``test_dual_write_parity.py``: it seeds a real dual-written
corpus, proves the verifier reports SAFE-TO-PROCEED, then deliberately
corrupts the legacy store and proves the verifier reports DO-NOT-PROCEED.
A verifier nobody has watched fail is not evidence of anything.
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from tests.migrations.rls_db import rls_postgres_or_skip, skip_or_fail_db

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "verify_canonical_parity_live.py"


def _load_verifier():
    """Import the script by path — ``scripts/`` is not an importable package."""
    spec = importlib.util.spec_from_file_location("verify_canonical_parity_live", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Register before exec: @dataclass resolves annotations via sys.modules.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vcpl = _load_verifier()


# ---------------------------------------------------------------------------
# Read-only guarantee
# ---------------------------------------------------------------------------


class TestReadOnlyGuard:
    @pytest.mark.parametrize(
        "statement",
        [
            "INSERT INTO fsma.cte_events (id) VALUES (1)",
            "update fsma.cte_events set source = 'x'",
            "DELETE FROM fsma.cte_kdes",
            "TRUNCATE fsma.cte_events",
            "DROP INDEX idx_cte_events_tenant",
            "CREATE INDEX CONCURRENTLY foo ON fsma.traceability_events (sha256_hash)",
            "-- looks innocent\nDELETE FROM fsma.cte_events",
            "/* c */ ALTER TABLE fsma.cte_events ADD COLUMN x int",
            # A CTE prelude must not launder a write.
            "WITH doomed AS (SELECT 1) INSERT INTO fsma.cte_events SELECT * FROM doomed",
        ],
    )
    def test_rejects_every_write(self, statement):
        with pytest.raises(vcpl.ReadOnlyViolation):
            vcpl.assert_read_only(statement)

    @pytest.mark.parametrize(
        "statement",
        [
            "SELECT 1",
            "  SELECT count(*) FROM fsma.cte_events",
            "/* comment */ WITH page AS (SELECT 1) SELECT * FROM page",
            "SELECT set_config('app.tenant_id', :tid, false)",
        ],
    )
    def test_allows_reads(self, statement):
        vcpl.assert_read_only(statement)

    def test_every_generated_query_passes_the_guard(self):
        """Whatever the flags, the SQL this tool builds is a pure read."""
        opts = vcpl.Options(
            tenants=(str(uuid4()),),
            since=datetime(2026, 1, 1, tzinfo=timezone.utc),
            until=datetime(2026, 2, 1, tzinfo=timezone.utc),
        )
        builders = [
            vcpl.build_page_query(opts, None, 100),
            vcpl.build_page_query(opts, (datetime.now(timezone.utc), str(uuid4())), 100),
            vcpl.build_legacy_total_query(opts),
            vcpl.build_canonical_only_query(opts),
            vcpl.build_unjoinable_canonical_query(opts),
        ]
        for sql, _params in builders:
            vcpl.assert_read_only(sql)


# ---------------------------------------------------------------------------
# The mapping actually being asserted
# ---------------------------------------------------------------------------


class TestMappingFidelity:
    def test_field_list_matches_dual_write_legacy(self):
        assert vcpl.FIELD_NAMES == (
            "id",
            "product_description",
            "location_gln",
            "location_name",
            "source",
            "kdes",
        )

    def test_page_sql_encodes_the_documented_mapping(self):
        sql, _ = vcpl.build_page_query(vcpl.Options(), None, 10)
        # id == event_id verbatim
        assert "p.id::text IS DISTINCT FROM t.event_id::text" in sql
        # product_description == COALESCE(product_reference, '')
        assert "p.product_description IS DISTINCT FROM COALESCE(t.product_reference, '')" in sql
        # location_gln == location_name == COALESCE(from_facility, to_facility) (#2535)
        assert (
            sql.count("COALESCE(t.from_facility_reference, t.to_facility_reference)") >= 2
        ), "location_gln and location_name must share one expression (#2535)"
        # source == source_system
        assert "p.source IS DISTINCT FROM t.source_system" in sql
        # None-valued KDEs are dropped on the canonical side, mirroring
        # dual_write_legacy's `if kde_value is None: continue`.
        assert "kv.value <> 'null'::jsonb" in sql
        # sha256_hash is the ONLY cross-store join key.
        assert "t.sha256_hash = p.sha256_hash" in sql
        assert "t.tenant_id = p.tenant_id" in sql

    def test_ignored_fields_are_not_compared(self):
        sql, _ = vcpl.build_page_query(vcpl.Options(ignore_fields=("id", "kdes")), None, 10)
        assert "t.event_id::text" not in sql
        assert "jsonb_build_object('id'" not in sql
        assert "jsonb_build_object('source'" in sql

    def test_window_uses_ingested_at_not_event_timestamp(self):
        """``event_timestamp`` is supplier-declared and can be backdated years."""
        opts = vcpl.Options(since=datetime(2026, 1, 1, tzinfo=timezone.utc))
        sql, params = vcpl.build_legacy_total_query(opts)
        assert "c.ingested_at >= :since" in sql
        assert "event_timestamp" not in sql
        assert params["since"] == opts.since

    def test_tenant_is_bound_never_interpolated(self):
        tenant = str(uuid4())
        sql, params = vcpl.build_legacy_total_query(vcpl.Options(tenants=(tenant,)))
        assert tenant not in sql
        assert params["tenants"] == [tenant]


# ---------------------------------------------------------------------------
# Verdict semantics — including the false-green guard
# ---------------------------------------------------------------------------


class TestVerdict:
    def test_zero_coverage_is_never_success(self):
        report = vcpl.Report(rows_examined=0, rows_matched=0)
        code, headline, reason = vcpl.decide(report, vcpl.Options())
        assert code == vcpl.EXIT_ZERO_COVERAGE
        assert headline == "DO-NOT-PROCEED"
        assert "ZERO COVERAGE" in reason

    def test_legacy_orphan_is_a_hard_failure(self):
        report = vcpl.Report(rows_examined=10, rows_matched=9, legacy_orphans=1)
        code, headline, reason = vcpl.decide(report, vcpl.Options())
        assert code == vcpl.EXIT_VIOLATIONS
        assert headline == "DO-NOT-PROCEED"
        assert "#1277" in reason

    def test_canonical_only_rows_are_never_a_failure(self):
        """dual_write=False paths make canonical-only rows expected (#1335)."""
        report = vcpl.Report(rows_examined=10, rows_matched=10, canonical_only=999_999)
        code, headline, _ = vcpl.decide(report, vcpl.Options())
        assert code == vcpl.EXIT_SAFE
        assert headline == "SAFE-TO-PROCEED"

    def test_field_divergence_fails(self):
        report = vcpl.Report(
            rows_examined=10,
            rows_matched=10,
            diverged_rows=2,
            diverged_same_txn=2,
            field_divergence={"product_description": 2},
        )
        code, _headline, reason = vcpl.decide(report, vcpl.Options())
        assert code == vcpl.EXIT_VIOLATIONS
        assert "dual_write_legacy mapping" in reason

    def test_limit_truncated_clean_run_is_not_a_cutover_decision(self):
        report = vcpl.Report(rows_examined=5, rows_matched=5, truncated_by_limit=True)
        code, headline, reason = vcpl.decide(report, vcpl.Options(limit=5))
        assert code == vcpl.EXIT_SAFE
        assert "NOT A CUTOVER DECISION" in headline
        assert "--limit" in reason

    def test_ignored_fields_are_disclosed_in_the_verdict(self):
        report = vcpl.Report(rows_examined=3, rows_matched=3)
        _code, _headline, reason = vcpl.decide(report, vcpl.Options(ignore_fields=("id",)))
        assert "ignoring field(s): id" in reason


class TestCli:
    def test_url_normalization(self):
        assert vcpl.normalize_database_url("postgres://u:p@h/db").startswith("postgresql://")
        assert vcpl.normalize_database_url("postgresql+asyncpg://u:p@h/db").startswith("postgresql+psycopg2://")

    def test_tenant_must_be_uuid(self):
        with pytest.raises(Exception):
            vcpl.parse_tenant("not-a-uuid")

    def test_naive_timestamps_are_utc(self):
        assert vcpl.parse_timestamp("2026-07-01").tzinfo is timezone.utc
        assert vcpl.parse_timestamp("2026-07-01T00:00:00Z").tzinfo is timezone.utc

    def test_until_defaults_to_a_settled_bound(self):
        """Cross-transaction writers would otherwise produce phantom orphans."""
        args = vcpl.build_parser().parse_args([])
        opts = vcpl.options_from_args(args)
        assert opts.until is not None
        assert not opts.until_was_explicit
        assert (datetime.now(timezone.utc) - opts.until).total_seconds() >= vcpl.DEFAULT_SETTLE_SECONDS - 5

    def test_missing_database_url_exits_incomplete(self, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert vcpl.main([]) == vcpl.EXIT_INCOMPLETE


# ---------------------------------------------------------------------------
# Live database: prove it passes clean AND prove it fails dirty
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def migrated_db():
    with rls_postgres_or_skip() as (database_url, engine):
        from tests.migrations.test_rls_coverage import _provision_app_roles

        _provision_app_roles(database_url)
        env = dict(os.environ)
        env["DATABASE_URL"] = database_url
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            skip_or_fail_db(f"alembic upgrade head failed: {result.stderr[-2000:]}")
        yield database_url, engine


def _make_event(tenant_id):
    from shared.canonical_event import (
        CTEType,
        EventStatus,
        IngestionSource,
        ProvenanceMetadata,
        TraceabilityEvent,
    )

    return TraceabilityEvent(
        event_id=uuid4(),
        tenant_id=tenant_id,
        source_system=IngestionSource.WEBHOOK_API,
        source_record_id=f"rec-{uuid4().hex[:8]}",
        event_type=CTEType.SHIPPING,
        event_timestamp=datetime.now(timezone.utc),
        event_timezone="UTC",
        product_reference="urn:gs1:01:09506000134352",
        lot_reference="LOT-VERIFY-1",
        traceability_lot_code=f"TLC-VERIFY-{uuid4().hex[:8]}",
        quantity=10.0,
        unit_of_measure="kg",
        from_entity_reference="urn:gs1:417:0614141000005",
        to_entity_reference="urn:gs1:417:0614141000012",
        from_facility_reference="urn:gs1:414:0614141000005",
        to_facility_reference="urn:gs1:414:0614141000012",
        # A None-valued KDE must be DROPPED from the legacy store; a nested
        # dict must survive the TEXT->JSONB round trip (#2532).
        kdes={"gtin": "09506000134352", "nested": {"b": 1, "a": 2}, "dropped": None},
        status=EventStatus.ACTIVE,
        provenance=ProvenanceMetadata(),
    )


@pytest.fixture()
def seeded_tenant(migrated_db):
    """A tenant with dual-written events plus intentional canonical-only rows."""
    from shared.canonical_persistence.writer import CanonicalEventStore

    database_url, _ = migrated_db
    engine = create_engine(database_url, future=True)
    tenant_id = uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO tenants (id, name, slug, status) "
                "VALUES (:id, :name, :slug, 'active') ON CONFLICT DO NOTHING"
            ),
            {"id": str(tenant_id), "name": f"vfy-{tenant_id.hex[:8]}", "slug": f"vfy-{tenant_id.hex[:8]}"},
        )
    session = sessionmaker(bind=engine, future=True)()
    session.execute(text("SET app.tenant_id = :tid"), {"tid": str(tenant_id)})
    for _ in range(6):
        CanonicalEventStore(session, dual_write=True).persist_event(_make_event(tenant_id))
    # Canonical-only rows: EXPECTED, must not affect the verdict.
    for _ in range(2):
        CanonicalEventStore(session, dual_write=False).persist_event(_make_event(tenant_id))
    session.commit()
    try:
        yield database_url, engine, str(tenant_id)
    finally:
        session.close()
        engine.dispose()


def _run_verifier(database_url: str, tenant: str, *extra: str):
    env = dict(os.environ)
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--tenant",
            tenant,
            "--settle-seconds",
            "0",
            "--json",
            *extra,
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )


class TestAgainstLiveDatabase:
    def test_clean_dual_write_corpus_is_safe_to_proceed(self, seeded_tenant):
        import json

        database_url, _engine, tenant = seeded_tenant
        result = _run_verifier(database_url, tenant)
        assert result.returncode == vcpl.EXIT_SAFE, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["verdict"] == "SAFE-TO-PROCEED"
        assert payload["legacy_orphans"]["count"] == 0
        assert payload["field_divergence"]["rows"] == 0
        # Coverage is real, not a false green.
        assert payload["coverage"]["rows_compared"] == 6
        assert payload["coverage"]["same_transaction"] == 6
        # dual_write=False rows are reported, not failed.
        assert payload["canonical_only"]["count"] == 2

    def test_legacy_orphan_is_detected(self, seeded_tenant):
        """A legacy row with no canonical twin = a lost canonical write (#1277)."""
        import json

        database_url, engine, tenant = seeded_tenant
        with engine.begin() as conn:
            conn.execute(
                text("SET LOCAL app.tenant_id = :tid"),
                {"tid": tenant},
            )
            conn.execute(
                text("""
                    INSERT INTO fsma.cte_events (
                        id, tenant_id, event_type, traceability_lot_code,
                        product_description, quantity, unit_of_measure,
                        location_gln, location_name, event_timestamp,
                        source, source_event_id, idempotency_key,
                        sha256_hash, chain_hash
                    ) VALUES (
                        gen_random_uuid(), CAST(:tid AS uuid), 'shipping', 'TLC-ORPHAN',
                        'orphan', 1.0, 'kg', 'GLN-X', 'GLN-X', NOW(),
                        'webhook_api', 'rec-orphan', :idem, :sha, 'chain-orphan'
                    )
                """),
                {"tid": tenant, "idem": f"idem-orphan-{uuid4().hex}", "sha": "de" + "0" * 62},
            )

        result = _run_verifier(database_url, tenant)
        assert result.returncode == vcpl.EXIT_VIOLATIONS, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        assert payload["verdict"] == "DO-NOT-PROCEED"
        assert payload["legacy_orphans"]["count"] == 1
        assert payload["legacy_orphans"]["samples"][0]["sha256_hash"] == "de" + "0" * 62

    def test_field_divergence_is_detected(self, seeded_tenant):
        """A legacy twin that violates the dual_write_legacy mapping must fail."""
        import json

        database_url, engine, tenant = seeded_tenant
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant})
            # Forge a legacy row for one of the canonical-only events, with a
            # different id, description, location, and source.
            conn.execute(
                text("""
                    INSERT INTO fsma.cte_events (
                        id, tenant_id, event_type, traceability_lot_code,
                        product_description, quantity, unit_of_measure,
                        location_gln, location_name, event_timestamp,
                        source, source_event_id, idempotency_key,
                        sha256_hash, chain_hash
                    )
                    SELECT gen_random_uuid(), t.tenant_id, t.event_type,
                           t.traceability_lot_code, 'WRONG DESCRIPTION',
                           t.quantity, t.unit_of_measure, 'WRONG-GLN', 'WRONG-NAME',
                           t.event_timestamp, 'csv_upload', 'rec-div', :idem,
                           t.sha256_hash, t.chain_hash
                    FROM fsma.traceability_events t
                    WHERE t.tenant_id = CAST(:tid AS uuid)
                      AND NOT EXISTS (
                          SELECT 1 FROM fsma.cte_events c
                          WHERE c.tenant_id = t.tenant_id
                            AND c.sha256_hash = t.sha256_hash
                      )
                    LIMIT 1
                """),
                {"tid": tenant, "idem": f"idem-div-{uuid4().hex}"},
            )

        result = _run_verifier(database_url, tenant)
        assert result.returncode == vcpl.EXIT_VIOLATIONS, result.stdout + result.stderr
        payload = json.loads(result.stdout)
        by_field = payload["field_divergence"]["by_field"]
        assert payload["field_divergence"]["rows"] == 1
        for name in ("id", "product_description", "location_gln", "location_name", "source"):
            assert by_field[name] == 1, f"{name} divergence not detected: {by_field}"

    def test_empty_window_reports_zero_coverage_not_success(self, seeded_tenant):
        """The false-green guard, end to end."""
        database_url, _engine, tenant = seeded_tenant
        result = _run_verifier(database_url, tenant, "--since", "2099-01-01")
        assert result.returncode == vcpl.EXIT_ZERO_COVERAGE, result.stdout + result.stderr

    def test_verifier_does_not_mutate_the_database(self, seeded_tenant):
        """Read-only, proven against a live database rather than asserted."""
        database_url, engine, tenant = seeded_tenant
        counts_sql = text("""
            SELECT (SELECT COUNT(*) FROM fsma.cte_events),
                   (SELECT COUNT(*) FROM fsma.cte_kdes),
                   (SELECT COUNT(*) FROM fsma.traceability_events)
        """)
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant})
            before = tuple(conn.execute(counts_sql).fetchone())
        _run_verifier(database_url, tenant)
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant})
            after = tuple(conn.execute(counts_sql).fetchone())
        assert before == after
