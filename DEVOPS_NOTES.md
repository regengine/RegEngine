# Policy and index migration prep — 2026-10-16

- v128 merges four exact `FOR ALL TO PUBLIC` permissive policy pairs. Their effective `USING` and `WITH CHECK` predicates are identical. Other policy overlaps have different role scopes and remain unchanged; this does not resolve every advisor finding.
- v129 stages 155 index drops from the 265-entry catalog. It excludes 99 FK-leading indexes and 11 more with code-name references; none of the eligible indexes appears in migrations from the last 30 days. Downgrade recreates each index from the catalog definition.
- **Do not apply v129** until `idx_scan=0` is re-verified for at least 14 days. `pg_stat_database.stats_reset` was NULL in the export, so the current observation window is unknown. Merging and deploying this Alembic chain would run the migration automatically.
- No database was contacted. Catalog drift, real workload usage, and lock or rebuild cost remain unverified; dropping an index can slow queries even when its recorded scan count is zero.

## v128 plain SQL handoff

- C. Lee approved rendering only v128 (`93eb33f262a1`) as `sql/prod-apply/apply_v128_policy_merges.sql` and `rollback_v128_policy_merges.sql`. The matching `PRECHECK_v128_policy_merges.sql` lists the referenced schemas, pseudo-role, functions, catalog view, tables, and policies with existence results.
- APPLY validates the four original policy pairs before replacing each with the retained policy and v128's duplicated `OR` predicate. ROLLBACK restores the pairs in reverse order, including the removed policies' implicit `WITH CHECK` behavior. Both files use one transaction, guard absent tables, and support reruns.
- These plain SQL files contain no index changes and do not update `alembic_version`. Production's Alembic version is stale relative to this chain, per the task brief. No database was contacted; production catalog state and execution remain unverified.
- Local static verification captured v128's 20 upgrade and 12 downgrade statements and matched the four policy pairs, generated DDL, and reverse rollback order. A TruffleHog filesystem scan of the three SQL files found no secrets. PostgreSQL execution remains unverified by request.
