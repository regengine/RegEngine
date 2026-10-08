# Break Report: ingestion authz, auditor_router, canonical_router

## Summary

Adversarial testing of the ingestion authorization surface, the auditor
read-only router, the canonical records router, and CSV template handling.
Local test setups only, no production contact. SafetyCulture webhook
signature paths were skipped as ordered.

Breaks found: 4. Fixed and tested: 4. Fixed but failing: 0. Blocked: 0.

1. CSV row-cap silently drops rows (Medium). Fixed, tested.
2. Auditor endpoints accept negative pagination, reaching SQL (Low). Fixed, tested.
3. Record history returns 200 for missing or foreign-tenant events (Low). Fixed, tested.
4. Downloaded CSV templates contain formula-leading example cells (Info). Fixed, tested.

Authz bypass attempts, IDOR probes on tenant artifacts, quantity and date
edge cases, malformed payloads, and tenant-mismatch handling were all
exercised. No bypass or cross-tenant data leak was found. Details below.

## Finding 1 (Medium): CSV row-cap silently drops rows

What broke: uploading a CSV with more than 500 data rows ingested the
first 500 and reported a single error, "Row 502: CSV exceeds maximum row
limit of 500", with no count of how many rows were discarded. A 505-row
file lost 4 rows the caller was never told about, and the ingestion
receipt counted 501 records against a 505-row file.

How to reproduce: call `parse_csv_rows` with 505 valid harvesting rows.
Before the fix: 500 events, 1 error, no skipped count. After the fix: 500
events plus an error stating "4 more row(s) after this one were skipped
and not ingested", followed by the unchanged cap message.

Root cause: `services/ingestion/app/csv_templates.py:764` (read loop
breaks after 501 records without consuming the rest of the reader) and
`:782` (cap error named no count).

Fix: after hitting the cap, the reader is drained with a counter (no
storage) and the skipped count is reported as its own parse error placed
before the existing cap message, which is kept byte-identical because an
existing test pins its exact text. A malformed tail degrades to the old
message rather than rejecting rows already read.

Test results: new `TestCsvOverflowReporting` in
`services/ingestion/tests/test_break_ingestion_authz.py` (3 tests) fails
on old code, passes on new. Existing suites
`test_csv_templates_1342.py`, `test_csv_jev_header_mapping.py`,
`test_csv_jev_file_cte.py`, `test_csv_ingestion_receipt.py`,
`test_csv_ingest_response_model_2892.py`, `test_csv_malformed_input.py`
all pass.

## Finding 2 (Low): auditor endpoints accept negative pagination

What broke: `GET /api/v1/audit/events` accepted `limit=-5` and
`offset=-1`, and `/api/v1/audit/exceptions` and `/api/v1/audit/export-log`
accepted negative `limit`. Validation passed these values straight to
parameterized SQL, where Postgres rejects negative LIMIT and OFFSET, so an
unauthenticated-shape adversarial input became a 500 instead of a 422.
The canonical router already enforced `ge=0` on the same parameters.

How to reproduce: `GET /api/v1/audit/events?limit=-5` returned 200
through validation (confirmed against a fake session that the value
passed validation and reached the query layer).

Root cause: `services/ingestion/app/auditor_router.py:224-225`,
`:547`, `:680` (Query declarations without `ge=0`).

Fix: added `ge=0` to `limit` on all three endpoints and to `offset` on
`/events`. Negative values now get 422 before any database work.
`limit=0` remains allowed and returns an empty page.

Test results: new `TestAuditorPaginationBounds` (5 tests) fails on old
code, passes on new. Existing `test_auditor_router_1342.py` passes.

## Finding 3 (Low): record history returns 200 for missing or foreign events

What broke: `GET /api/v1/records/{event_id}/history` returned 200 with an
empty amendment chain for an event id that does not exist under the
caller's tenant, including ids belonging to another tenant. That response
is identical to "event exists, no amendments", so callers cannot tell a
wrong or foreign id from a clean record, and sibling endpoints
(`GET /api/v1/records/{event_id}`, auditor event detail) correctly return
404 for the same input.

