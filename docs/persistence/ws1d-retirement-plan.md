# WS-1d — dual-write retirement: mechanical application plan (#1335)

> **Status: SPECIFICATION ONLY. Nothing in this document has been applied.**
> The repo is still dual-writing and must stay that way until the production
> soak described in `docs/persistence/dual-write-cutover.md` is clean.
>
> This document exists so that WS-1d is a ~30-minute mechanical edit once the
> soak passes, instead of a re-investigation. Every claim below is anchored to
> a `file:line` that was read on 2026-08-04 against branch
> `claude/repo-review-comprehensive-1464k9`.

WS-1d is step 4 of the sequence in `docs/persistence/dual-write-cutover.md:22-26`:
*"drop `dual_write` from `CanonicalEventStore`, read-only trigger on the legacy
tables for one release, then archive."*

---

## 0. The single most important finding, read this first

**`dual_write=True` is NOT the only writer of `fsma.cte_events`.** Removing the
dual write does *not* make the legacy tables quiescent. There are **four live
production call sites of the legacy-native writer** `CTEPersistence.store_event()`
/ `store_events_batch()`, which issue their own `INSERT INTO fsma.cte_events`
(`services/shared/cte_persistence/writes.py:228`, `batch.py:307`) and
`INSERT INTO fsma.cte_kdes` (`writes.py:312`, `batch.py:399`):

| # | Call site | Reachable from |
|---|---|---|
| 1 | `services/ingestion/app/webhook_compat.py:172` (`persistence.store_event`) | `csv_templates.py:679`, `sensitech_parser.py:300`, `supplier_portal.py:976`, `edi_ingestion/routes.py:529`, `edi_ingestion/routes.py:891` — all call `webhook_compat.ingest_events` |
| 2 | `services/ingestion/app/epcis/persistence.py:749` (`persistence.store_event`) | EPCIS ingestion |
| 3 | `services/ingestion/app/webhook_router_v2/routes.py:223` (`store_events_batch`) | webhook v2 batch |
| 4 | `services/ingestion/app/webhook_router_v2/routes.py:316` (`store_event`) | webhook v2 single |

