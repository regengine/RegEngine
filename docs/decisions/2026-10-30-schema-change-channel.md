# Schema change channel — Alembic is the only authority

**Decision date:** 2026-10-30
**Owner:** Christopher Sellers (solo technical founder)
**Status:** Proposed (WI-01 of `docs/plans/TECH_DEBT_REMEDIATION_PRD_2026-10-28.md`); becomes Active when Christopher merges it

## Decision

1. The Alembic chain under `alembic/versions/` is the only authoritative
   description of the production database schema. Its head is the schema
   the code expects.
2. `supabase/migrations/` is the Supabase CLI project history. It is frozen
   as of this decision. No new file is added there unless it is a render of
   an Alembic revision and carries the header in §Header.
3. `sql/prod-apply/` holds rendered outputs of Alembic revisions only: a
   `PRECHECK_`, `apply_` and `rollback_` triple per revision, each carrying
   the header in §Header. Nothing in that directory is hand-authored DDL.
4. Applying schema change to production by any path other than
   `scripts/run-migrations.sh` (which runs `alembic upgrade head`) is a
   break-glass action. Break-glass changes are allowed for security fixes
   only, and the same PR must add an idempotent Alembic revision whose
   `upgrade()` converges on the hand-applied state, so the chain stays true.
5. The production database is the Supabase project named in
   `docs/operations/MIGRATION_V079_TO_V120_2026_09_05.md`, and
   `docs/operations/DATABASE_ROLE_CUTOVER.md` is the blocking procedure for
   running the chain against it. Railway hosts the application container
   only. Documents that say the tenant database is Railway Postgres are
   stale (see §Consequences).
6. `public.alembic_version` is never edited by hand except through
   `docs/runbooks/ALEMBIC_VERSION_RECONCILE.md`, and that runbook permits an
   edit only when the catalog proves every observable effect through the
   target revision is present.

## Header

Every file under `supabase/migrations/` or `sql/prod-apply/` added after
this date starts with:

```sql
-- alembic-revision: <12-hex revision id>
-- rendered-from: alembic/versions/<file>.py (<upgrade|downgrade|precheck>)
```

A CI guard (`scripts/check_schema_channels.py`, run by the backend CI
"Alembic revision ID guard" job) fails a PR that adds or changes a file in those directories without
the header or with a revision id that does not exist.

## Context

Measured against the tree at `f87ed2a` on 2026-10-30.

- Alembic: 105 revision files, one head `a3f7ce361b0e` (v137). The
  revision DAG is clean (`scripts/check_alembic_revisions.py`).
- Production was last observed at `267d8053ced5` (v079), on 2026-09-05
  (`docs/operations/MIGRATION_V079_TO_V120_2026_09_05.md`) and again on
  2026-10-20 (`DEVOPS_NOTES.md`). 71 revisions sit between that row and
  head.
- The controlled execution of the chain has been "prepared for review;
  execution blocked" since 2026-09-05. Its prerequisites are role
  provisioning, object-ownership reconciliation and a verified backup, all
  in `docs/operations/DATABASE_ROLE_CUTOVER.md`. None is recorded as done.
- Meanwhile schema changes kept reaching production by two other channels:
  45 files in `supabase/migrations/` (17 from March–April 2026, 28 from
  July–October 2026) and 12 files in `sql/prod-apply/`. Ten of the 45 render
  an Alembic revision; 35 have no Alembic counterpart (Appendix A).
- `docs/MIGRATION_CONSOLIDATION.md` described a state from March 2026 (10
  Alembic revisions, a `migrations/` directory that no longer exists). It
  now points here.
- Two documents disagree on the database's identity:
  `docs/CODEBASE_MAP.md` §1 says Supabase; `frontend/COPY_REMEDIATION_PLAN.md`
  (2026-08-02) says Railway Postgres. The operations documents and the
  observed `alembic_version` row settle it: Supabase.

Why this matters: the product promise is tamper-evident evidence, and the
schema that holds it has three write paths and a version row 71 revisions
behind the applied state. `scripts/run-migrations.sh` runs
`alembic upgrade head` whenever the version table is populated, so a deploy
whose `MIGRATIONS_DATABASE_URL` points at production would replay v080 to
v137. The 2026-09-05 rehearsal proved the chain from v079 on a synthetic
restore, but production has since received hand-applied changes that the
rehearsal did not have (Appendix A, "no counterpart").

