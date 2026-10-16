# Policy and index migration prep — 2026-10-16

- v128 merges four exact `FOR ALL TO PUBLIC` permissive policy pairs. Their effective `USING` and `WITH CHECK` predicates are identical. Other policy overlaps have different role scopes and remain unchanged; this does not resolve every advisor finding.
- v129 stages 155 index drops from the 265-entry catalog. It excludes 99 FK-leading indexes and 11 more with code-name references; none of the eligible indexes appears in migrations from the last 30 days. Downgrade recreates each index from the catalog definition.
- **Do not apply v129** until `idx_scan=0` is re-verified for at least 14 days. `pg_stat_database.stats_reset` was NULL in the export, so the current observation window is unknown. Merging and deploying this Alembic chain would run the migration automatically.
- No database was contacted. Catalog drift, real workload usage, and lock or rebuild cost remain unverified; dropping an index can slow queries even when its recorded scan count is zero.
