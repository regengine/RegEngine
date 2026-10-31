# Trace and export limits

What a caller receives when a trace or an FDA-oriented export is larger
than the query cap, and how the compliance spreadsheet writes Event
Time. Confirm the router is enabled before calling it.
`server/router_policy.py` is the production allowlist.

## FDA sortable spreadsheet

`GET /v1/fsma/audit/spreadsheet` is on the `fsma_compliance` router,
which is on the production allowlist. Implementation:
`services/compliance/app/routes.py` and
`services/compliance/app/fsma_spreadsheet.py`.

The caller is an API key. Tenant scope is the key's tenant. An
`X-Tenant-ID` or `X-RegEngine-Tenant-ID` header that names a different
tenant is HTTP 409 `E_TENANT_MISMATCH`. A key with no tenant is HTTP
403.

`start_date` and `end_date` are required `YYYY-MM-DD` values.
`validate_export_window` requires `end_date` on or after `start_date`
and a span of at most 90 days (`(end - start).days` greater than 90 is
HTTP 400). Optional `tlc` filters one lot code. Optional
`requesting_entity` must match `^[A-Za-z0-9 .,&'\-]{0,120}$`.

| Outcome | Status |
| --- | --- |
| At least one event | 200, CSV attachment |
| No events in the window | 404 |
| More than 50,000 events | 413. Narrow the dates or the TLC. |
| Event storage cannot be reached | 503 |
| An event date or event shape cannot be rendered | 400. The export stops. |

### Event Time

Zone-aware timestamps are converted to UTC before they are written.
`Event Date` is the UTC date, which can be the next or previous
calendar day. `Event Time` is `HH:MM:SSZ`. Rows sort by that date, then
that time, so two events from different offsets sort in real order.

A timestamp with no zone is written as `HH:MM:SS` with no suffix. The
spreadsheet does not label it UTC. A date-only value becomes midnight
with no zone (`00:00:00`).

When `kdes.event_time` is present and not blank, that string is the
Event Time cell, including a value with no zone. The date still comes
from the parsed event timestamp.

A malformed `event_date` on this path raises `FSMATimestampError` and
the route returns HTTP 400. It does not truncate the raw string into
the date column.

```bash
python3 -m pytest services/compliance/tests/test_fda_event_time_utc_sel519.py \
  services/compliance/tests/test_fda_spreadsheet.py -q --no-cov
```

## EPCIS and FDA export on the experimental export router

`POST /api/v1/export/epcis` and `POST /api/v1/export/fda` are
`services/ingestion/app/epcis_export.py`. The owner is `export`, which
is in `EXPERIMENTAL_ROUTERS` and is off the production allowlist.

Both routes read `fsma.cte_events` for the authenticated tenant
context. The JSON `tenant_id` field does not select a different tenant.
`lot_code`, `date_from`, and `date_to` filter the query. `date_from` is
inclusive and `date_to` is exclusive (`event_timestamp < date_to`).

| Outcome | Status | Body |
| --- | --- | --- |
| The query succeeds and the row count is within 50,000 | 200 | EPCIS document, or the FDA CSV from this module |
| The query succeeds and returns no rows | 200 | EPCIS metadata says `No data yet`. The FDA route returns the header row, `X-RegEngine-Events-Count: 0`, and `X-RegEngine-Message: No data yet` |
| The database read fails | 503 | `Event storage unavailable; export not generated` |
| The query returns more than 50,000 rows | 413 | Names the 50,000-event cap and asks for a narrower date range or lot code |

The cap query fetches 50,001 rows. Crossing the cap refuses the export.
It does not return the newest 50,000 and omit the rest. The compliance
spreadsheet above uses the same cap and, unlike this router, returns
404 when the window is empty.

The FDA CSV on this router formats `event_timestamp` with
`%Y-%m-%d` and `%H:%M:%SZ`. That is a separate writer from the
compliance spreadsheet in the previous section.

```bash
python3 -m pytest services/ingestion/tests/test_epcis_export_1342.py -q --no-cov
```

## Graph traces and gap queries

The graph router is in `EXPERIMENTAL_ROUTERS`. On the consolidated app
its prefix is `/api/v1`.

### Forward and backward trace

`GET /api/v1/fsma/traceability/trace/forward/{tlc}` and
`GET /api/v1/fsma/traceability/trace/backward/{tlc}`.

Each capped query reads `TRACE_ROW_LIMIT + 1` rows. The limit is 5000
(`services/graph/app/fsma/tracer.py`).

| Rows the capped query returned | Response |
| --- | --- |
| 5000 or fewer | `truncated` is false and `truncation_limit` is null |
| 5001 | `truncated` is true, `truncation_limit` is 5000, and the extra row is dropped |

The HTTP status stays 200. The body is a partial trace: the events that
fit, plus `truncated: true`. A recall response that ignores the flag
treats a cut-off chain as the whole chain.

The association query that rebuilds lot, event, and facility rows uses
the same cap. That query alone can set `truncated` even when the event
list is shorter than 5000.

### Gap, chain, and orphan reads

`find_gaps`, `find_broken_chains`, and `find_orphaned_lots` read Neo4j
in keyset pages of 2000 (`_PAGE_SIZE` in
`services/graph/app/fsma/chain_integrity.py`). Each page starts after
the last key already returned. The functions yield every matching row
into one result. A result larger than 2000 is the full set.

HTTP routes that call them:

- `GET /api/v1/fsma/compliance/gaps` and
  `GET /api/v1/fsma/compliance/export/gaps` call `find_gaps`
- `GET /api/v1/fsma/compliance/gaps/orphans` calls `find_orphaned_lots`

`find_broken_chains` uses the same pager. `find_all_gaps` calls it
together with `find_gaps`. The compliance router has no separate
broken-chain route. The responses above have no page cursor. The caller
receives the assembled list. A missing tenant id raises `ValueError`
inside these functions, so a null tenant does not become a cross-tenant
read.

```bash
python3 -m pytest services/graph/tests/test_trace_truncated_flag_sel515.py \
  services/graph/tests/test_graph_row_paging_r1.py -q --no-cov
```