## Consequences

- No more hand-applied SQL without a paired Alembic revision (rule 4).
  The eleven hand-applied changes since 2026-10-16 that have no counterpart
  (Appendix A) need back-porting decisions before the chain runs; otherwise
  `alembic upgrade head` will either fail on an object that exists or
  silently diverge from what production has.
- The reconcile runbook, not a stamp, resolves the version row. Stamping
  `head` would record 60 revisions whose effects the catalog cannot show.
- `frontend/COPY_REMEDIATION_PLAN.md` row "Tenant DB" is corrected in WI-07.
- `docs/engineering/SCHEMA_CHANGE_POLICY.md` §3.1 still describes Flyway
  style `V{N}__description.sql` files and a `schema_migrations` table. That
  policy predates Alembic ownership and is updated in WI-07 to name Alembic.

## Alternatives considered

- **Stamp production to head and forward-port the hand-applied changes.**
  Rejected: the catalog shows most v080–v127 effects absent (passwordless
  auth tables, receipts, dead-letter, evidence snapshots). Stamping would
  lie about them and the application would fail on first use.
- **Make `supabase/migrations/` the authority and retire Alembic.** Rejected:
  it has no revision graph, no downgrade path, and CI's migration tests,
  parity audit and seeded rehearsals are all Alembic-based.
- **Keep three channels and document them.** Rejected: that is the current
  state, and it produced a version row that cannot be trusted.

Second opinion: TypeSafe Jev, given the catalog pattern above, chose "run
the chain, leave the row" at 0.89 confidence, called stamping to head unsafe
at p=0.95, and rated replay without back-porting the hand-applied changes a
high risk (2.22 of 3, low confidence 0.23). Request
`req_01a18b886d7f76d6b797d4ea7f5065ca`, 2026-10-30.

## Appendix A — Channel inventory (2026-10-30)

Counterpart = the Alembic revision whose `upgrade()` produces the same
objects. "Partial" means some of the file's statements have a counterpart.
"Auxiliary" means the objects exist only for Supabase-side features
(anonymous lead capture, developer portal RPCs, Supabase roles) and the
decision in Appendix B applies.

### `supabase/migrations/`

