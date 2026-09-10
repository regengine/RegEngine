# Disposable local operational acceptance — 2026-09-10

This is **local evidence, not staging or production acceptance**. No provider services, existing databases, deployments, credentials, or migrations were changed.

The service started from `3f1cdea048bf5f52cb822456f8422718460e2a11` with the uncommitted relational-query fix. `evidence.json` records hashes of the exercised relational query, canonical writer, idempotency middleware, and server entrypoint. This is not a claim that a later commit was serving. Concurrent admin CSV changes were outside this HTTP trial.

Runtime: Python 3.11.15 from `/tmp/regengine-dependency-ci-venv`, PostgreSQL 16.14 (Homebrew), Redis 8.6.3. Full Alembic upgrade reached `c6a120b4e901` as dedicated `regengine_migrator_local`. Migration/runtime/admin roles were all NOSUPERUSER, NOBYPASSRLS, NOCREATEROLE. The API ran with production router/environment configuration, real database API-key authentication, HMAC signatures, Redis, RLS enforcement, and `RULES_ENGINE_ENFORCE=cte_only`.

| Check | Result |
|---|---|
| Initial authenticated ingest; same-key replay; fresh-key datastore dedup | Passed; same persisted event ID |
| Changed-body same-key request | HTTP 409 |
| Cross-tenant header / invalid API key | HTTP 403 / 401 |
| Two tenants, runtime RLS reads | Other tenant rows invisible |
| Runtime cross-tenant ledger insert | Denied, SQLSTATE 42501 |
| Runtime ledger privileges | SELECT/INSERT allowed; UPDATE/DELETE denied |
| Unseeded maximum batch | 500 accepted, no rejection |
| Two tenant package exports | HTTP 200, `X-Chain-Integrity: VERIFIED`; standalone verifier exit 0 |
| Same-length CSV content tamper | Standalone verifier exit 1, SHA-256 mismatch |
| Stored canonical quantity tamper | Canonical verification rejected; mutation rolled back |
| Catalog-seeded maximum batch after fix | 500 accepted, 0 rejected, 1.549 seconds |
| Durable state after seeded batch | 1,001 legacy events, 1,001 canonical events, 1,001 ledger rows, 7,000 rule evaluations |
| Seeded final chain/export | Canonical valid; standalone package verifier exit 0 |

`checks.json` contains 18 passing checks. `negative-write-and-versions.json` records the additional RLS write denial. Timing is one local measurement, not a capacity estimate.

## Finding and proof boundary

A fresh migrated database contains only the initial-packing harvester-phone rule. Shipping events therefore had no applicable rules. The first unseeded trial proves ingest/ledger/export behavior, **not rule-evaluation persistence**. `durability.json` records those original counts (501/501/501/0 for tenant 0; 2/2/2/0 for tenant 1, including the simulator event).

For the separate rules trial, `seed_rule_definitions()` explicitly inserted the repository's 36 missing built-in rules into the disposable database. No production rule catalog was changed. Before the source fix, this trial returned HTTP 500 and persisted zero additional events or rule evaluations. PostgreSQL reported `could not determine data type of parameter $3` for the untyped `:exclude_id IS NULL` expression in `fetch_related_events`. `seeded-rules-before-fix.json` preserves the failed trial and unchanged counts. Casting that nullable parameter to UUID fixes psycopg3 parameter inference without changing the tenant or event predicates.

The live regression was red twice before the fix (NULL and non-NULL UUID) and green afterward. It forces `postgresql+psycopg` even when CI provides a plain `postgresql://` URL. The live regression and existing prefetch tests passed **19 tests**.

The independently run pinned Inflow simulator (`78050ae78c72a348a518b6d48bdeae7424d772da`, contract v2) posted one mock event and one signed live event with zero failures. `simulator-before-fix.json` preserves that original-candidate result. It was not rerun after the unrelated relational-query fix. The old fixture's two-row canonical chain and export verified; the rule-evaluation limitation above also applies to that simulator trial.

## Reproduce

Use an environment installed from the checked-in lock, plus native `initdb`, `pg_ctl`, and `redis-server` on `/opt/homebrew/bin`. The harness creates a new temporary cluster and dynamic loopback ports; it never loads inherited connection URLs. Synthetic auth material stays in a private 0600 `access.json` in a 0700 temporary directory.

From the repository root:

```bash
/tmp/regengine-dependency-ci-venv/bin/python docs/engineering/local-acceptance-2026-09-10/probe.py
```

The foreground process prints `READY_ACCESS_FILE=<temporary path>`. In a second terminal, use that path (do not print its contents):

```bash
acceptance_access=/tmp/regengine-operational-REPLACE/access.json
/tmp/regengine-dependency-ci-venv/bin/python docs/engineering/local-acceptance-2026-09-10/checks.py "$acceptance_access"
/tmp/regengine-dependency-ci-venv/bin/python docs/engineering/local-acceptance-2026-09-10/rules_checks.py "$acceptance_access"
```

The checks write new evidence into this directory. Run only once per fresh fixture to reproduce the stated counts. To exercise the live SQL regression, set `REGENGINE_MIGRATION_TEST_DB` from the protected access file's `runtime_url` in a child process, then run `tests/shared/test_rules_related_events_live.py` and `tests/shared/test_rules_engine_prefetch_related_1365.py` with pytest.

After checks, signal cleanup without reading auth data:

```bash
/tmp/regengine-dependency-ci-venv/bin/python -c 'import pathlib,sys; pathlib.Path(sys.argv[1]).parent.joinpath("stop").touch()' "$acceptance_access"
```

The harness stops its API, Redis, and PostgreSQL processes and removes its temporary directory. An automatic 30-minute lease also bounds the running fixture. Both executed clusters were cleaned; `evidence-before-fix.json` and `evidence.json` record cleanup. No active-path file, raw auth file, or raw server log is included. `secret-scan.json` confirms the final fixture API keys/HMAC secret were absent from artifacts and ZIP members.

Remaining acceptance: hosted CI with the new SQL fix; provider serving identity; production role/catalog readback; backups/recovery; partner-owned acceptance. Native PostgreSQL 16/Redis 8 does not establish behavior on every provider version.

## Evidence serialization and scanner scope

Archived source identifiers use canonical GitHub commit/blob URLs. All four runtime SHA-256 snapshots were independently compared with the committed file bytes at `988ae85d`; they match. This comparison does not change the original service-start provenance. SHA-256 values in structured event metadata and source snapshots use space-separated hexadecimal octets: removing spaces reconstructs the exact original digest. The ZIP artifacts and verifier outputs remain unchanged. Reproduction probes emit the original API field shapes; this archival representation is a lossless packaging transformation.

The only inline scanner exclusion is the boolean feature flag ENABLE_DB_API_KEYS in `probe.py`, which enables database API-key authentication. It contains no credential. No scanner configuration, historical scan, or secrets baseline was changed.
