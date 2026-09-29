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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from shared.db_url import sync_postgres_url
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
            "event_type",
            "traceability_lot_code",
            "event_timestamp",
            "quantity",
            "unit_of_measure",
            "kdes",
        )

    def test_recall_filter_predicate_columns_are_compared(self):
        """The columns build_recall_where_clause filters on MUST be compared.

        ``event_type``, ``traceability_lot_code`` and ``event_timestamp`` are
        the WHERE predicates of both the legacy and canonical recall queries
        (fda_export/queries.py). A divergence in any of them changes WHICH
        ROWS a regulator's recall search returns, not merely a cell value, so
        leaving them uncompared forfeits the verifier's entire purpose.
        """
        for predicate_column in ("event_type", "traceability_lot_code", "event_timestamp"):
            assert predicate_column in vcpl.FIELD_NAMES

    def test_uncompared_export_columns_are_disclosed_by_name(self):
        """The tool must publish its own blind spots, not leave them in chat."""
        disclosed = {name for name, _why in vcpl.UNCOMPARED_EXPORT_COLUMNS}
        assert disclosed == {"sha256_hash", "chain_hash", "ingested_at"}
        # Everything the v1 export emits is either compared or disclosed.
        export_columns = {
            "id", "event_type", "traceability_lot_code", "product_description",
            "quantity", "unit_of_measure", "event_timestamp", "location_gln",
            "location_name", "source", "sha256_hash", "chain_hash", "kdes",
            "ingested_at",
        }
        assert export_columns <= set(vcpl.FIELD_NAMES) | disclosed

    def test_page_sql_encodes_the_documented_mapping(self):
        sql, _ = vcpl.build_page_query(vcpl.Options(), None, 10)
        # id == event_id verbatim
        assert "p.id::text IS DISTINCT FROM t.event_id::text" in sql
        # product_description == COALESCE(product_reference, '')
        assert "p.product_description IS DISTINCT FROM COALESCE(t.product_reference, '')" in sql
        # location_gln == location_name == the writer's ``from_facility_reference
        # or to_facility_reference``. That Python ``or`` falls back on ANY falsy
        # left operand (None AND ''), so the canonical-side expression must
        # NULLIF the empty string to NULL before COALESCE — a bare
        # COALESCE(from, to) would only substitute on NULL and diverge on '' .
        assert (
            sql.count("COALESCE(NULLIF(t.from_facility_reference, ''), t.to_facility_reference)") >= 2
        ), "location_gln and location_name must share the NULLIF-collapsing expression (#2535)"
        # The bare (empty-string-mishandling) form must be gone.
        assert "COALESCE(t.from_facility_reference, t.to_facility_reference)" not in sql
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

    def test_unexplained_orphan_is_a_hard_failure(self):
        report = vcpl.Report(
            rows_examined=10, rows_matched=9, legacy_orphans=1, orphans_unexplained=1
        )
        code, headline, reason = vcpl.decide(report, vcpl.Options())
        assert code == vcpl.EXIT_VIOLATIONS
        assert headline == "DO-NOT-PROCEED"
        assert "#1277" in reason

    def test_legacy_native_orphan_is_not_a_lost_write(self):
        """The correction that this whole tool turned on.

        A legacy row written by ``CTEPersistence.store_event`` (live via
        ``webhook_compat.ingest_events``) carries the LEGACY hash formula,
        which hashes a different field set than the canonical formula. It can
        never join canonical on ``sha256_hash`` even though its canonical
        sibling exists. Reporting that as "a canonical write was lost" is
        both wrong and dangerous: the documented remediation is the backfill,
        which would then duplicate FDA traceability records.

        NOT a violation is not the same as SAFE: with zero of the five
        orphans content-probed, this scan cannot show canonical holds them,
        so the verdict is PARTIAL — the exit code ``if verify; then proceed``
        must not read as authorization to retire the legacy store.
        """
        report = vcpl.Report(
            rows_examined=10,
            rows_matched=5,
            legacy_orphans=5,
            orphans_legacy_native=5,
            orphans_unexplained=0,
        )
        code, headline, reason = vcpl.decide(report, vcpl.Options())
        assert code != vcpl.EXIT_VIOLATIONS, "legacy-native orphans are not violations"
        assert code == vcpl.EXIT_PARTIAL, "unprobed native orphans are unproven coverage"
        assert "never content-probed" in reason
        assert "lost" not in reason.lower() or "NOT a lost write" in reason
        # It must still be visible in the verdict — silence would be its own bug.
        assert "legacy-native" in reason or "legacy_native_hash_formula" in reason

    def test_fully_corroborated_legacy_native_orphans_are_safe(self):
        """When every native orphan is probed AND corroborated, canonical
        demonstrably holds the data, and SAFE-TO-PROCEED is earned."""
        report = vcpl.Report(
            rows_examined=10,
            rows_matched=5,
            legacy_orphans=5,
            orphans_legacy_native=5,
            content_probe_attempted=5,
            content_probe_corroborated=5,
            content_probe_uncorroborated=0,
        )
        code, headline, _reason = vcpl.decide(report, vcpl.Options())
        assert code == vcpl.EXIT_SAFE
        assert headline == "SAFE-TO-PROCEED"

    def test_mixed_orphans_fail_on_the_unexplained_ones_only(self):
        report = vcpl.Report(
            rows_examined=20,
            rows_matched=14,
            legacy_orphans=6,
            orphans_legacy_native=5,
            orphans_unexplained=1,
        )
        code, _headline, reason = vcpl.decide(report, vcpl.Options())
        assert code == vcpl.EXIT_VIOLATIONS
        assert "1 legacy row(s)" in reason

    def test_uncorroborated_legacy_native_orphans_are_surfaced(self):
        """Legacy-native only proves WHICH WRITER wrote the row.

        It does not prove the canonical sibling survived — webhook_compat
        writes canonical inside a savepoint whose exceptions it swallows. An
        orphan with no canonical row matching even on content is the case an
        operator must actually look at.
        """
        report = vcpl.Report(
            rows_examined=10,
            rows_matched=5,
            legacy_orphans=5,
            orphans_legacy_native=5,
            content_probe_attempted=5,
            content_probe_corroborated=3,
            content_probe_uncorroborated=2,
        )
        code, _headline, reason = vcpl.decide(report, vcpl.Options())
        assert "NO canonical row matching even" in reason
        assert "investigate" in reason
        # An uncorroborated orphan is a row this scan cannot show canonical
        # holds. Exit 0 here once authorized retiring the sole copy of an FDA
        # traceability record; it must be PARTIAL, never SAFE.
        assert code == vcpl.EXIT_PARTIAL
        assert code != vcpl.EXIT_SAFE, "uncorroborated orphans must never exit 0"

    def test_out_of_window_rows_downgrade_a_clean_scan(self):
        """The --since false green: the worst outcome this tool can produce.

        A clean scan of a one-month window on a multi-year compliance table
        used to exit 0 SAFE-TO-PROCEED, which would authorise retiring the
        legacy FDA fallback while unverified legacy-only rows remained.
        """
        report = vcpl.Report(
            rows_examined=5,
            rows_matched=5,
            legacy_total_in_window=5,
            legacy_out_of_window=1_000_000,
            out_of_window_oldest=datetime(2023, 1, 1, tzinfo=timezone.utc),
        )
        opts = vcpl.Options(since=datetime(2026, 7, 1, tzinfo=timezone.utc))
        code, headline, reason = vcpl.decide(report, opts)
        assert code == vcpl.EXIT_PARTIAL
        assert code != vcpl.EXIT_SAFE, "partial coverage must never exit 0"
        assert "NOT A CUTOVER DECISION" in headline
        assert "1,000,000" in reason and "OUTSIDE" in reason

    def test_violations_outrank_partial_coverage(self):
        """A real violation must not be masked by the partial-coverage path."""
        report = vcpl.Report(
            rows_examined=5,
            rows_matched=4,
            legacy_orphans=1,
            orphans_unexplained=1,
            legacy_out_of_window=99,
        )
        code, headline, _ = vcpl.decide(report, vcpl.Options(since=datetime(2026, 7, 1, tzinfo=timezone.utc)))
        assert code == vcpl.EXIT_VIOLATIONS
        assert headline == "DO-NOT-PROCEED"

    def test_unclassifiable_orphans_are_a_coverage_gap(self):
        """If the hash probe cannot be imported, nothing may be called green."""
        report = vcpl.Report(rows_examined=5, rows_matched=4, legacy_orphans=1)
        if not vcpl.LEGACY_HASH_PROBE_AVAILABLE:
            gaps = vcpl.coverage_gaps(report, vcpl.Options())
            assert any("classified" in g for g in gaps)

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
        # Previously this returned 0, so `if verify; then proceed` read a
        # truncated smoke pass as green. It now has its own exit code.
        assert code == vcpl.EXIT_PARTIAL
        assert code != vcpl.EXIT_SAFE
        assert "NOT A CUTOVER DECISION" in headline
        assert "--limit" in reason

    def test_ignored_fields_are_disclosed_in_the_verdict(self):
        report = vcpl.Report(rows_examined=3, rows_matched=3)
        code, _headline, reason = vcpl.decide(report, vcpl.Options(ignore_fields=("id",)))
        assert "--ignore-field" in reason and "id" in reason
        # A verdict that skipped a column is not a verdict on that column.
        assert code == vcpl.EXIT_PARTIAL


