# SEL-314 RLS policy dedupe — 2026-10-20

- Supabase advisors on 2026-10-20: 2 security WARNs (both `submit_assessment_lead` executable by anon/authenticated as SECURITY DEFINER — intended, see 2026-10-16 note; `search_path` is already pinned to `public, pg_temp`, inputs are length/format-checked, rate-limited 60/10min) and 46 `multiple_permissive_policies` WARNs on 12 tables. 274 `unused_index` INFOs were not touched.
- The 44 `public.*` warnings came from eleven out-of-band `authenticated`-only policies (`users_own_data`, `sessions_user_owns`, `tenant_isolation_policy` on `api_keys`/`review_items`, and `*_tenant_isolation` / `*_isolation` on `compliance_alerts`, `compliance_status_log`, `invites`, `memberships`, `roles`, `tenant_compliance_status`, `tenant_product_profile`). None exists in the Alembic chain. The tenant ones fall back to placeholder tenant `…0001`, which is not in `public.tenants` and has zero rows in any of the nine tables; `public.get_tenant_context()` raises when `app.tenant_id` is unset, so the remaining `TO PUBLIC` policies stay fail-closed. `frontend/` has no `.from()` call against any of these tables; its only Supabase data call is `.rpc('submit_assessment_lead')`.
- The 2 `fsma.tenant_portal_links` warnings: `portal_links_token_lookup` (SELECT, TO PUBLIC, v075) and `tenant_isolation_portal_links` (ALL, TO regengine/regengine_sysadmin; production still carries this v074 name — v090 renamed it `tenant_isolation_tenant_portal_links` on Alembic-built databases, and both names are dropped) both reach `regengine`. Replaced by `portal_links_select` plus `portal_links_insert/update/delete`. Predicates use the v096 `CASE` form (token arm, sysadmin arm, then `get_tenant_context()`), and a portal-token session (token set, tenant unset, as inside `fsma.get_active_portal_link_by_token`) now hides non-matching rows instead of raising on them; tenant sessions stay fail-hard. Same effective access otherwise.
- Verified on Postgres 16 with a fixture mirroring production (both policy names, `get_tenant_context()` raising): apply, six behavioral checks (tenant read, token read without tenant, no-context raise, cross-tenant insert refused, own-tenant insert, armed sysadmin), rollback restores the eight original policies byte-for-name, apply twice is a no-op; v134 `upgrade()`/`downgrade()` the same way via Alembic `Operations`.
- Files: `alembic/versions/20261020_1faec7148e78_v134_sel314_rls_policy_dedupe.py` (idempotent), `sql/prod-apply/apply_sel314_rls_dedupe.sql`, `sql/prod-apply/rollback_sel314_rls_dedupe.sql` (exact restore of the observed definitions). Not applied to production from the agent session (write to the Supabase project was declined); apply the plain SQL, then re-run the performance advisor and expect 0 `multiple_permissive_policies`.
- Observed while here: `public.alembic_version` on the Supabase project still reads `267d8053ced5` (v079) although v128 policies are present, so prod-apply SQL has been landing without a version bump. `alembic upgrade head` against this database would re-run v080–v133; do not run it until the version row is reconciled.

# FSMA RLS and assessment lead review — 2026-10-16

