# EPIC-B — Postgres RLS fail-open remediation — plan

**Meta-issue:** #1456
**Status when plan was written:** 7 open children, partial coverage from
a local branch not yet on origin.
**Author's recommendation:** ship in two PRs — one that pushes the
already-coded migration branch, one that covers the three remaining
items. Sign-off point between PRs.

---

## 1. Key finding before coding

A local-only branch exists:

```
fix/migrations-audit-long-tail-2026-04-17
```

Not pushed to origin. Not a PR. Not on main. It contains **5 new
alembic migrations + 3 fix commits + 1 regression test** that address
four of the seven EPIC-B children:

| Child | Addressed by | File |
|---|---|---|
| #1204 task_queue fail-open `OR '' = ''` | commit `a2948c7a` | `alembic/versions/20260417_v061_task_queue_rls_fail_closed.py` |
| #1281 FORCE RLS missing on 4 tables | commit `4611dacd` | `alembic/versions/20260417_v062_force_rls_fsma_tables.py` |
| #1287 nullable `tenant_id` on audit tables | commit `838f7d61` | `alembic/versions/20260417_v064_tenant_id_not_null_audit_tasks.py` |
| #1271 v051/v056 policy drift | commits `7edc75b3` + `9870fce2` | `alembic/versions/20260417_v063_restore_memberships_policy.py` + v056 restore |
| (bonus) #1227 / #1247 / #1257 / #1303 migration hygiene | mixed | various |

The migrations look sane on spot-read (idempotent `DO` blocks, sysadmin
branches match the v056 policy pattern, downgrades provided). They
deserve a CI run and a code review, not a rewrite.

**Recommendation:** merge the existing branch first as PR-1. Three
children remain after that, handled in PR-2.

---

## 2. Remaining scope after PR-1

| # | Issue | File | Fix shape |
|---|---|---|---|
| #1096 | `SECURITY DEFINER` functions without `SET search_path` | `alembic/versions/20260415_rls_hardening_v056.py:94` and `alembic/versions/20260417_rls_fail_closed_hardening_v059.py:413` | `CREATE OR REPLACE FUNCTION ... SET search_path = pg_catalog, fsma`. One new migration, two functions. |
| #1217 | `fsma.transformation_links` has RLS enabled+forced but no policies (empty fortress) | `alembic/versions/20260415_schema_additions_v057.py:65-66` | Add `CREATE POLICY tenant_isolation_transformation_links` in a new migration using the v056 policy template. |
| #1265 | `canonical_persistence.persist_event` never calls `set_tenant_context` | `services/shared/canonical_persistence/writer.py:138, 289` | Application-code fix. Call `self.set_tenant_context(tenant_id)` at the top of `persist_event` and `persist_events_batch`. Unit test asserts `current_setting('app.tenant_id')` is populated before any SQL. |

No migrations touch the same tables. PR-2 is additive: one new alembic
migration (`v066_security_definer_search_path.py`) + one
(`v067_transformation_links_policies.py`) + one application-code patch
to `writer.py` with a test.

---

## 3. Recommended PR-1 execution

**Scope:** push `fix/migrations-audit-long-tail-2026-04-17` as-is, open
a PR, let CI run, merge.

**Steps:**

1. `git push origin fix/migrations-audit-long-tail-2026-04-17`
2. `gh pr create --title "fix(migrations): RLS fail-open + policy drift
   long-tail — #1204 #1271 #1281 #1287 #1227 #1247 #1257 #1303"`
   referencing the 8 issues it closes.
3. Watch CI. Expect:
   - alembic `upgrade head` on fresh DB green (this is the #1187 suite
     the branch specifically guards).
   - No test failures in `tests/migrations/`.
4. Review + squash-merge.

**Rollback plan:** every migration provides a `downgrade()` that
restores the previous fail-open state. We would not run downgrade in
production — we would roll forward with a follow-up migration that
re-tightens. This is documented in each migration's docstring.

**What PR-1 does NOT do:** it does not touch application code. It does
not change RLS policy shape outside the specific fail-open patterns it
fixes. It keeps the v056 policy template as the single canonical shape.

---

## 4. Recommended PR-2 execution

**Scope:** three additive fixes. All smaller than PR-1.