This is already documented in the cutover table
(`docs/persistence/dual-write-cutover.md:38`: *"the real ingest route
(`webhook_compat.ingest_events` = legacy `store_event` **+** canonical-only
store) appends TWO chain rows per event"*) and in the canonical verifier
(`services/shared/canonical_persistence/verification.py:166-177`).

**Consequence:** applying section 3's read-only trigger without first retiring
these four call sites turns every CSV upload, EDI 856 ingest, Sensitech parse,
supplier-portal submission, EPCIS ingest and webhook-v2 batch into a 500. See
section 6 (ordering) — this is the blast radius, and it is the riskiest item in
the whole plan.

---

## 1. Every `dual_write` reference in the repo

Counted by AST walk over `git ls-files '*.py'` (keyword arguments, parameter
declarations, and `Name`/`Attribute` loads named exactly `dual_write`;
`dual_write_legacy` / `legacy_dual_write` / `DUAL_WRITE_RECONCILIATION_NEEDED`
are different identifiers and are tracked separately in section 5).

**Total: 104 distinct source lines** — 77 keyword-argument call sites, 18
parameter declarations, 9 name/attribute load lines. (Raw AST node count is 108:
a line like `self.dual_write = dual_write` contributes both an `Attribute` and a
`Name` node. The appendix command prints the raw node count, 108.) Plus 3
string-literal `"dual_write"` occurrences in one test's kwarg-capture
assertions (`services/ingestion/tests/test_webhook_router_v2_canonical_helper.py:46,251,436`),
for **107 distinct lines mentioning it in executable positions**.

### 1a. The definition — 4 references, all in one file

| file:line | What it is | WS-1d action |
|---|---|---|
| `services/shared/canonical_persistence/writer.py:46` | `def __init__(self, session, dual_write: bool = True, skip_chain_write: bool = False)` | **Decision required.** Two options in section 2b. |
| `services/shared/canonical_persistence/writer.py:48` | `self.dual_write = dual_write` | Delete (option A) or keep as an ignored attribute (option B) |
| `services/shared/canonical_persistence/writer.py:355` | `if self.dual_write:` in `persist_event` | **Delete** — see the literal diff in section 2a |
| `services/shared/canonical_persistence/writer.py:603` | `if self.dual_write and inserted_events:` in `persist_events_batch` | **Delete** — see the literal diff in section 2a |

### 1b. Production `dual_write=True` call sites — 3, all become no-ops or deletions

| file:line | Caller | WS-1d action |
|---|---|---|
| `services/admin/app/supplier_cte_service.py:150` | `CanonicalEventStore(db, dual_write=True)` — supplier CTE → canonical bridge | **Becomes a no-op.** Delete the kwarg. Behaviour change: this path stops producing `cte_events` rows. It is the *only* production writer whose legacy rows disappear as a direct result of WS-1d. |
| `services/graph/app/routers/fsma/traceability.py:739` | `CanonicalEventStore(db, dual_write=True)` — mobile ingest bridge | **Becomes a no-op.** Delete the kwarg. Note `services/graph/tests/test_mobile_ingestion.py:99` asserts `mock_store_cls.assert_called_once_with(mock_db, dual_write=True)` and **will fail** — update it in the same commit. |
| `scripts/seed_demo_data.py:592` | `CanonicalEventStore(db, dual_write=True)` — demo seeding | **Becomes a no-op.** Delete the kwarg. Demo tenants stop getting legacy rows; acceptable, demo data is regenerated. |

### 1c. Production `dual_write=False` call sites — 10, all pure deletions of a now-default kwarg

Every one of these is already canonical-only and is behaviourally unaffected.
Under option A (section 2b) the kwarg must be deleted from all ten or the
constructor raises `TypeError`. Under option B they can be left alone.

| file:line | Notes |
|---|---|
| `services/ingestion/app/auditor_router.py:285` | canonical-only ingest |
| `services/ingestion/app/canonical_router.py:290` | canonical-only ingest |
| `services/ingestion/app/canonical_router.py:478` | canonical-only ingest |
| `services/ingestion/app/canonical_router.py:523` | canonical-only ingest |
| `services/ingestion/app/webhook_compat.py:201` | canonical half of the dual ingest — the legacy half is `webhook_compat.py:172`, see section 0 |
| `services/ingestion/app/epcis/persistence.py:801` | also `skip_chain_write=True` |
| `services/ingestion/app/webhook_router_v2/rules_eval.py:192` | also `skip_chain_write=True` |
| `services/ingestion/app/chain_verification_job.py:160` | **read-only use** — constructs the store purely to call `verify_chain_canonical` |
| `services/ingestion/app/compliance_score.py:363` | **read-only use** — same |
| `services/ingestion/app/fda_export/queries.py:330` | **read-only use** — inside `_verify_chain_for_export`, gated on `CHAIN_VERIFY_READ_CANONICAL` |

The last three are verify-only constructions; they never reach the dual-write
branch at all, so they are the safest deletions in the list.

### 1d. Test call sites — 64 kwarg sites + 17 stub parameter declarations

These are mechanical. Grouped by required action:

**Delete outright (the behaviour they assert ceases to exist) — 5 files:**

| file | Why it dies |
|---|---|
| `tests/invariants/test_dual_write_parity.py` (kwargs at `:130`, `:169`) | The whole premise is "two writers must agree". See section 5c for what replaces it. |
| `tests/shared/test_canonical_dual_write_strict_1277.py` (kwargs at `:133,161,208,238`) | Tests that `dual_write_legacy` raises rather than swallows, and that `dual_write=False` skips it. Both statements become vacuous. |
| `tests/shared/test_dual_write_legacy_mapping_2514_2532_2533_2535.py` (`:106,121,186,196` call `migration.dual_write_legacy` directly; kwargs at `:137,163`) | Tests the mapping function being deleted. |
| `tests/shared/test_dual_write_reconciliation_2521.py` | Tests `check_dual_write_reconciliation` and asserts `DUAL_WRITE_RECONCILIATION_NEEDED` still exists — both retired in section 5. |
| `tests/shared/test_chain_verify_dual_write_live.py` (kwargs at `:112,122,168`) | Its whole point (`:18`) is the two-chain-row shape the dual ingest produces. |

**Must be re-based or frozen BEFORE WS-1d — 3 files (see section 6, this is an ordering constraint, not a cleanup):**

| file:line | Problem |
|---|---|
| `tests/invariants/test_fda_export_v1_golden.py:144` | Seeds its corpus with `CanonicalEventStore(session, dual_write=True)`. This is the *only* proof that `FDA_EXPORT_V1_READ_CANONICAL` is byte-identical. Once dual-write is gone it cannot seed a legacy corpus at all. |
| `tests/invariants/test_chain_verify_golden.py:106` | Same — seeds via `dual_write=True`; it is the proof for `CHAIN_VERIFY_READ_CANONICAL`. |
| `tests/invariants/test_verify_canonical_parity_live.py:322,325` and `tests/invariants/test_backfill_canonical.py:248` | Seed a dual-written corpus to exercise the WS-1c parity/backfill tooling. |

**Mechanical kwarg deletion, no semantic change — the remaining ~52 sites:**
`tests/shared/test_canonical_persistence_hardening.py` (11),
`tests/shared/test_canonical_verify_chain_2506.py` (10),
`tests/shared/test_canonical_trace_cap_1282.py` (9),
`services/shared/tests/test_canonical_persistence_chain_race_1300.py` (7),
`tests/shared/test_canonical_persistence_tenant_context.py` (6),
`services/ingestion/tests/test_canonical_router.py` (4),
`tests/shared/test_hash_chain_fk_drop_2500.py` (3),
`tests/shared/test_canonical_batch_insert_conflict.py` (3),
`tests/shared/test_canonical_raw_payload_sizecap.py` (2),
`tests/shared/test_canonical_get_event_raw_payload_opt_in.py` (2).
All pass `dual_write=False`; all are unaffected under option B.

**Stub `__init__` signatures that shadow the real constructor — 17 declarations**
in `services/admin/tests/test_supplier_cte_service_1342.py:181`,
`services/ingestion/tests/{test_auditor_router_1342.py:523, test_canonical_router.py:221/234/429/459, test_canonical_router_1342.py:277/569, test_chain_verification_job_1342.py:111, test_dual_write_timeout_1335.py:62, test_epcis_batch_transaction_1156.py:113, test_epcis_persistence_1342.py:87, test_epcis_persistence_enforcement.py:48, test_webhook_compat_1342.py:249/626, test_webhook_compat_enforcement.py:159, test_webhook_router_v2_canonical_helper.py:42}`.
These are fakes, not the real class. Under option A they must lose the parameter
or they will silently accept a kwarg production no longer passes — which is the
*good* failure mode (test still passes) but leaves dead surface. Under option B
leave them. `test_dual_write_timeout_1335.py:66` asserts `assert dual_write is False`
and `test_webhook_router_v2_canonical_helper.py:251,436` assert the captured
kwargs dict equals `{"dual_write": False, "skip_chain_write": True}` — **these
three assertions break under option A** and must be updated.

### 1e. Non-code references that need a doc edit

| file:line | Action |
|---|---|
| `docs/DATA_MODEL.md:250-256` | Rewrite the "Migration Note" — it still says the legacy tables *"continue to receive writes"*. |
| `docs/persistence/dual-write-cutover.md:13-26,40,45,47-52,59-61` | Mark WS-1d done; the "Intentional `dual_write=False` canonical-only writers" section becomes "all writers are canonical-only". |
| `services/shared/workflows/ingest_event.py:59-60` | "Dual-write to legacy table + Kafka sync is temporary migration code" — update. |
| `services/shared/canonical_persistence/writer.py:37-38` | Class docstring: *"optionally dual-writes to fsma.cte_events (legacy) during migration"*. |
| `services/shared/canonical_persistence/verification.py:7` | Docstring reference to `dual_write=True`. |
| `alembic/versions/20260629_4c5d6e7f8a9b_v090_hash_chain_drop_cte_events_fk.py:11` | **DO NOT EDIT.** Applied migrations are historical records. Exempt it from the CI gate by path instead (section 4). |
| `services/ingestion/app/fda_export/queries.py:198-215` | The comment block documenting the invertible mapping stays — it is the justification for the canonical reader's SQL, and that SQL survives WS-1d. |

---

## 2. The exact `writer.py` change

### 2a. Stop writing the legacy tables — literal before/after

**`services/shared/canonical_persistence/writer.py`, `persist_event`, lines 344-357.**

BEFORE (verbatim, lines 344-357):

```python

        # --- Dual-write to legacy table (TEMPORARY — see migration.py) ---
        # #1277: dual_write_legacy now raises on failure instead of
        # silently returning None. That's intentional — the FDA-export
        # path still reads from the legacy table during migration, so
        # a swallowed failure would silently desync the export from
        # canonical. Letting the exception propagate rolls the
        # surrounding transaction back, so either BOTH tables have
        # the event or NEITHER does. Callers that don't want legacy
        # writes at all must opt out via ``dual_write=False``.
        legacy_id = None
        if self.dual_write:
            legacy_id = migration.dual_write_legacy(self.session, event)

```

AFTER:

```python

        # WS-1d (#1335): the legacy dual-write is retired. fsma.cte_events /
        # fsma.cte_kdes are read-only (Alembic v1XX installs
        # fsma.prevent_cte_write); fsma.traceability_events is the sole
        # store of record. ``legacy_event_id`` is retained on
        # CanonicalStoreResult and always None so the result shape is
        # unchanged for callers.
        legacy_id = None

```

**Same file, `persist_events_batch`, lines 588-605.**

BEFORE (verbatim, lines 588-605):

```python

        # --- Dual-write legacy (TEMPORARY — see migration.py) ---
        # Only dual-write events that actually inserted here; an event
        # we lost to a concurrent writer was (presumably) dual-written
        # by that winner and re-writing would just duplicate in legacy.
        #
        # #1277: previously this loop wrapped dual_write_legacy in a
        # try/except and logged-and-continued on failure. That swallowed
        # the invariant "canonical row landed → legacy row landed",
        # which in turn meant the FDA-export path (still reading from
        # the legacy table during migration) silently diverged from the
        # canonical source of truth. The fix is to let the exception
        # propagate — the surrounding transaction rolls back, the
        # canonical INSERTs are reverted, and the caller gets a loud
        # failure instead of a silent data-integrity violation.
        if self.dual_write and inserted_events:
            for evt in inserted_events:
                migration.dual_write_legacy(self.session, evt)

```

AFTER:

```python

        # WS-1d (#1335): legacy dual-write retired — see persist_event.

```

**Do NOT touch these in the same edit:**

- `writer.py:23` — `from shared.canonical_persistence import legacy_dual_write as migration`
  **stays.** `migration.stage_graph_sync(self.session, event)` at `writer.py:371`
  is the #1276 transactional-outbox hook for Neo4j sync and is *not* part of
  WS-1d. Removing the import breaks it.
- `writer.py:392` — `legacy_event_id=legacy_id,` **stays.** It is a declared
  slot on `CanonicalStoreResult` (`models.py:18`); dropping it changes the
  result shape. It just becomes permanently `None`.
- `writer.py:335-343` — the `hash_chain` insert. Unrelated.

### 2b. The `dual_write` parameter itself — the one real decision

**Option A — delete the parameter.**
`def __init__(self, session: Session, skip_chain_write: bool = False)`.
Loud and complete: any missed caller raises `TypeError` immediately.
Cost: all 13 production kwarg sites (1b + 1c), all 64 test kwarg sites, the 17
stub signatures, and the 3 assertions listed at the end of 1d must change in the
same commit. Nothing can be staged.

**Option B — keep the parameter, ignore it, deprecate it.**

```python
    def __init__(self, session: Session, dual_write: bool = False, skip_chain_write: bool = False):
        # WS-1d (#1335): ``dual_write`` is retained for signature
        # compatibility and is IGNORED. The legacy tables are read-only.
        if dual_write:
            warnings.warn(
                "CanonicalEventStore(dual_write=True) is a no-op since WS-1d "
                "(#1335); fsma.cte_events is read-only.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.session = session
        self.dual_write = False
        self.skip_chain_write = skip_chain_write
```

Note the default flips `True → False`, which is itself the safety property: a
caller that forgets to update gets canonical-only, not a crash.

**Recommendation: Option B for the WS-1d commit, Option A as a follow-up
cleanup one release later.** Rationale: WS-1d already changes production write
behaviour and installs a DB trigger. Coupling that to a 90-file mechanical
signature change makes the diff unreviewable and makes a targeted revert
impossible. Option B's diff is ~40 lines. This mirrors the deprecation shape
already used for the legacy writer at
`services/shared/cte_persistence/writes.py:94-100` and `batch.py:55-61`.

---

## 3. Alembic migration — legacy tables read-only

> **This is the literal file content for the operator to save. It is NOT
> created in `alembic/versions/` by this plan. Creating it now would make the
> repo un-deployable, because the four legacy-native writers in section 0 are
> still live.**

Save as `alembic/versions/<YYYYMMDD>_<rev>_v1XX_ws1d_cte_events_readonly.py`.

**Before saving, do two things:**

1. Generate a real revision id (`python -m alembic revision -m "v1XX ws1d cte events readonly"`)
   and replace `WS1D_PLACEHOLDER_REVISION`.
2. Re-derive `down_revision` from the actual head. **The head at the time this
   plan was written is `51701aedee57` (v109,
   `alembic/versions/20260802_51701aedee57_v109_team_roster_security_definer.py:27`)
   — not v093 as some task briefs state.** Confirm with
   `python -m alembic heads` before committing.

### Design notes (each anchored)

- **Reuses the existing break-glass GUC `fsma.allow_mutation`**, established by
  v078 (`alembic/versions/20260505_5ac9e7b1d402_v078_orphan_migration_forward_ports.py:1343`)
  and corrected by v107 (`20260801_c35358cae7d4_v107_cte_mutation_update_returns_new.py:38-41`).
  One documented escape hatch, not two.
- **Blocks INSERT only.** UPDATE and DELETE on `fsma.cte_events` are already
  governed by the v078 `cte_events_append_only` trigger. DELETE **must remain
  reachable** — `services/scheduler/service.py:1215` runs the 1095-day FSMA
  retention purge (`DELETE FROM fsma.cte_events WHERE ingested_at < NOW() - INTERVAL '1095 days'`)
  under `set_config('fsma.allow_mutation','true',true)` at
  `services/scheduler/service.py:1211-1213`. Blocking DELETE would break FDA
  retention compliance. `cte_kdes` rows go via `ON DELETE CASCADE`
  (`services/scheduler/service.py:1199-1201`), so `cte_kdes` gets an INSERT
  block only and no UPDATE/DELETE trigger at all.
- **Returns `NEW` for INSERT** when the GUC is set. A `BEFORE INSERT` trigger
  returning `OLD` (which is `NULL` for INSERT) silently *skips* the row — the
  exact class of bug v107 was written to fix.
- **Separate function name** `fsma.prevent_cte_write()`. Do **not** extend
  `fsma.prevent_cte_mutation()` — it is shared with `fsma.hash_chain`
  (`v078:1362-1366`), and adding an INSERT branch there would block every
  canonical chain append.
- **`to_regclass` guards** mirror v078's `DO $$ ... IF to_regclass(...) IS NOT NULL`
  shape so the migration is safe on a database where the legacy tables were
  already archived.
- **Triggers apply to the table owner and to superusers.** Unlike RLS, there is
  no `BYPASS`. The backfill (`scripts/backfill_canonical_from_legacy.py`) reads
  legacy and writes canonical, so it is unaffected — but any operator recovery
  that needs to write `cte_events` must `SET LOCAL fsma.allow_mutation = 'true'`.

### File content

```python
"""v1XX — WS-1d: make fsma.cte_events / fsma.cte_kdes read-only (#1335).

The canonical store ``fsma.traceability_events`` is now the sole store of
record. ``CanonicalEventStore.persist_event`` no longer dual-writes
(``services/shared/canonical_persistence/writer.py``), and the legacy-native
``CTEPersistence.store_event`` / ``store_events_batch`` writers have been
retired from every ingestion route. This migration is the database-side
enforcement of that: a new row can no longer appear in either legacy table.

Scope — INSERT only, deliberately:

* UPDATE / DELETE on ``fsma.cte_events`` are already governed by the v078
  ``cte_events_append_only`` trigger (fixed by v107 to RETURN NEW on UPDATE).
* DELETE must stay reachable: ``services/scheduler/service.py`` runs the
  1095-day FSMA retention purge under ``fsma.allow_mutation='true'``, and
  ``fsma.cte_kdes`` rows are removed by ON DELETE CASCADE. Blocking DELETE
  would break retention compliance (FDA 21 CFR 1.1455 recordkeeping window).

Break-glass: ``SET LOCAL fsma.allow_mutation = 'true'`` — the same GUC v078
established for authorized corrections. Transaction-local; clears at COMMIT.

Reversibility is the safety story: ``downgrade()`` drops ONLY the two new
triggers and the new function, restoring writability exactly. It must never
touch ``fsma.prevent_cte_mutation`` (v078/v107) — dropping that would silently
remove the append-only guarantee on cte_events and hash_chain.

Revision ID: WS1D_PLACEHOLDER_REVISION
Revises: 51701aedee57
Create Date: <fill in>
"""

from alembic import op

# revision identifiers, used by Alembic.
# WS-1d OPERATOR: replace with the id produced by `alembic revision`, and
# re-confirm down_revision against `alembic heads` at apply time.
revision = "WS1D_PLACEHOLDER_REVISION"  # pragma: allowlist secret
down_revision = "51701aedee57"  # pragma: allowlist secret  (v109 — VERIFY)
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fsma.prevent_cte_write()
        RETURNS TRIGGER LANGUAGE plpgsql AS $$
        BEGIN
            IF current_setting('fsma.allow_mutation', true) = 'true' THEN
                -- BEFORE INSERT must RETURN NEW; returning OLD (NULL on
                -- INSERT) would silently skip the row. See v107.
                IF TG_OP = 'INSERT' THEN
                    RETURN NEW;
                END IF;
                RETURN OLD;
            END IF;
            RAISE EXCEPTION
                'fsma.% is read-only since WS-1d (#1335). fsma.traceability_events is the store of record. Set fsma.allow_mutation=true for an authorized backfill/correction. Operation: %',
                TG_TABLE_NAME, TG_OP;
        END;
        $$;

        DO $$
        BEGIN
            IF to_regclass('fsma.cte_events') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS cte_events_readonly ON fsma.cte_events;
                CREATE TRIGGER cte_events_readonly
                    BEFORE INSERT ON fsma.cte_events
                    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_cte_write();
            END IF;

            IF to_regclass('fsma.cte_kdes') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS cte_kdes_readonly ON fsma.cte_kdes;
                CREATE TRIGGER cte_kdes_readonly
                    BEFORE INSERT ON fsma.cte_kdes
                    FOR EACH ROW EXECUTE FUNCTION fsma.prevent_cte_write();
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Restore writability to the legacy tables.

    This is the whole safety story for WS-1d: if a consumer or ingestion
    path turns out to still need legacy writes, `alembic downgrade -1`
    restores the pre-WS-1d database behaviour in one statement, with no
    data movement and no application deploy.

    Drops ONLY what upgrade() created. fsma.prevent_cte_mutation (v078,
    body corrected by v107) and the cte_events_append_only /
    hash_chain_append_only triggers are left untouched.
    """
    op.execute(
        """
        DO $$
        BEGIN
            IF to_regclass('fsma.cte_events') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS cte_events_readonly ON fsma.cte_events;
            END IF;
            IF to_regclass('fsma.cte_kdes') IS NOT NULL THEN
                DROP TRIGGER IF EXISTS cte_kdes_readonly ON fsma.cte_kdes;
            END IF;
        END $$;

        DROP FUNCTION IF EXISTS fsma.prevent_cte_write();
        """
    )
```

### Verified locally, 2026-08-04 — this DDL was executed, not just written

Against a scratch Postgres brought to `alembic upgrade head` (which reported
`51701aedee57`, confirming v109 is the head, and showed exactly two pre-existing
non-internal triggers: `cte_events.cte_events_append_only` and
`hash_chain.hash_chain_append_only` — **`fsma.cte_kdes` has none**, as assumed
above). Applying the `upgrade()` body then produced:

| Check | Result |
|---|---|
| `INSERT INTO fsma.cte_events` with no GUC | `ERROR: fsma.cte_events is read-only since WS-1d (#1335) … Operation: INSERT` |
| `INSERT INTO fsma.cte_kdes` with no GUC | `ERROR: fsma.cte_kdes is read-only since WS-1d (#1335) … Operation: INSERT` |
| Same two INSERTs after `set_config('fsma.allow_mutation','true',true)` | `INSERT 0 1` / `INSERT 0 1` — confirms the `RETURN NEW` branch |
| `UPDATE fsma.cte_events` with no GUC | `ERROR: CTE records are append-only (FDA 21 CFR 1.1455) … Table: cte_events, Operation: UPDATE` from `fsma.prevent_cte_mutation()` — v078/v107 unchanged |
| Scheduler retention shape: `DELETE … WHERE ingested_at < NOW() - INTERVAL '1095 days'` under the GUC | `DELETE 1`, and `cte_kdes` count went to 0 via `ON DELETE CASCADE` |
| `INSERT INTO fsma.hash_chain` with no GUC | `INSERT 0 1` — canonical chain appends unaffected |
| `downgrade()` body | Both new triggers dropped, `fsma.prevent_cte_write` dropped, `prevent_cte_mutation` and both append-only triggers still present, and a plain `INSERT` into both legacy tables succeeded again with **no GUC** |

Note for whoever writes the acceptance test: `fsma.cte_events` has `NOT NULL` on
`product_description`, `quantity`, `unit_of_measure`, `sha256_hash` **and**
`chain_hash`, so a minimal probe row must supply all of them.

### Migration acceptance test to add alongside it

Mirror the shape of
`services/shared/cte_persistence/tests/test_append_only_1334_1335.py:370-399`
(which asserts on the v078 source text) plus a live-DB test that:

1. `INSERT INTO fsma.cte_events (...)` raises, message contains `read-only since WS-1d`;
2. the same INSERT succeeds after `SET LOCAL fsma.allow_mutation = 'true'`;
3. `DELETE FROM fsma.cte_events` under the GUC still succeeds (retention purge regression);
4. `INSERT INTO fsma.hash_chain (...)` still succeeds — proves
   `prevent_cte_mutation` was not accidentally widened;
5. `alembic downgrade -1` then re-INSERT succeeds — proves reversibility.

`tests/migrations/test_rls_coverage.py` is unaffected: no tables are added or
dropped, so the "every `fsma.*` table is RLS-hardened" assertion still holds.

---

## 4. CI grep gate — block a new dual-write call site

Plugs into `scripts/check_legacy_dead_code.py`, which already runs in CI at
`.github/workflows/legacy-code-scan.yml:60`
(`python3 scripts/check_legacy_dead_code.py`) on every PR touching
`services/**`, `scripts/**`, `tests/**` or `docs/**`
(`legacy-code-scan.yml:4-28`).

### 4a. Add to `BANNED_PATTERNS` (currently `scripts/check_legacy_dead_code.py:207-253`)

Insert after the existing `legacy-per-service-railway-host` entry, using the
same `LegacyPattern(code, regex, message)` dataclass
(`check_legacy_dead_code.py:81-86`):

```python
    LegacyPattern(
        "ws1d-dual-write-call-site",
        re.compile(r"CanonicalEventStore\s*\(\s*[^)]*\bdual_write\b"),
        "The legacy dual-write was retired in WS-1d (#1335). fsma.cte_events "
        "and fsma.cte_kdes are read-only at the database level; a dual_write "
        "kwarg is a no-op that will mislead the next reader. Write only "
        "fsma.traceability_events via CanonicalEventStore(session).",
    ),
    LegacyPattern(
        "ws1d-legacy-dual-write-import",
        re.compile(r"\bdual_write_legacy\b"),
        "shared.canonical_persistence.legacy_dual_write.dual_write_legacy was "
        "deleted in WS-1d (#1335). Nothing may write fsma.cte_events.",
    ),
    LegacyPattern(
        "ws1d-legacy-native-cte-writer",
        re.compile(r"\.store_events?_batch\s*\(|\.store_event\s*\("),
        "CTEPersistence.store_event / store_events_batch write fsma.cte_events "
        "directly and were retired in WS-1d (#1335). Use "
        "shared.canonical_persistence.CanonicalEventStore.",
    ),
```

The third pattern is the one that actually protects the trigger from section 3 —
it guards the four legacy-native writers in section 0, which the `dual_write`
regex would never see.

### 4b. Required exclusions

`EXCLUDED_FILES` (`check_legacy_dead_code.py:66-70`) must gain:

```python
    "alembic/versions/20260629_4c5d6e7f8a9b_v090_hash_chain_drop_cte_events_fk.py",
    "docs/persistence/dual-write-cutover.md",
    "docs/persistence/ws1d-retirement-plan.md",
```

Reasons, each verified:
- `v090:11` contains the literal `` `CanonicalEventStore(dual_write=False)` `` in
  its docstring. **Applied migrations are historical records and must never be
  edited**, so the exemption is by path.
- `dual-write-cutover.md` and this plan quote the retired call syntax by design;
  the scan covers `.md` (`TEXT_SUFFIXES` at `check_legacy_dead_code.py:22-42`).

If the WS-1d commit deletes `scripts/verify_canonical_parity_live.py`,
`scripts/backfill_canonical_from_legacy.py` and the reconciliation check
(section 5), no further exclusions are needed — those are the only other files
carrying the literal strings outside tests, which are themselves deleted.

### 4c. Negative-tested, per the established shape

`tests/scripts/test_check_legacy_dead_code.py` currently proves
`check_manual_agent_sweep` both ways — a passing case (`:22-28`) and a blocking
case (`:31-40`). Add the equivalent pair against `check_patterns(files, root)`
(`check_legacy_dead_code.py:328`), which takes an iterable of paths and a root
so it is `tmp_path`-testable exactly like the sweep guard:

```python
def test_ws1d_gate_blocks_new_dual_write_call_site(tmp_path: Path) -> None:
    src = tmp_path / "services" / "x" / "writer_caller.py"
    src.parent.mkdir(parents=True)
    src.write_text("store = CanonicalEventStore(db, dual_write=True)\n", encoding="utf-8")

    findings = _MODULE.check_patterns([src], tmp_path)

    assert [f.code for f in findings] == ["ws1d-dual-write-call-site"]


def test_ws1d_gate_allows_canonical_only_construction(tmp_path: Path) -> None:
    src = tmp_path / "services" / "x" / "writer_caller.py"
    src.parent.mkdir(parents=True)
    src.write_text("store = CanonicalEventStore(db)\n", encoding="utf-8")

    assert _MODULE.check_patterns([src], tmp_path) == []
```

Note `check_patterns` calls `should_skip` → `relpath(path, root)`, so the
temporary file must live under `tmp_path`. The module is loaded once at import
via `_load_module()` (`tests/scripts/test_check_legacy_dead_code.py:10-19`);
reuse `_MODULE`.

**Do not add these patterns before WS-1d ships** — all three would fire on
`webhook_compat.py:172`, `epcis/persistence.py:749`,
`webhook_router_v2/routes.py:223,316` and the three `dual_write=True` sites
today, turning CI red on `main`.

---

## 5. Everything retired alongside

### 5a. `DUAL_WRITE_RECONCILIATION_NEEDED`

- **Definition:** `services/shared/cte_persistence/core.py:103`
  (`DUAL_WRITE_RECONCILIATION_NEEDED = True`), with the explanatory block at
  `core.py:90-102` which states outright: *"The marker stays `True` because the
  dual-write shim is still LIVE; it flips to `False` / is deleted only when the
  shim is removed under #1335."*
- **Action:** delete the constant and the comment block. Deleting is better than
  flipping to `False` — a `False` constant is dead surface that a future grep
  will misread as "reconciliation was considered and rejected".
- **Guard test to delete:**
  `tests/shared/test_cte_persistence_cluster_1323_1324_1334_1335.py:300-307`
  (`test_dual_write_reconciliation_marker_present`) asserts the attribute exists.

### 5b. The reconciliation and parity tooling

| Artifact | Action | Anchor |
|---|---|---|
| `check_dual_write_reconciliation` in `scripts/validate_data_integrity.py:96-172` | **Delete the function** and its entry in the `checks` list at `validate_data_integrity.py:226`. It compares the two stores by `sha256_hash`; with one writer the "legacy orphan" count is frozen and can only ever go stale. | `validate_data_integrity.py:96,226` |
| `scripts/verify_canonical_parity_live.py` (1300+ lines) | **Delete after the final pre-cutover run.** Its contract (`:59-70`) is "a LEGACY row with no canonical twin is a HARD FAILURE" — meaningless once legacy is frozen. Archive its final green output as the soak evidence. | `verify_canonical_parity_live.py:26-83` |
| `scripts/backfill_canonical_from_legacy.py` | **Keep through WS-1d, delete one release later.** It is the *repair tool* if the trigger surfaces a gap. Deleting it in the same commit removes the only remedy at exactly the moment it might be needed. `--dry-run` is its default (`:135`). | `backfill_canonical_from_legacy.py:1-22,135` |
| `tests/invariants/test_verify_canonical_parity_live.py`, `tests/invariants/test_backfill_canonical.py` | Delete with the script they cover; both seed via `dual_write=True` (`:322`, `:248`). | — |
| Ops runbooks | `docs/persistence/dual-write-cutover.md:45` says *"retire from runbooks at WS-1d acceptance"*. Note: `validate_data_integrity.py` is **not** invoked by any workflow in `.github/` today — grep returned nothing — so the runbook edit is documentation-only. | — |

### 5c. `tests/invariants/test_dual_write_parity.py` — and what replaces its guarantee

This file is the WS-1a freeze (`docs/persistence/dual-write-cutover.md:13-16`).
It runs in CI at `.github/workflows/backend-ci.yml:854`, in the *"RLS coverage +
tenant-isolation e2e (alembic head)"* step against a live migrated Postgres.
It asserts two things:

1. `test_ingest_writes_both_stores_with_matching_hash` (`:124-154`) — a
   `dual_write=True` ingest lands in both tables with the same `sha256_hash`.
2. `test_no_legacy_orphans_after_ingest` (`:156-189`) — no `cte_events` row
   lacks a canonical twin by `sha256_hash`.

**Assertion 1 is genuinely meaningless after WS-1d** — there is only one writer,
so there is nothing to compare. Delete it.

**Assertion 2 is NOT meaningless, and must not simply be deleted.** It is the
standing proof that no canonical write was lost. Replace it with two things:

- **Primary replacement — the database trigger from section 3.** Once
  `cte_events_readonly` is installed, a new legacy orphan is not merely
  *detected*, it is *impossible*: no process can insert a `cte_events` row at
  all. That is a strictly stronger guarantee than a periodic reconciliation
  query, and it is enforced at the storage layer rather than in CI. The
  migration acceptance test in section 3 is what proves the trigger holds.
- **Secondary replacement — a frozen-count invariant.** Add
  `tests/invariants/test_legacy_store_frozen.py` in the same CI step
  (`backend-ci.yml:854`, swap the filename in place) asserting that after a full
  canonical ingest against the migrated DB, `SELECT COUNT(*) FROM fsma.cte_events`
  is **unchanged**, and that a direct `INSERT INTO fsma.cte_events` raises. This
  keeps a live-Postgres invariant in exactly the CI slot the parity test
  occupied, so the step's coverage does not silently shrink.

Reuse the existing fixtures verbatim: `migrated_db` (`test_dual_write_parity.py:45-63`)
and `tenant_session` (`:98-120`), both built on
`tests/migrations/rls_db.rls_postgres_or_skip` / `skip_or_fail_db` and honouring
`REGENGINE_REQUIRE_DB=1` (#2530).

### 5d. `services/shared/canonical_persistence/legacy_dual_write.py`

**Do not delete the file.** It still owns `stage_graph_sync`, `publish_graph_sync`,
`_drain_pending_graph_sync`, `_clear_pending_graph_sync[_soft]` — the #1276
transactional-outbox hooks called from `writer.py:371` and covered by
`tests/shared/test_canonical_graph_outbox_1276.py` (12 references).

Delete from it only:
- `dual_write_legacy` (`legacy_dual_write.py:212-330`)
- `_STATUS_TO_VALIDATION_STATUS` / `_map_validation_status` (`:76-100`) — only
  consumed at `:286`
- `_jsonify_kde` (`:115-127`) — only consumed at `:325`
- `("fsma", "cte_events")` and `("fsma", "cte_kdes")` from `_REQUIRED_TABLES`
  (`:137-141`) — the startup guard should stop demanding tables nothing writes
- the module docstring's dual-write framing (`:1-16`)

Then **rename the module** (e.g. `graph_sync_outbox.py`) so the name stops
implying a dual write, updating `writer.py:23`,
`services/shared/canonical_persistence/__init__.py:7`, and
`services/shared/tests/test_legacy_dual_write_rename_1293.py` (which pins the
import path — it will need the same rename treatment #1293 already applied once).

The graph-sync producer is separately gated OFF by `ENABLE_NEO4J_SYNC`
(`legacy_dual_write.py:189-190`) and is scheduled for deletion under the Neo4j
retirement, not WS-1d. Keep those concerns separate.

---

## 6. Ordering constraints and blast radius

### 6a. Hard prerequisites — apply WS-1d only when ALL are true

| # | Prerequisite | Verify by |
|---|---|---|
| P1 | **The four legacy-native writers in section 0 are retired.** This is the gating item, not the dual write. | `grep -rn "\.store_event(\|store_events_batch(" services/ --include="*.py"` returns only definitions in `services/shared/cte_persistence/`. |
| P2 | `FDA_EXPORT_V1_READ_CANONICAL` is the **code default**, not just a prod env var. Today: default `"0"` at `services/ingestion/app/fda_export/queries.py:225`; prod flag observed set 2026-07-17 (`dual-write-cutover.md:36`). | `export_v1_reads_canonical()` returns `True` with no env set. |
| P3 | ✅ **Done 2026-09-02 (#3039)** — `CHAIN_VERIFY_READ_CANONICAL` is the code default (`services/shared/canonical_persistence/verification.py`); `=0` remains as emergency rollback. | `chain_verify_reads_canonical()` returns `True` with no env set. |
| P4 | **Backfill complete and green.** `scripts/verify_canonical_parity_live.py` reports 0 legacy orphans over the full production corpus. | Its own exit code; contract at `verify_canonical_parity_live.py:59-70`. |
| P5 | The two golden suites are re-based or frozen (see 6c). | — |
| P6 | Production soak of P2+P3 defaults for one full release with no export/verification incident. | `dual-write-cutover.md:17-19` |

### 6b. What breaks if WS-1d is applied before the backfill (P4)

The backfill repairs legacy rows that have **no canonical twin**
(`backfill_canonical_from_legacy.py:15-19`: *"Legacy-only rows are the error
this script repairs"*). Those rows are real FDA traceability records that exist
**only** in `fsma.cte_events`.

Applying WS-1d first does not delete them, but it does this:

1. Every read path is now canonical-only (P2/P3), so those events **vanish from
   the regulator-facing FDA CSV export** — a recall query returns fewer rows
   than the database actually holds. For FSMA 204 this is a completeness
   failure, not a performance issue.
2. `fetch_recall_events_canonical` (`queries.py:282-312`) reads
   `fsma.traceability_events` exclusively; there is no union, no fallback.
3. The gap becomes **harder to repair**, because the backfill's oracle depends on
   the legacy row's `sha256_hash` still being reconcilable against a dual-written
   corpus (`backfill_canonical_from_legacy.py:50-60` — it uses the canonical hash
   preimage to disambiguate the `from_facility` / `to_facility` collapse that
   `dual_write_legacy` performs at `legacy_dual_write.py:275-276`). Once no new
   dual-written rows exist, the population of examples that validate the
   inversion stops growing.
4. `check_dual_write_reconciliation` (`validate_data_integrity.py:96`) would keep
   reporting the orphans, but section 5b deletes it — so the detector and the
   condition it detects would be removed in the same commit.

**Therefore: backfill → verify 0 orphans → then WS-1d. Never the reverse.**

### 6c. The FDA-export fallback story after WS-1d

**Before WS-1d:** `services/ingestion/app/fda_export/recall.py:125-146` is a live
A/B. `export_v1_reads_canonical()` false → `fetch_recall_events` reads
`fsma.cte_events` + `cte_kdes`; true → `fetch_recall_events_canonical` reads
`fsma.traceability_events`. Flipping the env var back is a **complete,
instantaneous rollback with no deploy**, because both stores hold the same data.

**After WS-1d:** that rollback is gone. `fsma.cte_events` stops receiving rows at
the instant the trigger lands, so every event ingested after that moment exists
only in canonical. Setting `FDA_EXPORT_V1_READ_CANONICAL=0` would then produce an
export that is *silently missing all recent events* — strictly worse than the
canonical path it "rolls back" to. The same reasoning applies to
`CHAIN_VERIFY_READ_CANONICAL` and `_verify_chain_for_export`
(`queries.py:315-331`).

**The fallback must therefore be re-defined, in this order:**

1. **Delete the legacy branch rather than leave it as a trap.** Remove
   `build_recall_where_clause` / `fetch_recall_events` (`queries.py:129`),
   `export_v1_reads_canonical` (`:223`) and the `if/else` at `recall.py:125-146`,
   collapsing to the canonical reader. Same for `chain_verify_reads_canonical`
   (`verification.py:65`) and the branch at `queries.py:327-331`. A flag whose
   "off" position now returns incomplete regulatory data is a liability.
2. **The new rollback is `alembic downgrade -1`.** This is exactly why
   section 3's `downgrade()` matters and why it must be tested: it restores
   writability to the legacy tables in one statement with no data movement,
   so re-enabling dual-write is an application-code revert plus a downgrade,
   not a data recovery operation.
3. **The new proof of export integrity** is the canonical hash chain —
   `verify_chain_canonical` (`verification.py`) and the `X-Chain-Integrity`
   header — no longer cross-store agreement.

**Consequence for the golden suites (prerequisite P5).** Both
`tests/invariants/test_fda_export_v1_golden.py:144` and
`tests/invariants/test_chain_verify_golden.py:106` seed their corpora with
`CanonicalEventStore(session, dual_write=True)` and then compare the legacy
reader against the canonical reader. After WS-1d they cannot seed a legacy
corpus at all — and step 1 above deletes the legacy reader they compare against.
So **before** WS-1d, capture their current output as a checked-in fixture and
convert them into "canonical reader still produces this exact byte sequence"
regression tests. If this is skipped, the byte-identical guarantee that
justified the entire read-path cutover disappears with no replacement, and the
CI step at `backend-ci.yml:854-856` loses three of its five invariant suites at
once.

### 6d. Recommended commit sequence

1. Retire the four legacy-native writers (P1). Ship. Soak.
2. Flip P2/P3 code defaults; delete the legacy reader branches. Ship. Soak.
3. Freeze the goldens into fixture-based regression tests (P5).
4. Run the backfill to zero orphans (P4); archive the parity report.
5. **WS-1d commit:** `writer.py` change (section 2) + the migration (section 3) +
   test retirements (sections 1d, 5c) + doc updates (1e).
6. **WS-1d+1:** add the three CI patterns (section 4) — they must land *after*
   the call sites are gone or `main` goes red.
7. **WS-1d+2 (one release later):** Option A signature cleanup; delete
   `backfill_canonical_from_legacy.py`; archive the legacy tables.

### 6e. Blast-radius summary

| If applied prematurely | Symptom | Severity |
|---|---|---|
| Before P1 (legacy-native writers) | CSV / EDI / Sensitech / supplier-portal / EPCIS / webhook-v2 ingest all raise `fsma.cte_events is read-only`. Total ingestion outage. | **Critical** |
| Before P4 (backfill) | Legacy-only FDA records silently absent from regulator-facing exports; repair tooling degraded. | **Critical (compliance)** |
| Before P2/P3 defaults | Default-configured environments read empty legacy tables → exports return zero rows. | **Critical** |
| Before P5 (goldens) | Byte-identical export proof deleted with no replacement. | **High** |
| With `downgrade()` untested | The only rollback is unverified at the moment it is needed. | **High** |
| Section 4 patterns added early | `main` CI red on 7+ existing call sites. | Medium |
| `prevent_cte_mutation` extended instead of a new function | Every canonical `hash_chain` append blocked → all ingestion fails. | **Critical** |
| DELETE blocked on `cte_events` | 1095-day FSMA retention purge (`services/scheduler/service.py:1213-1216`) raises a SQLAlchemy `DatabaseError`, which is **not** in the caught tuple at `service.py:1233` (`ImportError, RuntimeError, ConnectionError, ValueError`) — so it escapes `_archive_expired_data` uncaught and aborts the archival job rather than logging `data_archival_failed`. | High |

---

## Appendix — verification commands for the operator

```bash
# 1. Confirm the dual_write inventory has not drifted from this document.
python3 - <<'EOF'
import ast, pathlib, subprocess
files = subprocess.run(["git","ls-files","*.py"],capture_output=True,text=True).stdout.split()
kw=params=attrs=0
for f in files:
    try: tree=ast.parse(pathlib.Path(f).read_text(errors="ignore"))
    except SyntaxError: continue
    for n in ast.walk(tree):
        if isinstance(n,ast.Call): kw+=sum(1 for k in n.keywords if k.arg=="dual_write")
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
            a=n.args
            params+=sum(1 for x in list(a.posonlyargs)+list(a.args)+list(a.kwonlyargs) if x.arg=="dual_write")
        if isinstance(n,ast.Attribute) and n.attr=="dual_write": attrs+=1
        if isinstance(n,ast.Name) and n.id=="dual_write": attrs+=1
print(f"kwargs={kw} params={params} refs={attrs} total={kw+params+attrs}")
EOF
# Expected as of 2026-08-04: kwargs=77 params=18 refs=13 total=108
# (refs counts raw AST nodes across 9 distinct lines — `self.dual_write =
#  dual_write` contributes an Attribute node and a Name node.)

# 2. Confirm P1 — no legacy-native writer call sites remain.
grep -rn "\.store_event(\|\.store_events_batch(" services/ --include="*.py" | grep -v "/tests/"

# 3. Confirm the alembic head before writing down_revision.
python3 -m alembic heads

# 4. Confirm the read-path flag defaults (P2/P3).
python3 -c "import os,sys; sys.path[:0]=['services']; \
from app.fda_export.queries import export_v1_reads_canonical as a; \
from shared.canonical_persistence.verification import chain_verify_reads_canonical as b; \
print('export_v1:',a(),'chain_verify:',b())"
```
