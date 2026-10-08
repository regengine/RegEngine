# FIX-REPORT for PR #3232 (merge 154e45172f6f67c8980c2cb9b90ab4766f84f391)

Scope: CONCERN and BLOCKER findings touching the SSRF-safe fetching change.
Out of scope per the task order (noted, not fixed): the suspended-tenant
deny on live auth, the tenant-scope gate failure, and the 7 xfail
cross-tenant leaks. No critical findings were reported for #3232.

## Findings table

| # | Source report | Severity | Finding in one line | Status |
|---|---|---|---|---|
| 1 | re-rv-3232-correct, lead-correct | High | Relative RSS item links dropped (no feedparser base URL) | FIXED AND TESTED |
| 2 | re-rv-3232-correct, lead-correct, lead-blast | Medium | 5 MiB cap on FDA PDFs and discovery docs, silent HTML fallback | FIXED AND TESTED |
| 3 | re-rv-3232-security, re-rv-3232-correct (low), lead-security | High | Compressed bodies expand before the size cap runs | FIXED AND TESTED |
| 4 | re-rv-3232-security | Medium | Playwright fallback sidesteps cap and redirect checks | FIXED AND TESTED (decode and size slice; see boundary note) |
| 5 | re-rv-3232-tenant, lead-tenant, lead-blast | Medium | Robots 401/403 pushes approvals into manual_upload_queue:system | FIXED AND TESTED |
| 6 | re-rv-3232-tests, lead-tests | Medium | Async redirect tests stub the validator, no live async SSRF test | FIXED AND TESTED |
| 7 | re-rv-lead-blast (3232b) | Medium | FoodReady, FoodDocs, Tive swallow refusals as empty sync | FIXED AND TESTED |
| 8 | re-rv-lead-blast (3232c) | Medium | Private base_url fails late at sync instead of at configure | FIXED AND TESTED |
| 9 | re-rv-lead-blast (3232a) | Medium | ResponseTooLargeError handled as generic ValueError at doc sites | FIXED AND TESTED |
| 10 | re-rv-int-backend-suite | High | tests/test_discovery_hardening.py 2 deterministic failures | FIXED AND TESTED |
| 11 | re-rv-3232-tests (low) | Low | FoodDocs and Tive lack unmocked 127.0.0.1 tests | FIXED AND TESTED |
| 12 | re-rv-3232-security (low) | Low | SSRF refusal text echoes the resolved private IP | FIXED AND TESTED |
| 13 | re-rv-lead-blast (low) | Low | SafetyCulture GETs carry Content-Type, an extra redirect refusal | FIXED AND TESTED |
| 14 | re-rv-3232-security (low) | Low | follow_redirects_safely has no cap or header policy | FIXED AND TESTED (doc fix; no callers) |
| 15 | re-rv-3232-correct (low) | Low | nydfs.py, fda.py, ecfr adapters still use plain clients | Not fixed, listed below |
| 16 | re-rv-3232-ops (low), lead-ops | Low | 5 MiB cap has no env override | Not fixed, listed below |

## What each fix does

1. `generic.py` passes `response_headers={"content-location": <final URL>}`
   to feedparser. The safe helpers record the logical final-hop URL at
   `response.extensions["safe_final_url"]` (the transport rewrites
   `request.url` to the pinned IP, so `resp.url` is unusable as a base).
2. New `DOCUMENT_MAX_RESPONSE_BYTES` (20 MiB) used by the FDA warning
   letter PDF deep fetch and the Google discovery document fetch.
   Oversized PDFs log `fda_deep_fetch_pdf_too_large` /
   `google_fetch_too_large` instead of the generic failure, and discovery
   scrape returns a distinct `Response exceeds size cap` error.
3. Capped readers use an adaptive chunk size
   (`min(64 KiB, max_bytes + 1)`), so one gzip or brotli read cannot
   allocate past the cap, while small budgets still trip immediately.
   Non-integer Content-Length stays lenient (see notes).
4. `fetch_content` no longer promotes `httpx.DecodingError` to the
   Playwright fallback (size and SSRF refusals were already fatal).
   Boundary: timeouts, connect errors, and HTTP errors still fall back,
   since that retry is the feature and the initial URL was validated.
5. `tenant_id` rides in the `discovery_scrape` payload (approve and bulk
   approve), the handler forwards it to `scrape`, and
   `run_all_regulations_ingest` accepts it (route passes the caller
   tenant, scheduler keeps `system`). Old payloads default to `system`.
6. Three live async tests with the real client and real validator:
   link-local redirect blocked, canary zero hits with the hop re-check
   isolated as the sole guard, and final-URL tagging.
7. `fetch_events` in FoodReady, FoodDocs, and Tive re-raise
   `ResponseTooLargeError` and `SSRFError`, so `sync` records errors
   instead of reporting an empty finished sync.
8. `configure_connector` rejects provably non-public literal base URLs
   with 400 (DNS-free check, so setup needs no live lookup; private
   hostnames are still refused per hop at fetch time).
9. Same code as 2, plus scheduler JSON scrapers intentionally keep the
   5 MiB default (measured payloads stay under it, failures there are
   already visible as `success=False`).
10. The two hardening tests now mock `safe_httpx_get_sync` (the seam the
    PR moved fetching to) instead of the removed `session.get`.
11. Unmocked `http://127.0.0.1:9` tests for FoodDocs and Tive fetch, plus
    Tive connection refusal.
12. Discovery SSRF refusal returns a fixed string; the resolved address
    stays in server logs only.