- Assessment leads: the Next.js server action calls `submit_assessment_lead` with a Supabase client initialized from the public anon key. The function's 24-hour dedupe reads and updates existing leads, so `SECURITY INVOKER` plus anon INSERT would break it or expose lead reads/updates. Keep `SECURITY DEFINER` and anon EXECUTE. The existing auxiliary-Supabase runbook revokes EXECUTE from PUBLIC and grants it to anon/authenticated; that project's current function privileges were not verified. The Alembic chain targets a different database, so this migration does not change the lead function.
- FSMA: v128 restores tenant-GUC policies for the 18 listed tables with `regengine` runtime grants, limited to their v111 operations. Only `ingestion_runs` also permits tenant-scoped `regengine_sysadmin` SELECT. Four tables (`cte_kdes_backfill_log_v059`, `entity_merge_history`, `exception_attachments`, `key_data_elements`) have no runtime grant and receive no permissive app policy. Restrictive guards deny direct anon/authenticated access on all 22, including where older PUBLIC policies exist (the Alembic path skips the `ingestion_runs` guard where nothing reaches those roles; see the INC-2 note). The 20 tables with `tenant_id` use `public.get_tenant_context()`; seven TEXT columns compare with `::text`, and 13 UUID columns compare directly. The two tenant-less tables (`cte_kdes_backfill_log_v059` and `key_data_elements`) use only the `current_user` guard. No table grants or schema columns change.
- INC-2 follow-up: the Alembic migration creates the `ingestion_runs` guard only where a permissive policy reaches `anon` or `authenticated`, through PUBLIC or role inheritance. `ingestion_runs` is the one v128 table the boot canary fingerprints (`_RUNTIME_CUTOVER_CANARY_SQL`). A TO PUBLIC guard there changes both runtime fingerprints, and containers then refuse to boot. An Alembic-built database has no such policy, so v128 adds 21 guards there and the canary manifest stays byte-identical. The plain SQL in `sql/prod-apply/` is unchanged and still creates all 22. Each table's block also sets a 10s `lock_timeout`, as v126 does, so a long transaction from the still-serving container fails the deploy and rolls it back instead of stalling FSMA queries behind the lock.
- Production v128 first failed with PostgreSQL 42883 (`text = uuid`). A later dry run rolled back after PostgreSQL 42703 (`tenant_id` missing on `cte_kdes_backfill_log_v059`). Earlier offline checks missed the two tenant-less tables. This repair has not been applied to a database here.
- Risks: no database connection or live migration test was allowed, so live RLS force flags, role memberships, current grants, and deployment state remain unverified. Identity-resolution writes already exceed v111's read-only ACL and remain blocked. An anon caller who knows an email can still enrich that lead within 24 hours through the RPC. Downgrading v128 removes its policies and may restore prior client-role exposure.

## Plain SQL for production v128 repair

- Rendered `upgrade()` and `downgrade()` from `alembic/versions/20261016_a5e7c9b2d341_v128_fsma_rls_policy_repair.py` into `sql/prod-apply/apply_v128_fsma_rls.sql` and `sql/prod-apply/rollback_v128_fsma_rls.sql`. Both use one transaction and preserve the migration's 22-table order (reversed for rollback), conditional policy behavior, required-table/RLS failures, and optional quarantine-table skip. The APPLY adds `DROP POLICY IF EXISTS` inside each original creation branch; a same-named but nonmatching app policy still raises a duplicate-policy error. No grants or Alembic version write are included.
- `sql/prod-apply/PRECHECK_v128_fsma_rls.sql` contains only read-only SELECTs. It reports existence for the five role labels (including PostgreSQL's `PUBLIC` pseudo-role), two referenced functions including `public.get_tenant_context()`, 22 FSMA relations plus three catalog relations, and all 60 possible v128 policy names; it also reports RLS enabled status.
- Offline verification: 5 focused migration tests passed; Ruff check and format checks passed. The tests inspect all 22 Alembic and plain APPLY table blocks for the seven TEXT casts, 13 UUID comparisons, and `current_user`-only guards on the two tenant-less tables. No migration was applied or tested against a database here; current live policy definitions, function behavior/privileges, and execution after this edit remain unverified. Rolling back the guard policies may restore access allowed by historical policies.

## Columns referenced by v128 policy expressions

`tenant_id` is the only table column in these expressions, and only on the 20 tables below. The guards on `fsma.cte_kdes_backfill_log_v059` and `fsma.key_data_elements` reference no table column; production confirmed that neither has `tenant_id`. `current_user` is a PostgreSQL identity expression. Types below are from the production report; no catalog query was made for this repair.

| Column | Reported type |
| --- | --- |
| `fsma.canonical_entities.tenant_id` | UUID |
| `fsma.cte_events.tenant_id` | TEXT |
| `fsma.cte_kdes.tenant_id` | TEXT |
| `fsma.entity_aliases.tenant_id` | UUID |
| `fsma.exception_cases.tenant_id` | UUID |
| `fsma.exception_comments.tenant_id` | UUID |
| `fsma.exception_signoffs.tenant_id` | UUID |
| `fsma.fda_export_log.tenant_id` | TEXT |
| `fsma.hash_chain.tenant_id` | TEXT |
| `fsma.identity_review_queue.tenant_id` | UUID |
| `fsma.ingestion_runs.tenant_id` | TEXT |
| `fsma.request_cases.tenant_id` | UUID |
| `fsma.request_signoffs.tenant_id` | UUID |
| `fsma.response_packages.tenant_id` | UUID |
| `fsma.rule_evaluations.tenant_id` | UUID |
| `fsma.submission_log.tenant_id` | UUID |
| `fsma.tenant_suppliers.tenant_id` | TEXT |
| `fsma.traceability_events.tenant_id` | TEXT |
| `fsma.entity_merge_history.tenant_id` | UUID |
| `fsma.exception_attachments.tenant_id` | UUID |