How to reproduce: `GET
/api/v1/records/evt-foreign/history?tenant_id=tenant-a` returned 200 with
`{"event_id": "evt-foreign", "amendment_chain": []}` before the fix, and
404 after it. No cross-tenant data was ever returned (the chain walk is
tenant-filtered), so this is a consistency issue, not a data leak.

Root cause: `services/ingestion/app/canonical_router.py:372`
(`get_record_history` walked the chain without checking the event exists
under the resolved tenant).

Fix: a tenant-scoped existence query up front, 404 when absent. Two
existing tests in `test_canonical_router.py` were updated to script the
new leading query in their fake sessions; their assertions are unchanged.

Test results: new `TestRecordHistoryNotFound` (2 tests) fails on old
code, passes on new. Full `test_canonical_router.py` passes.

## Finding 4 (Info): downloaded CSV templates contain formula-leading examples

What broke: the served `initial_packing` template example row contains
`+1-202-555-0100` and the `first_land_based_receiving` example contains
`-1.5`. Both start with characters the project's own CSV safety module
(`services/shared/fda_export/csv_safety.py`, `DANGEROUS_PREFIXES`)
defines as spreadsheet formula triggers. Opening a downloaded template in
Excel evaluates the phone example as arithmetic (displaying -2756 instead
of the sample number). Exported tenant data was already sanitized by
`fda_export_service.py`; only the static template examples were missed.

How to reproduce: generate every template with `_generate_csv_template`
and check each example cell with `sanitize_cell`. Before the fix, 2 cells
across 8 templates changed under sanitization. After the fix, none do.

Root cause: `services/ingestion/app/csv_templates.py:208`
(`_generate_csv_template` wrote example values raw).

Fix: the example row passes through the same `sanitize_cell` the FDA
export uses. Safe values are returned unchanged, so the other 6 templates
are byte-identical and round-trip ingest tests are unaffected.

Test results: new `TestTemplateFormulaSafety` (1 test) fails on old
code, passes on new. Existing `test_csv_templates.py`,
`test_csv_input_quantities.py` pass.

## Tested, no break found

Authz bypass: tenant mismatch via `?tenant_id=` returns 403, via
`X-Tenant-ID` header returns 403, conflicting query and header returns
400, wildcard `*` scope on a tenant-bound key cannot pivot tenants
(`resolve_tenant` and `require_permission` both enforce it), missing key
is 401 outside explicit dev or test mode, presented-but-invalid keys are
never downgraded to the dev-open path, and retired `X-Admin-Key` presents
are rejected. The template download endpoints are unauthenticated but
serve only static column definitions with no tenant data, and the
download filename is built from a validated CTE key.

IDOR on tenant artifacts: `get_record`, auditor event detail, and
ingestion-run detail are tenant-scoped and return 404 for foreign ids
(verified). Trace forward and backward return tenant-filtered results
with no existence signal beyond the shared supply-chain lot code.

CSV and payload edge cases: negative, zero, `nan`, `inf`, and
non-numeric quantities are all rejected; flexible date parsing rejects
unreadable dates instead of stamping placeholders; duplicate normalized
columns are rejected; oversized and unreadable files are rejected whole;
formula-prefix values in uploaded cells are stored raw but every CSV
export path in scope of this task either returns JSON or sanitizes with
`sanitize_cell`. `compliance_status` filter values outside the known set
are silently ignored (returns unfiltered); noted as a wart, left
unchanged to avoid breaking existing clients.

Not run: `test_auditor_pagination_ties_pg.py` (1 skip, needs a migrated
Postgres with the fsma schema, not available locally). Negative
pagination was therefore verified at the validation boundary (422 before
any query) rather than against live Postgres.

## Open questions

1. Should the 500-row CSV cap become a full-file rejection instead of
   partial ingest with a skipped count? The current fix keeps the pinned
   behavior (first 500 ingested) and reports the drop truthfully.
2. Should unknown `compliance_status` filter values on
   `/api/v1/audit/events` return 422 instead of unfiltered results?
   Caller decision, minor.
3. The Jev sidecar skill was not consulted: this task made no CTE-type or
   header-mapping judgment calls (no classification thresholds or
   mappings were changed), so there was nothing to ask it.
