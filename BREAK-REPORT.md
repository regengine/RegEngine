# Break Report: services/compliance csv_safety, fsma_spreadsheet, routes

## Summary

Probed four areas with adversarial inputs against local test setups only: formula injection, semicolon handling, oversized CSV, and content type, plus auth bypass attempts, concurrency, boundary values, and malformed shapes.

Outcome: 2 breaks found, fixed, and tested. 0 fixed but failing. 0 blocked.

1. Zero quantity exported as a blank cell (data integrity, medium). Fixed.
2. One malformed event record crashed the whole export with HTTP 500 (robustness, medium). Fixed, now a structured HTTP 400.

No new formula injection break was found. First character prefix sanitizing plus QUOTE_ALL holds end to end, and that behavior is now locked in by extra tests. Semicolon bearing values round trip intact. The CSV content type already declares UTF-8. Auth, tenant mismatch, the 50,000 event boundary, and concurrent generation all behaved.

## Finding 1 (medium): quantity 0 exported as blank

What broke: an event with `"quantity": 0` produced an empty Quantity cell in the FDA spreadsheet. A zero quantity is a fact about a shipment. A blank cell reads as missing data, so the export rewrote the fact.

How to reproduce: call `_normalise_event({"type": "SHIPPING", "quantity": 0, "kdes": {}})` and read `row["quantity"]`. Old code returned `""`. At route level, `GET /v1/fsma/audit/spreadsheet` with a mocked zero quantity event returned 200 with an empty Quantity cell.

Root cause: `services/compliance/app/fsma_spreadsheet.py`, `_normalise_event` used plain `or` chains (`str(event.get("quantity") or kdes.get("quantity") or "")`). `0` is falsy, so it fell through to `""`. The same pattern also dropped zero valued text fields, zero valued named KDEs, and zero valued extra KDEs from the JSON column.

Fix: added a `_pick()` helper that treats only `None` and `""` as missing and applied it to every value selection chain, the named KDE filter, and the extra KDE filter in `_normalise_event`.

Test results: `services/compliance/tests/test_csv_break_adversarial.py` adds unit tests (zero quantity, fallback order, zero text and KDE values, CSV round trip) and a route test. All pass. Confirmed fail without the fix: on original code `quantity=0` returned `""`.

## Finding 2 (medium): malformed record shape returned HTTP 500

What broke: an event whose `kdes` was a truthy non object value (string, number, or non empty list) crashed `_normalise_event` with `AttributeError`, and the route returned an unhandled HTTP 500 for the entire export window. One bad record denied the whole export with no actionable message.

How to reproduce: `GET /v1/fsma/audit/spreadsheet` with the event loader mocked to return `[{"type": "SHIPPING", "kdes": "planted", ...}]`. Old code returned 500 Internal Server Error.

Root cause: `services/compliance/app/fsma_spreadsheet.py`, `_normalise_event` called `kdes.get(...)` with no type check, and `services/compliance/app/routes.py`, `fsma_audit_spreadsheet` caught only `FSMATimestampError`. Note the sibling read path in `services/shared/canonical_persistence/verification.py` already defends against non dict `kdes` with an isinstance check, but the export query path (`r[12] if r[12] else {}`) passes stored scalars and lists straight through.

Fix: added `FSMAEventError(ValueError)`; `_normalise_event` raises it for non dict events and non dict `kdes` instead of crashing; the route catches it next to `FSMATimestampError` and returns a structured HTTP 400 naming the problem. The export still aborts rather than silently dropping a record from a regulatory submission.

Test results: unit tests for each bad shape (str, int, list, tuple, None event) plus route tests asserting 400 with a malformed detail and no Content-Disposition header. All pass. Confirmed fail without the fix: original code raised `AttributeError` and the route returned 500.

## Probed, no break

* Formula injection: 8 payload shapes (`=`, `+`, `-`, `@`, tab, CR, HYPERLINK, WEBSERVICE) all neutralized end to end through generate plus CSV reparse. Existing #1272 tests already cover the main cases. No change.
* Semicolon values (`TLC;001`, `a;b;c`): round trip intact with correct column counts under QUOTE_ALL. No change.
* Content type: Starlette already renders `text/csv; charset=utf-8`, and non ASCII bodies (Cafe with accent, degree sign) arrive intact. No change needed.
* Oversized CSV: the 50,000 event hard cap holds (exactly 50,000 returns 200 with all rows, 50,001 returns 413 per existing tests). A single multi megabyte field exports fine; Python csv readers with default limits cannot reparse huge fields, but that is consumer side behavior, and truncating regulatory data to fit would be worse. No change.
* Auth: unauthenticated requests get 401, tenant header mismatch gets 409, missing tenant gets 403. No change.
* Concurrency: 8 threads generating exports simultaneously, no errors. No change.
* `safe_cell` gaps for newline prefix, leading whitespace, BOM, pipe, percent, and zero width prefixes: these pass through unchanged, but no spreadsheet evaluator was found that executes such cells as formulas (evaluation keys off the first character, which is what the module contract covers), so these were not claimed as breaks. Left for the shared module owners as a possible hardening item since `csv_safety` is shared with ingestion under EPIC-L.
* NaN or Infinity inside extra KDEs serializes as bare `NaN` tokens (invalid strict JSON): unreachable through Postgres JSONB storage, only through direct library calls. Left unchanged, noted below.

## Open questions

1. Should the ingestion CSV export also be checked for the falsy value drop, or does its row builder already handle zero quantities. Not inspected in this task.
2. Should oversized single cell values get an explicit byte cap with a 413, or is the event count cap plus async batched jobs enough. This needs a product decision because truncation is not acceptable for submissions.
3. Should `safe_cell` in `services/shared/fda_export/csv_safety.py` also escape a leading newline for symmetry with tab and CR. Low value, shared surface, needs ingestion side review.
4. The audit log line for the export warning was renamed from `fda_export_malformed_event_date` to `fda_export_malformed_event`. Any dashboard alert matching the old name needs updating.