### 4a. #1096 — `SET search_path` on SECURITY DEFINER functions

New migration `v066_security_definer_search_path.py`:

```python
op.execute("""
    CREATE OR REPLACE FUNCTION audit.log_sysadmin_access()
    RETURNS TRIGGER AS $$
    BEGIN
        IF current_setting('regengine.is_sysadmin', true) = 'true'
           AND current_user = 'regengine_sysadmin' THEN
            INSERT INTO audit.sysadmin_access_log (table_name, operation, connection_info)
            VALUES (...);
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql SECURITY DEFINER
       SET search_path = pg_catalog, audit, fsma;
""")
```

Do the same for `get_tenant_context()`. Keep the function bodies
identical so behavior is unchanged — only the `SET search_path` clause
is added. Downgrade re-creates without the clause.

**Test:** existing RLS tests should pass unchanged. Add a regression
test that asserts every `SECURITY DEFINER` function in `pg_proc` has a
non-empty `proconfig` containing `search_path=...`.

### 4b. #1217 — transformation_links policies

New migration `v067_transformation_links_policies.py`:

```sql
CREATE POLICY tenant_isolation_transformation_links_select ON fsma.transformation_links
    FOR SELECT TO regengine, regengine_sysadmin
    USING (
        tenant_id = get_tenant_context()
        OR (current_setting('regengine.is_sysadmin', true) = 'true'
            AND current_user = 'regengine_sysadmin')
    );

CREATE POLICY tenant_isolation_transformation_links_insert ON fsma.transformation_links
    FOR INSERT TO regengine
    WITH CHECK (tenant_id = get_tenant_context());

-- repeat for UPDATE, DELETE following v056 template
```

**Test:** add `tests/migrations/test_transformation_links_rls.py` that:
- Inserts as tenant A, asserts tenant B cannot SELECT.
- Asserts sysadmin can read across tenants with the role + GUC set.
- Asserts INSERT rejected when `app.tenant_id` unset.

### 4c. #1265 — canonical_persistence writer context

`services/shared/canonical_persistence/writer.py`:

```python
def persist_event(self, event: TraceabilityEvent) -> CanonicalStoreResult:
    self.set_tenant_context(event.tenant_id)   # <-- new
    ...
```

Repeat for `persist_events_batch` (use the first event's tenant_id and
assert homogeneity, else raise).

Make `set_tenant_context` idempotent (it already is — it issues a
`SET LOCAL` which re-executes cheaply).

**Test:** `tests/shared/test_canonical_persistence_tenant_context.py`
mocks the DB session and asserts `SET LOCAL app.tenant_id` fires before
any INSERT. Uses a fake SQLAlchemy session with a statement log.

**Effort estimate:** PR-1 is 0.5-1 day (review + CI watch). PR-2 is
2-3 days.

---

## 5. CI gate to prevent regression

Add `tests/migrations/test_rls_coverage.py`:

```python
def test_every_fsma_table_has_tenant_id_not_null_and_force_rls(db):
    tables = db.execute("""
        SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON c.relnamespace = n.oid
        WHERE n.nspname = 'fsma' AND c.relkind = 'r'
    """).fetchall()
    for (t,) in tables:
        # tenant_id exists and NOT NULL
        col = db.execute(...).fetchone()
        assert col and col.is_not_null, f"{t}.tenant_id nullable"
        # FORCE RLS
        info = db.execute("SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE relname = :t", t=t).fetchone()
        assert info.relforcerowsecurity, f"{t} missing FORCE RLS"
```

Gate required on every PR that touches `alembic/versions/`. Kills the
regression vector where a new table ships with ENABLE but not FORCE.

Lands in PR-2.

---

## 6. Out of scope for this epic

- EPIC-A ("client-supplied tenant_id trust") — bundled elsewhere.
- Neo4j tenant scoping — handled by #1315 / EPIC-C.
- RLS policy syntax unification (Strategy A vs Strategy B across old
  migrations) — #1271 addresses the specific v051/v056 drift; broader
  stylistic cleanup can wait.

## 7. Decision needed

Before I start: **push the local branch as PR-1?**

If you're not sure, a safe low-cost move is to push the branch, let CI
run, and judge from the CI output + diff. You can close the PR without
merging if the migrations look wrong.
