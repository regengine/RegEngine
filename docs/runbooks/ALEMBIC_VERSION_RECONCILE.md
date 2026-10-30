# Alembic version-row reconcile runbook

**Severity:** SEV2 if a deploy is pending (a deploy runs `alembic upgrade head`)
**Owner:** Christopher Sellers
**Last updated:** 2026-10-30
**Decision record:** `docs/decisions/2026-10-30-schema-change-channel.md`

> The agent that wrote this did not run anything against a database. Every
> command below is for Christopher to run. The only script that touches a
> database here is read-only.

## 0. When to use this

Use it when `public.alembic_version` on the production database does not
match what the catalog shows. Today that is the case: the row reads
`267d8053ced5` (v079) while effects of v128, v131 and v134 to v137 are
present, because those reached production through `supabase/migrations/`
and `sql/prod-apply/`.

Do not use it to "get the row to head". The row is reconciled to what the
catalog proves, nothing more.

## 1. Preconditions

- A current backup with a tested restore, per
  `docs/operations/DISASTER_RECOVERY.md`.
- A read-only database session. Any of: the Supabase SQL editor on a
  read-only role, or `psql` with a role that has `SELECT` on `pg_catalog`
  and `public.alembic_version`.
- The repository checked out at the commit you are reconciling against.
  Note its SHA; the precheck's signature table is tied to the revision files
  in that tree.

## 2. Run the precheck

```bash
psql -X -v ON_ERROR_STOP=1 -f sql/prod-apply/PRECHECK_alembic_version_reconcile.sql
```

The script opens a `BEGIN READ ONLY` transaction with a 15-second statement
timeout, reads `pg_catalog` and the version row, and rolls back. It writes
nothing. It returns three result sets:

1. `alembic_version`: the row as recorded.
2. One line per revision after v079, in chain order, with `present` =
   `true`, `false` or `NULL` (not observable: merge revisions, data-only
   revisions, or a role the check needs is absent).
3. A summary: `recorded_version`, `supported_through_revision` (the last
   revision before the first `false`), counts, and
   `present_beyond_first_gap` (effects that exist past that point).

The three `absent_*` signatures (v088, v090 `4c5d6e7f8a9b`, v132) read
`true` on any database that never had the object, so they appear in
`present_beyond_first_gap` on a v079 database. That is expected; read them
with their neighbours. Verified on a scratch PostgreSQL 16 cluster on
2026-10-30: the script runs with `ON_ERROR_STOP`, returns 71 signature rows
and the summary, and leaves no writes.

Save the output next to the run date under
`docs/operations/` as ALEMBIC_RECONCILE_(date).txt. It contains no
customer rows.

## 3. Read the result

Expected pattern on 2026-10-30, from the evidence in the decision record:

| Observation | Meaning |
|---|---|
| `recorded_version = 267d8053ced5` | Row is at v079. |
| `supported_through_revision` is v079 or shortly after | The chain was not run past v079. Most v080 to v127 effects are absent. |
| `present_beyond_first_gap` lists v128, v131, v134, v135, v136, v137 | Those revisions were hand-applied (decision record, Appendix A). |

Three outcomes:

**A. The expected pattern.** Do not change the row. v079 is the truthful
chain position. Go to §4.

**B. Every observable revision through some revision X is `true`, and
nothing is `true` beyond X.** The chain was run to X and the row was not
updated (for example a crashed `run-migrations.sh` after the last
revision committed). Go to §5 with X.

**C. Anything else** (gaps in the middle, `false` on a revision whose
later neighbours are `true` without a HAND-APPLIED note). Stop. Record the
output and raise it in the PR or with the engine that prepared the
migration. Do not edit the row.

## 4. Outcome A: run the chain, do not stamp

Reconciling the row means executing the pending revisions through the
supported runner, not editing the row. The procedure is already written:

1. `docs/operations/DATABASE_ROLE_CUTOVER.md` sections 1 to 4: roles,
   ownership, extension ownership, memberships.
2. `docs/operations/MIGRATION_V079_TO_V120_2026_09_05.md` "Controlled
   execution sequence": steps 1 to 8, with the target now
   `a3f7ce361b0e` (v137) instead of `c6a120b4e901`.
3. Before step 4 of that sequence, resolve decisions B1 to B7 in the
   decision record. The hand-applied changes without an Alembic
   counterpart must be back-ported first, or the chain's last word on
   `tenant_isolation_tasks` and `data_gap_events` will differ from
   production.
4. On the staging restore, confirm the hand-applied revisions pass over
   their already-present effects. Expected: v128, v131, v134 to v137 complete
   with no error because each `upgrade()` is guarded (decision record,
   "Hand-applied revisions and their idempotency"). If any raises
   "already exists", repair that revision's guard in a PR before touching
   production.
5. After the production run, `alembic current` must print `a3f7ce361b0e`,
   and a second run of `scripts/run-migrations.sh` must be a no-op.

## 5. Outcome B: set the row to X

Only when §3 outcome B holds. One transaction, one statement, then the
precheck again.

```sql
BEGIN;
SET LOCAL statement_timeout = '5s';
UPDATE public.alembic_version SET version_num = '<X>' WHERE version_num = '267d8053ced5';
-- Expect: UPDATE 1. If 0, another session changed the row; ROLLBACK and re-run §2.
COMMIT;
```

Then:

```bash
psql -X -v ON_ERROR_STOP=1 -f sql/prod-apply/PRECHECK_alembic_version_reconcile.sql
```

`recorded_version` must equal `supported_through_revision`. Record the
before and after outputs in `DEVOPS_NOTES.md` with the date.

## 6. What never to do

- `alembic stamp head`, or any `UPDATE` of the row to a revision whose
  effects the precheck shows absent.
- `alembic upgrade head` against production before
  `DATABASE_ROLE_CUTOVER.md` is complete and the staging rehearsal in
  §4 step 4 has passed.
- Applying another file from `supabase/migrations/` or `sql/prod-apply/`
  without a paired Alembic revision (decision record, rule 4).
- Running the precheck with a role that can write. It cannot write by
  construction, but the habit matters.

## 7. Keeping the precheck current

The signature table inside the precheck names one object per revision.
When a revision is added to `alembic/versions/`, add one line to the
`VALUES` list in `sql/prod-apply/PRECHECK_alembic_version_reconcile.sql`
in the same PR. scripts/check_schema_channels.py (WI-01 requirement 5)
is the intended guard for that; until it exists, the PR template's
documentation checkbox covers it.