13. `Content-Type` dropped from SafetyCulture GET headers (no request
    body, one fewer redirect refusal cause).
14. Module and client docstrings now point new callers at the capped
    `safe_httpx_get_async`, not the legacy helper. No production caller
    exists, so no behavior changed.

## Test commands and results (all through ~/metacode/fleet/heavy)

- `.venv/bin/pytest tests/test_discovery_hardening.py services/ingestion/tests/security/test_ssrf_redirect.py services/ingestion/tests/security/test_fetcher_ssrf_size_cap.py services/ingestion/tests/security/test_fetch_fallback.py -p no:cacheprovider` => `28 passed in 6.88s`
- `.venv/bin/pytest services/shared/tests/test_connector_safe_http.py services/shared/tests/test_safe_http_streaming_cap.py services/shared/tests/test_safe_http_redirect_headers.py services/shared/tests/test_safe_http_size_cap.py -p no:cacheprovider` => `51 passed in 1.33s`
- `.venv/bin/pytest services/ingestion/tests/test_task_handlers_discovery_1342.py services/ingestion/tests/test_routes_discovery_tenant_key_2921.py services/ingestion/tests/test_fda_enforcement_scraper_1342.py services/ingestion/tests/test_integration_router_1342.py -p no:cacheprovider` => `81 passed in 3.31s`
- `.venv/bin/pytest services/ingestion/tests/test_google_discovery_scraper_1342.py services/ingestion/tests/security/test_scrapers_ssrf.py services/ingestion/tests/security/ -p no:cacheprovider` => `58 passed in 6.86s`
- `.venv/bin/pytest services/ingestion/tests/test_google_discovery_scraper_1342.py -p no:cacheprovider` (after budget tests) => `23 passed in 0.44s`
- `.venv/bin/pytest services/scheduler/tests/test_fsma_nightly_sync_wired.py services/scheduler/tests/test_silent_failures_2697.py services/ingestion/tests/test_pipeline_1342.py tests/test_discovery_hardening.py -p no:cacheprovider` => `42 passed in 1.35s`
- `.venv/bin/pytest services/shared/tests -p no:cacheprovider` => `1 failed, 1179 passed, 28 skipped in 9.61s`. The single failure is `test_extract_document_script.py::test_verbose_sends_wrapper_log_lines_to_stderr_only`, which passes in isolation (`19 passed`) and passes together with every file I touched (`70 passed`). It is order dependent, lives in an area I did not touch (document extract logging), and matches the integration report pattern of order dependent failures on main. Left as is.
- `ruff check` on all 23 touched files => `All checks passed!`. `ruff format --check` on production files => clean.
- `scripts/security/scan_tenant_scope.py` was not run: I touched no SQL or Cypher queries (only payload dicts, Redis keys, and HTTP plumbing).

## How new tests were confirmed to fail without the fix

- Relative RSS links: direct feedparser probe in the repo venv. Parsing
  the same bytes without `response_headers` leaves `notice.html` and
  `/regs/item/2` unresolved; with `content-location` both resolve
  absolute. Old code takes the first path, so both new tests fail there.
- Async canary twin: with `current_url = validator(next_url)` temporarily
  edited out by hand, the test fails (`Failed` at the `pytest.raises`
  line, canary hit once). Restored after, suite green again. The
  link-local twin keeps passing via the pin layer, which documents the
  defense in depth.
- Streaming cap: the first fixed 64 KiB chunk version failed 4 existing
  streaming tests (over-buffering, exact consumption counts), which forced
  the adaptive sizing. Final code passes all existing assertions
  unmodified.
- Discovery hardening: the integration suite on main documents both
  failures (`AttributeError: NoneType has no attribute args`), caused by
  mocking the removed `session.get` seam.
- Connector propagation, FDA oversized log, Google oversized log,
  configure 400s, handler tenant forwarding, payload tenant assertion,
  PDF document budget, and the DecodingError fallback test each assert
  behavior the old code cannot produce (old code returns `([], None)`,
  logs the generic event, stores the base, drops the tenant, omits
  `max_bytes`, or promotes to the browser mock), verified by reading both
  sides. Existing assertions that pinned the old swallowing behavior were
  updated to the audit required propagation contract.

## Lows listed without fixing

- `nydfs.py` (single `validate_url`, then `requests.get` with unvalidated
  redirects and no size cap) and `fda.py`, ecfr, federal_register, fsma
  adapters (plain `httpx.Client`, hardcoded hosts). Routing them through
  the safe helpers is its own task with retry and session implications.
- No env override for the 5 MiB default. Per-caller document budgets now
  cover the known large-document paths.
- Non-integer `Content-Length` stays lenient: httpx joins repeated
  headers with commas, so a hard error would refuse legitimate
  responses. The streaming cap still bounds the body either way.

## Notes for Christopher (decisions needed)

1. On-prem connector bases: configure now rejects private literals with
   400. If any tenant needs a VPC or on-prem vendor endpoint, that needs
   an explicit allowlist decision first.
2. Browser fallback stays default-on for transient failures. Dropping the
   default until the browser path gets hop validation and a byte cap is a
   product call.
3. Scheduler FDA scrapers keep the 5 MiB default for JSON and index
   pages. If a real payload exceeds it, that caller needs its own
   `max_bytes`, same pattern as the PDF fix.
4. One pre-existing lint warning (`I001` import sort in
   `test_routes_discovery_tenant_key_2921.py`) predates this change and
   was left alone.
