# services/ingestion/tests

Test directory for the ingestion service. ~4,300 tests across ~165 files.

## CI gates that exercise this directory

1. **`Test ingestion`** (matrix job in `backend-ci.yml`) — runs the full
   suite single-process with coverage. Drives the `--cov-fail-under` floor.
2. **`Ingestion full suite (xdist signal)`** (single job in `backend-ci.yml`)
   — runs the suite under `pytest-xdist --dist=loadfile -n auto` so each
   test file gets a dedicated worker process. This is the gate that
   catches genuine cross-file failures without the cascade noise.
3. **`Test Suite Health Check / Full suite collects without errors`**
   (`test-suite-check.yml`) — fast collect-only sanity check.

The xdist gate is the only one with an allowlist. The matrix and
collect-only gates run against the whole directory.

## The allowlist

Configured in [`suite-runs.toml`](./suite-runs.toml). Read at CI time by
[`scripts/render_ingestion_ignores.py`](../../../scripts/render_ingestion_ignores.py),
which emits `--ignore=…` flags. Two buckets:

### Bucket 1 — module-level `sys.modules` poisoners (6 files)

These rewrite `sys.modules[...]` at import time with no teardown:

| File | Modules rewritten |
|------|-------------------|
| `test_sandbox_router_1342.py` | `shared.database` |
| `test_routes_health_metrics_1342.py` | `shared.kafka_consumer_base`, `app.config` |
| `test_task_handlers_scraping_1342.py` | `app.scraper_job`, `app.routes_scraping` |
| `test_task_handlers_sources_1342.py` | `regengine_ingestion`, `regengine_ingestion.sources`, `app.routes` |
| `test_task_handlers_discovery_1342.py` | `app.discovery` |
| `test_task_handlers_regulation_1342.py` | `app.regulation_loader` |

They pass solo (verified — and they're still exercised by the matrix
`Test ingestion` job, which runs single-process). With `--dist=loadfile`
each file already gets its own worker, so the cascade doesn't actually
form at runtime; quarantining them is belt-and-suspenders until the
rewrite ships.

The right fix is **Option A** (deferred): rewrite each file to use
fixtures + `monkeypatch.setitem(sys.modules, …)` so teardown undoes the
stub. Tracked in `project_test_suite_isolation_2026_04_19.md`.

### Bucket 2 — pre-existing real failures (0 files)

All three files in this bucket were fixed by repointing their mock
targets to the post–PR #2200 module layout (`app.routes_ingest`):

- `test_boundaries.py` already imports `app.routes_ingest` via its
  `routes` fixture — passes solo and in CI.
- `test_routes_regulation_task_queue.py` — patches updated from
  `app.routes.{SessionLocal,enqueue_task,redis,uuid,get_staging_path,
  consume_tenant_rate_limit}` to `app.routes_ingest.*`, and the router
  import was repointed to `app.routes_ingest.router` (where
  `/v1/ingest/regulation` actually lives now).
- `test_smoke_ingestion.py` — the stale `app.routes.AdminClient` patch
  was removed; `/health` lives in `routes_health_metrics.py` and only
  hits Kafka when `KAFKA_BOOTSTRAP_SERVERS` is configured to a
  non-default value, so the test now just unsets that env var.

When updating mock targets after a refactor, follow the new module
layout — don't paper over with allowlist entries unless the underlying
test is genuinely no longer meaningful.

## Adding a file back to the gate

1. Run the candidate file under the same flags CI uses:

   ```bash
   pytest services/ingestion/tests/<your file>.py --no-cov -q
   ```

2. Run the whole suite under `--dist=loadfile` with the candidate
   removed from the allowlist:

   ```bash
   # temporarily delete the line from suite-runs.toml, then:
   pytest services/ingestion/tests \
     --dist=loadfile -n auto --no-cov \
     $(python3 scripts/render_ingestion_ignores.py)
   ```

3. If both pass, drop the line from `suite-runs.toml` for real and PR
   the change. If they don't, fix or quarantine — never expand the
   allowlist to drop tests until it goes green.