| File | Counterpart | Disposition |
|---|---|---|
| `20260314053557_create_waitlist_leads.sql` | none | Auxiliary. Decision B1. |
| `20260314073855_create_developer_portal_tables.sql` | v058 (`20260415_v058_docs_and_data.py`) | Rendered history. |
| `20260314074042_create_increment_invite_usage_rpc.sql` | none | Auxiliary. Decision B1. |
| `20260314093510_create_assessment_submissions.sql` | v058 | Rendered history. |
| `20260317074952_create_fsma_organizations.sql` | baseline (`20260324_97588ba8edf3_baseline_consolidate_v002_through_v042.py`) | Rendered history. |
| `20260319014551_create_search_queries_table.sql` | none | Auxiliary. Decision B1. |
| `20260320220954_extend_organizations_schema.sql` | baseline / v084 | Rendered history. |
| `20260321014327_seed_fsma_204_obligations.sql` | seeds in code (`services/shared/rules/seeds.py`, v116/v119) | Superseded by code-owned seeds. |
| `20260321014418_seed_obligation_cte_rules.sql` | same | Superseded. |
| `20260330002451_enable_rls_missing_tables.sql` | v051 / v056 | Rendered history. |
| `20260330031620_developer_portal_schema_doc.sql` | none (COMMENT ON only) | No schema effect. Freeze. |
| `20260403234813_create_traceability_events_and_ingestion_runs.sql` | v043–v047 (`20260325_compliance_control_plane_v043_v047.py`) | Rendered history. |
| `20260403235145_drop_hash_chain_fk_to_cte_events.sql` | v090 (`4c5d6e7f8a9b`) | Rendered history. |
| `20260403235708_create_rules_engine_tables.sql` | v043–v047 | Rendered history. |
| `20260404000051_fix_cte_events_idempotency_constraint.sql` | v072 (`71e79e111c5d`) | Rendered history. |
| `20260404011602_create_transformation_links_adjacency.sql` | v057 / v068 | Rendered history. |
| `20260413044744_add_last_login_at_to_users.sql` | none found | Decision B2: confirm whether `public.users.last_login_at` is in the ORM; if yes, add an idempotent revision. |
| `20260729012459_v092_lockdown_rls_and_revokes_only.sql` | v092 (`b3c8e1f4a627`) | Rendered history. |
| `20260730025741_lockdown_anon_lead_capture_and_definer_rpcs.sql` | none | Auxiliary. Decision B1. |
| `20260730025751_revoke_pgaudit_event_trigger_fn_execute.sql` | none | Auxiliary (provider extension). Decision B1. |
| `20260730033519_drop_transitional_anon_insert_on_assessment_submissions.sql` | none | Auxiliary. Decision B1. |
| `20261001054030_security_fsma_rls_and_function_search_path_20260930.sql` | partial: v111 (`b71d9e4c2a60`), v128 | Decision B3: diff against v111/v128 and back-port the remainder. |
| `20261016072839_search_path_extensions.sql` | none | Decision B4 (advisor batch). |
| `20261016073047_a_move_extensions_to_extensions_schema.sql` | none | Decision B4. Conflicts with the v111 extension-ownership note in `MIGRATION_V079_TO_V120_2026_09_05.md`. |
| `20261016073057_b_drop_duplicate_indexes.sql` | none | Decision B4. Drops `fsma.ux_cte_events_tenant_idempotency_key`, which v072 creates; the chain will recreate it unless back-ported. |
| `20261016073107_c_rls_initplan_select_wrap.sql` | none | Decision B4. Rewrites 73 policy expressions that v128/v134 later replace; order matters. |
| `20261016073122_d_index_unindexed_foreign_keys.sql` | none | Decision B4. |
| `20261016234347_v128_fsma_rls_policy_repair.sql` | v128 (`a5e7c9b2d341`) | Render. Header added 2026-10-30. |
| `20261016234352_v128_consolidate_permissive_policies.sql` | v128 (`93eb33f262a1`) | Render. Header added 2026-10-30. |
| `20261017021229_e_wrap_get_tenant_context.sql` | none | Decision B4. 86 policies rewritten; v134 assumes the v096 `CASE` form. |
| `20261017021244_f_tenant_id_indexes.sql` | partial: v055 | Decision B4. |
| `20261020072328_assessment_lead_abuse_guard.sql` | none | Auxiliary. Decision B1. |
| `20261020085506_sel314_ftl_read_only_drop_sysadmin_overlap.sql` | v134 (`1faec7148e78`) | Render. Header added 2026-10-30. |
| `20261020094817_sel314_drop_fallback_tenant_policies.sql` | v134 | Render. Header added 2026-10-30. |
| `20261022101703_lock_down_submit_assessment_lead.sql` | none | Auxiliary. Decision B1. |
| `20261022103548_enable_rls_internal_tables.sql` | partial: v056 / v111 | Decision B3. |
| `20261023050348_sel401_notify_new_lead_secret.sql` | none | Auxiliary. Decision B1. |
| `20261025033803_data_gap_time_to_fix.sql` | v135 (`41f96588d87c`) | Render. Header added 2026-10-30. |
| `20261025090000_supplier_agreed_sending_hours.sql` | v136 (`b005ddbf1dba`) | Render. Header added 2026-10-30. |
| `20261025090100_epcis_document_receipts.sql` | v137 (`a3f7ce361b0e`) | Render. Header added 2026-10-30. |
| `20261025100000_fix_obligation_1455_regulation_refs.sql` | none | Decision B5: data correction; needs a data revision or a seed update. |
| `20261025100100_waitlist_leads_drop_authenticated_read.sql` | none | Auxiliary. Decision B1. |
| `20261025100200_task_queue_fail_closed_tenant_policy.sql` | none; **conflicts** with v090 `a128f7f95db8` and v096 `c3a51e2f7b90`, which define `tenant_isolation_tasks` differently | Decision B6: back-port as v138 so the chain's last word matches production. |
| `20261025100300_data_gap_close_receipt_not_null.sql` | none; post-v135 fix | Decision B6: back-port as a revision after v135. |
| `20261026132000_sel399_rls_split_api_keys_sessions_users.sql` | none; file says "PREP ONLY. Do not apply without C.Lee's yes" | Decision B7: record whether it was applied; if yes, back-port; if no, move to a `proposed/` subdirectory. |