class TestCli:
    def test_url_normalization(self):
        for scheme in ("postgres", "postgresql", "postgresql+psycopg2", "postgresql+asyncpg", "postgresql+psycopg"):
            assert vcpl.normalize_database_url(f"{scheme}://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
        assert vcpl.normalize_database_url("sqlite:///x.db") == "sqlite:///x.db"

    def test_tenant_must_be_uuid(self):
        with pytest.raises(Exception):
            vcpl.parse_tenant("not-a-uuid")

    def test_naive_timestamps_are_utc(self):
        assert vcpl.parse_timestamp("2026-07-01").tzinfo is timezone.utc
        assert vcpl.parse_timestamp("2026-07-01T00:00:00Z").tzinfo is timezone.utc

    def test_settle_window_defaults_to_disabled(self):
        """There is no phantom-orphan race, so the default must not lose rows.

        The old 300s default was justified by a claim that webhook_compat
        commits the legacy and canonical rows in SEPARATE transactions. It
        does not — both go into one session transaction via nested
        savepoints, and dual_write_legacy is a single transaction by
        construction. A non-zero settle window is therefore pure, silent
        coverage loss on the most recent (most interesting) rows.
        """
        assert vcpl.DEFAULT_SETTLE_SECONDS == 0
        args = vcpl.build_parser().parse_args([])
        opts = vcpl.options_from_args(args)
        assert opts.until is None
        assert not opts.until_was_explicit

    def test_explicit_settle_window_still_downgrades_the_verdict(self):
        args = vcpl.build_parser().parse_args(["--settle-seconds", "300"])
        opts = vcpl.options_from_args(args)
        assert opts.until is not None
        report = vcpl.Report(
            rows_examined=5, rows_matched=5, legacy_out_of_window=2
        )
        code, _headline, _reason = vcpl.decide(report, opts)
        assert code == vcpl.EXIT_PARTIAL

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
    engine = create_engine(sync_postgres_url(database_url), future=True)
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


def _seed_webhook_compat_pair(engine, tenant: str):
    """Seed ONE event exactly the way ``webhook_compat.ingest_events`` does.

    This is the corpus every earlier live test was missing: they all built
    their rows with ``CanonicalEventStore(dual_write=True/False)`` only, so
    they exercised the one writer whose rows join by hash and never the
    writer that produces most of production's legacy rows.

    The real route (``webhook_compat.py:172`` then ``:201``) does two
    independent writes in ONE session transaction:
      1. ``CTEPersistence.store_event`` -> a legacy row whose ``sha256_hash``
         is ``cte_persistence.hashing.compute_event_hash`` over a fresh
         ``uuid4()``;
      2. ``CanonicalEventStore(dual_write=False).persist_event`` -> a
         canonical row whose ``sha256_hash`` is the canonical 10-field
         formula over a DIFFERENT ``uuid4()``.

    The two hashes cannot be equal, so the pair never joins — while both
    rows are present and correct. Returns the legacy row's hash.
    """
    import json as _json

    from shared.cte_persistence.hashing import compute_event_hash

    legacy_id = str(uuid4())
    canonical = _make_event(UUID(tenant) if isinstance(tenant, str) else tenant)
    kdes = {"gtin": "09506000134352", "ingest_source": "webhook_api"}
    timestamp = canonical.event_timestamp
    location = canonical.from_facility_reference

    legacy_hash = compute_event_hash(
        legacy_id,
        canonical.event_type.value,
        canonical.traceability_lot_code,
        "webhook product",
        canonical.quantity,
        canonical.unit_of_measure,
        location,
        location,
        timestamp.isoformat(),
        kdes,
    )
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant})
        conn.execute(
            text("""
                INSERT INTO fsma.cte_events (
                    id, tenant_id, event_type, traceability_lot_code,
                    product_description, quantity, unit_of_measure,
                    location_gln, location_name, event_timestamp,
                    source, idempotency_key, sha256_hash, chain_hash
                ) VALUES (
                    CAST(:id AS uuid), CAST(:tid AS uuid), :et, :tlc,
                    'webhook product', :q, :uom,
                    :loc, :loc, :ts,
                    'webhook_api', :idem, :sha, 'chain-wc'
                )
            """),
            {
                "id": legacy_id,
                "tid": tenant,
                "et": canonical.event_type.value,
                "tlc": canonical.traceability_lot_code,
                "q": canonical.quantity,
                "uom": canonical.unit_of_measure,
                "loc": location,
                "ts": timestamp,
                "idem": f"idem-wc-{uuid4().hex}",
                "sha": legacy_hash,
            },
        )
        for key, value in kdes.items():
            conn.execute(
                text(
                    "INSERT INTO fsma.cte_kdes (cte_event_id, tenant_id, kde_key, kde_value) "
                    "VALUES (CAST(:e AS uuid), CAST(:tid AS uuid), :k, CAST(:v AS jsonb))"
                ),
                {"e": legacy_id, "tid": tenant, "k": key, "v": _json.dumps(value)},
            )

    # The sibling canonical-only write, same content tuple, different event_id.
    session = sessionmaker(bind=engine, future=True)()
    try:
        from shared.canonical_persistence.writer import CanonicalEventStore

        session.execute(text("SET app.tenant_id = :tid"), {"tid": tenant})
        canonical.kdes = kdes
        CanonicalEventStore(session, dual_write=False).persist_event(canonical)
        session.commit()
    finally:
        session.close()
    return legacy_hash