### `sql/prod-apply/`

| File | Counterpart | Disposition |
|---|---|---|
| `PRECHECK_v128_fsma_rls.sql`, `apply_v128_fsma_rls.sql`, `rollback_v128_fsma_rls.sql` | v128 (`a5e7c9b2d341`) | Render. Header added 2026-10-30. |
| `PRECHECK_v128_policy_merges.sql`, `apply_v128_policy_merges.sql`, `rollback_v128_policy_merges.sql` | v128 (`93eb33f262a1`) | Render. Header added 2026-10-30. |
| `PRECHECK_v131_tool_leads_utm.sql`, `apply_v131_tool_leads_utm.sql`, `rollback_v131_tool_leads_utm.sql` | v131 (`0a329588b824`) | Render. Header added 2026-10-30. |
| `apply_sel314_rls_dedupe.sql`, `rollback_sel314_rls_dedupe.sql` | v134 (`1faec7148e78`) | Render. Header added 2026-10-30. |
| `rollback_sel399_rls_split_api_keys_sessions_users.sql` | none (pairs with the Supabase file above) | Decision B7. |
| `PRECHECK_alembic_version_reconcile.sql` | all revisions after v079 | Read-only; owned by the reconcile runbook. |

### Hand-applied revisions and their idempotency

These revisions already have their effects on production. The chain must
pass over them without error. Counts are `IF NOT EXISTS` /
`DROP ... IF EXISTS` / `to_regclass` guards in each `upgrade()`:

| Revision | Guards | Verdict |
|---|---|---|
| v128 `a5e7c9b2d341` | 2 / 2 / 2, plus catalog fingerprint checks | Idempotent by design (its header says so). |
| v128 `93eb33f262a1` | 1 / 0 / 0 | Accepts "already merged" pairs per its docstring; verify on staging. |
| v131 `0a329588b824` | 1 / 0 / 0 | `ADD COLUMN IF NOT EXISTS`; idempotent. |
| v134 `1faec7148e78` | 0 / 2 / 3 | Documented idempotent. |
| v135 `41f96588d87c` | 5 / 6 / 0 | Documented idempotent. |
| v136 `b005ddbf1dba` | 2 / 1 / 0 | Documented idempotent. |
| v137 `a3f7ce361b0e` | 3 / 4 / 0 | Documented idempotent. |

## Appendix B — Decisions needed from Christopher

| # | Decision | Default if no answer |
|---|---|---|
| B1 | Are the Supabase auxiliary objects (`waitlist_leads`, `search_queries`, `increment_invite_usage`, `submit_assessment_lead`, `notify_new_lead`, anon/service_role policies) in scope for Alembic? | Out of scope. Record them in a docs/schema/supabase-auxiliary-objects.md list and leave `supabase/migrations/` as their only history. |
| B2 | Is `public.users.last_login_at` used by the ORM? | Check `services/admin/app/sqlalchemy_models.py`; if present, add an idempotent revision. |
| B3 | Back-port the parts of the 2026-09-30 and 2026-10-22 RLS files that v111/v128 do not cover? | Yes, as one revision, after a diff. |
| B4 | Back-port the six advisor-driven files (extensions move, duplicate indexes, initplan wrap, FK indexes, tenant_id indexes, get_tenant_context wrap)? | Yes for indexes; no for the policy rewrites, which v128/v134 supersede. Extension move needs the provider-ownership review in `DATABASE_ROLE_CUTOVER.md`. |
| B5 | Obligation 1455 citation fix: data revision or seed update? | Seed update in `services/shared/rules/seeds.py` plus a data revision that applies it. |
| B6 | Back-port `task_queue_fail_closed_tenant_policy` and `data_gap_close_receipt_not_null` as v138/v139? | Yes; both are small and idempotent. |
| B7 | Was SEL-399 applied to production? | Treat as not applied until the precheck shows `api_keys_backend` on `public.api_keys`. |
| B8 | Who runs the reconcile runbook and when? | Christopher, after B1–B7, on the staging restore the 2026-09-05 document requires. |