class TestAgainstLiveDatabase:
    def test_webhook_compat_pair_is_not_reported_as_a_lost_write(self, seeded_tenant):
        """The regression that made this tool unusable against production.

        Before the fix the verifier reported every webhook_compat legacy row
        as "a canonical write was lost (#1277)" and exited 1, on a database
        where the canonical row was present the whole time. Worse, the
        documented remediation for that message is the backfill — which, fed
        these rows, would duplicate FDA traceability records.
        """
        import json

        database_url, engine, tenant = seeded_tenant
        legacy_hash = _seed_webhook_compat_pair(engine, tenant)

        result = _run_verifier(database_url, tenant)
        payload = json.loads(result.stdout)
        orphans = payload["legacy_orphans"]

        # It IS an orphan by hash — that part was never in dispute.
        assert orphans["count"] == 1
        # But it must be classified, not blamed on a lost write.
        assert orphans["legacy_native_hash_formula"] == 1
        assert orphans["unexplained"] == 0
        assert orphans["samples"][0]["orphan_class"] == "legacy-native"
        assert orphans["samples"][0]["sha256_hash"] == legacy_hash
        # And the content probe should find the canonical sibling that is
        # sitting right there in the same database.
        assert orphans["content_probe"]["corroborated"] == 1
        assert orphans["content_probe"]["uncorroborated"] == 0
        # Verdict is not a data-loss page.
        assert result.returncode == vcpl.EXIT_SAFE, result.stdout + result.stderr
        assert payload["verdict"] == "SAFE-TO-PROCEED"

    def test_a_real_lost_write_still_fails_alongside_webhook_compat_rows(self, seeded_tenant):
        """Classification must not become a blanket amnesty for orphans.

        A legacy row carrying the CANONICAL hash formula with no canonical
        twin is a genuine #1277 violation, and must still fail even when
        legacy-native orphans are present in the same corpus.
        """
        import json

        database_url, engine, tenant = seeded_tenant
        _seed_webhook_compat_pair(engine, tenant)
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant})
            conn.execute(
                text("""
                    INSERT INTO fsma.cte_events (
                        id, tenant_id, event_type, traceability_lot_code,
                        product_description, quantity, unit_of_measure,
                        location_gln, location_name, event_timestamp,
                        source, idempotency_key, sha256_hash, chain_hash
                    ) VALUES (
                        gen_random_uuid(), CAST(:tid AS uuid), 'shipping', 'TLC-REALLY-LOST',
                        'lost', 1.0, 'kg', 'GLN-X', 'GLN-X', NOW(),
                        'webhook_api', :idem, :sha, 'chain-lost'
                    )
                """),
                {"tid": tenant, "idem": f"idem-lost-{uuid4().hex}", "sha": "de" + "0" * 62},
            )

        result = _run_verifier(database_url, tenant)
        payload = json.loads(result.stdout)
        assert result.returncode == vcpl.EXIT_VIOLATIONS, result.stdout + result.stderr
        assert payload["legacy_orphans"]["count"] == 2
        assert payload["legacy_orphans"]["legacy_native_hash_formula"] == 1
        assert payload["legacy_orphans"]["unexplained"] == 1
        assert "#1277" in payload["reason"]

    def test_a_narrow_since_window_cannot_return_safe_to_proceed(self, seeded_tenant):
        """The --since false green, end to end on a real database.

        A window that hides legacy rows must never exit 0. This is the exact
        shape that would otherwise authorise retiring the legacy FDA fallback
        while unverified legacy-only rows remained.
        """
        import json

        database_url, engine, tenant = seeded_tenant
        # Backdate one legacy row out of the window (pre-dual-write history).
        # fsma.cte_events is append-only (fsma.prevent_cte_mutation, FDA
        # 21 CFR 1.1455); the trigger's own documented escape hatch is the
        # only way to stage this fixture, and it is scoped to this
        # transaction. Production data is never mutated by the verifier —
        # this is test setup, and the verifier itself is read-only.
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant})
            conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
            conn.execute(
                text(
                    "UPDATE fsma.cte_events SET ingested_at = now() - interval '400 days' "
                    "WHERE tenant_id = CAST(:tid AS uuid) "
                    "AND id = (SELECT id FROM fsma.cte_events "
                    "          WHERE tenant_id = CAST(:tid AS uuid) LIMIT 1)"
                ),
                {"tid": tenant},
            )

        since = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
        result = _run_verifier(database_url, tenant, "--since", since)
        payload = json.loads(result.stdout)
        assert result.returncode == vcpl.EXIT_PARTIAL, result.stdout + result.stderr
        assert payload["verdict"] != "SAFE-TO-PROCEED"
        assert payload["coverage"]["legacy_out_of_window"] == 1
        assert payload["coverage"]["full_coverage"] is False
        assert any("OUTSIDE" in gap for gap in payload["coverage"]["gaps"])

    def test_canonical_drift_on_recall_predicate_columns_is_detected(self, seeded_tenant):
        """Post-hoc canonical UPDATEs are real (rules/engine.py:802, writer.py:322).

        ``event_type``/``traceability_lot_code``/``event_timestamp`` are the
        recall filter's WHERE predicates, so drift there changes WHICH ROWS a
        regulator's search returns. The verifier used to compare 6 columns and
        report SAFE-TO-PROCEED through exactly this mutation.
        """
        import json

        database_url, engine, tenant = seeded_tenant
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant})
            conn.execute(
                text(
                    "UPDATE fsma.traceability_events SET quantity = 999.0, "
                    "event_timestamp = event_timestamp - interval '90 days', "
                    "traceability_lot_code = 'TLC-MUTATED' "
                    "WHERE tenant_id = CAST(:tid AS uuid)"
                ),
                {"tid": tenant},
            )

        result = _run_verifier(database_url, tenant)
        payload = json.loads(result.stdout)
        assert result.returncode == vcpl.EXIT_VIOLATIONS, result.stdout + result.stderr
        by_field = payload["field_divergence"]["by_field"]
        assert by_field["quantity"] > 0
        assert by_field["event_timestamp"] > 0
        assert by_field["traceability_lot_code"] > 0

    def test_empty_from_facility_reference_falls_back_like_the_writer(self, seeded_tenant):
        """#2535 empty-string vs NULL — the exact operand asymmetry this fix closes.

        ``dual_write_legacy`` writes ``from_facility_reference or
        to_facility_reference`` (legacy_dual_write.py). Python ``or`` falls back
        on ANY falsy left operand — the empty string '' as well as None — so an
        event whose from_facility is '' but whose to_facility is populated has
        its legacy location_gln/location_name set to the ``to`` value.

        The verifier's canonical-side expression used a bare
        ``COALESCE(from, to)``, which only substitutes on SQL NULL, so it
        evaluated '' -> '' and reported a SPURIOUS location divergence against a
        legacy row that was written correctly. After the fix
        (``COALESCE(NULLIF(from, ''), to)``) both sides agree with the writer.

        Both directions are pinned here: the clean empty-from pair must NOT
        diverge, and a genuinely wrong location on that same pair must STILL be
        caught — the fix collapses '' to the fallback, it does not blanket-mute
        the column.
        """
        import json

        from shared.canonical_persistence.writer import CanonicalEventStore

        database_url, engine, tenant = seeded_tenant
        event = _make_event(UUID(tenant))
        # from_facility '' is falsy -> the writer falls back to to_facility.
        event.from_facility_reference = ""
        event.to_facility_reference = "urn:gs1:414:9999999999999"
        tlc = event.traceability_lot_code

        session = sessionmaker(bind=engine, future=True)()
        try:
            session.execute(text("SET app.tenant_id = :tid"), {"tid": tenant})
            CanonicalEventStore(session, dual_write=True).persist_event(event)
            session.commit()
        finally:
            session.close()

        # 1) No SPURIOUS divergence: '' collapses to the to_facility fallback on
        #    BOTH sides, exactly as the writer intended.
        result = _run_verifier(database_url, tenant)
        assert result.returncode == vcpl.EXIT_SAFE, result.stdout + result.stderr
        by_field = json.loads(result.stdout)["field_divergence"]["by_field"]
        assert by_field["location_gln"] == 0, by_field
        assert by_field["location_name"] == 0, by_field

        # 2) A GENUINELY wrong location on the same pair is still detected. The
        #    append-only trigger's documented escape hatch stages the fixture and
        #    is scoped to this transaction; the verifier itself never mutates.
        with engine.begin() as conn:
            conn.execute(text("SET LOCAL app.tenant_id = :tid"), {"tid": tenant})
            conn.execute(text("SET LOCAL fsma.allow_mutation = 'true'"))
            conn.execute(
                text(
                    "UPDATE fsma.cte_events SET location_gln = 'WRONG-GLN', "
                    "location_name = 'WRONG-NAME' "
                    "WHERE tenant_id = CAST(:tid AS uuid) AND traceability_lot_code = :tlc"
                ),
                {"tid": tenant, "tlc": tlc},
            )

        result = _run_verifier(database_url, tenant)
        assert result.returncode == vcpl.EXIT_VIOLATIONS, result.stdout + result.stderr
        by_field = json.loads(result.stdout)["field_divergence"]["by_field"]
        assert by_field["location_gln"] == 1, by_field
        assert by_field["location_name"] == 1, by_field

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
