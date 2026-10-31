# Traceability file intake

How CSV, EPCIS, and EDI intake turn a file into FSMA Critical Tracking Events.
All three are on the production router allowlist (`csv`, `edi`,
`epcis_ingestion` in `server/router_policy.py`). Tenant identity comes from
the authenticated principal. A caller-supplied tenant id is only an
assertion and must match that principal.

| Surface | Route | Permission | What it emits |
| --- | --- | --- | --- |
| Excel workbook on the CSV route | `POST /api/v1/ingest/csv` | `webhooks.ingest` | `.xlsx` is converted to CSV text, then the existing CSV path runs |
| EPCIS 2.0 upload on `/ingest` | `POST /api/v1/epcis/events`, `/events/batch`, `/events/xml` | tenant context (`require_tenant_context`) | The dashboard tab posts JSON or XML to those routes |
| ASN and receiving advice lines | `POST /api/v1/ingest/edi` and `POST /api/v1/ingest/edi/document` | `edi.ingest` | X12 856 and 861, one CTE per item line |
| Warehouse advices | `POST /api/v1/ingest/edi/document` | `edi.ingest` | X12 944 and 945, one CTE per item line |
| Purchase order and invoice | `POST /api/v1/ingest/edi/document` | `edi.ingest` | X12 850 and 810, one event per ST/SE set, quantities summed |

`POST /api/v1/ingest/edi` accepts a single 856 transaction set. 861, 944,
945, 850, and 810 belong on `/document`.

## EDI event time

Both EDI routes store the source date as the event time.
`_ship_timestamp_and_date` in
`services/ingestion/app/edi_ingestion/utils.py` parses CCYYMMDD or YYMMDD
into a UTC timestamp (`YYYY-MM-DDTHH:MM:SS+00:00`). A date with no time
is midnight UTC. A YYMMDD year uses `EDI_CENTURY_PIVOT` (default 50):
YY below the pivot is 20YY, and YY at or above it is 19YY.

The preflight runs after the partner allowlist and before the ISA13
control number is reserved. A date rejection does not reserve that
control number, so a corrected resend is not refused as a 409 replay.
Each rejection is written to the EDI rejection log with
`needs_review: true`, and the HTTP detail includes `rejection_id`.

| Source date | Status | `error` |
| --- | --- | --- |
| Missing or blank | 400 | `missing_edi_date` |
| Not CCYYMMDD or YYMMDD | 400 | `invalid_edi_date` |
| 856 time (BSN04) has at least four digits and the hour or minute is impossible | 400 | `invalid_edi_time` |
| More than 24 hours after the current UTC time | 400 | `edi_date_in_future` |
| A parseable date at or before that cutoff, including a date older than 90 days | accepted | timestamp is that source date |

856 is the only set that reads a time. The first four digits of BSN04
are the hour and minute. Fewer than four digits leaves the time at
midnight UTC. Seconds in a longer BSN04 are ignored. 944 and 945 pass
no time into the parser. A date more than 24 hours ahead is rejected.
A date exactly 24 hours ahead is kept.

| Set | Date element | Time |
| --- | --- | --- |
| 856 | BSN03 | BSN04 |
| 861 | BRA02 | none |
| 944 | W1702. A G62 date is used only when W1702 is empty. | none |
| 945 | W0603. A G62 date is used only when W0603 is empty. | none |
| 850 | BEG05 | none |
| 810 | BIG01 | none |

On `POST /api/v1/ingest/edi` a missing BSN date is this 400. The later
856 placeholder check (`edi_856_missing_required_kdes`) still rejects a
missing ship-from, ship-to, quantity, unit, or product, and it does not
get a chance to report the date.

### Accepted TLC shapes

EDI persistence validates the event TLC with `FSMAEvent` in
`services/shared/schemas.py`. A failure is HTTP 422
`fsma_validation_failed`. The validator accepts the submitted string
when it is one of these:

- Fourteen digits followed by a lot suffix of letters, digits, `-`, or
  `.`. The whole value is at least 15 characters.
- An LGTIN class URN: `urn:epc:class:lgtin:`, two digit groups whose
  lengths add up to 13, a dot, then the lot.
- A GS1 Digital Link: `http://` or `https://`, a host, optional extra
  path segments, `/01/` and 14 digits, `/10/` and the lot, then an
  optional further path and query.

On the URN and Digital Link forms the lot, after percent-decoding, is
1 to 20 characters from GS1 character set 82 (digits, both letter
cases, and the twenty specials in that set; no space). A character the
carrier requires to be percent-encoded, or a `%` that is not a `%HH`
escape, fails the match. The stored TLC is the submitted string.

## Excel `.xlsx` on `POST /api/v1/ingest/csv`

`services/ingestion/app/shared/xlsx_rows.py` turns the workbook into the CSV
text a "Save as CSV" would produce. `parse_csv_rows`, Jev header and
file-CTE suggestions, row validation, and persistence then run unchanged.
The ingestion run keeps the original workbook bytes. When the form `source`
is left at its default `csv_upload`, the recorded source becomes
`xlsx_upload`.

```bash
curl -X POST "$BASE/api/v1/ingest/csv" \
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \
  -F "file=@events.xlsx;type=application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
  -F "sheet_name=Shipping" \
  -F "cte_type=shipping"
```

`cte_type` is optional when the sheet has a `cte_type` or `event_type`
column, same as CSV. `sheet_name` selects a worksheet. Omit it to read the
first sheet. A name that is not in the workbook is HTTP 400 and the detail
lists the sheet names.

### What is read

- The first non-empty row is the header. Fully empty rows are skipped.
- At most 200 columns. More is HTTP 400.
- At most 500 data rows (`MAX_CSV_ROWS`). One extra data row is still read
  so the CSV parser can report the row-limit error.
- The reader stops after 20,000 scanned rows, blanks included. Cells past
  that window are not read and do not raise their own error.
- The upload itself is capped at 5 MB (`MAX_CSV_FILE_SIZE_BYTES`). The
  declared uncompressed size of the xlsx zip is capped at 100 MB before
  openpyxl opens it.
- Dates at midnight with no timezone become `YYYY-MM-DD`. Other datetimes
  become ISO 8601. Booleans become `TRUE` / `FALSE`. Whole-number floats
  become integers (`10.0` becomes `10`).
- Formula cells are read with `data_only=True`. Only Excel's last cached
  value is kept. A formula with no cached value is blank, and the response
  `kde_warnings` names the cells (up to 20, then a count). Recalculate and
  save in Excel, then upload again. Files written by libraries that never
  store a cached value hit this on every formula cell.

### What is rejected

| Upload | Status | Detail |
| --- | --- | --- |
| `.xls`, `.xlsm`, `.xlsb`, `.xltm`, macro content type, or a zip that contains `xl/vbaProject.bin` | 415 | Save as `.xlsx` (Excel Workbook) or CSV UTF-8 |
| Not a zip, a bad package, or a password-protected workbook | 400 | Same save-as guidance |
| Declared uncompressed size over 100 MB, or more than 200 columns | 400 | Named limit |

An `.xlsx` file name always selects the workbook reader. The OOXML content
type selects it only when the bytes start with ZIP magic (`PK`), so a CSV
sent with a wrong content type stays on the CSV decoder. The generic
`application/vnd.ms-excel` type does not select the workbook reader: Windows
browsers send it for ordinary `.csv` files.

Inbound email does not accept workbooks. That channel still requires a
`.csv` attachment. See
[EMAIL_INGESTION.md](EMAIL_INGESTION.md).

## EPCIS 2.0 on the dashboard ingest page

`/ingest` has an EPCIS 2.0 tab (`frontend/src/app/ingest/page.tsx`).
`frontend/src/lib/epcis-upload.ts` chooses the route. The API key is stored
first, the same way as a CSV upload, and the browser proxy sends it. The
tab does not pass `mode`.

| File | Request |
| --- | --- |
| EPCIS 2.0 JSON document (`epcisBody.eventList`) | `POST /api/v1/epcis/events/batch` with `{ "events": [ ... ] }` |
| JSON array of event objects | same batch route |
| One JSON event object | `POST /api/v1/epcis/events` |
| `.xml` | `POST /api/v1/epcis/events/xml` with the file text and `Content-Type: application/xml` |

Validate-only calls `POST /api/v1/epcis/validate` once per JSON event and
does not ingest. XML has no validate-only path; the tab tells the operator
to ingest the XML file directly.

Empty documents, empty arrays, and non-JSON text fail in the browser. No
request is sent.

### All or nothing, by default

CSV ingest keeps the good rows and reports the bad ones. EPCIS batch and
XML default to atomic mode (`EPCIS_BATCH_TRANSACTIONAL` defaults to true in
`services/ingestion/app/epcis/persistence.py`):

- Every event is validated first. Any failure is HTTP 400
  `batch_validation_failed`. Nothing is persisted. The detail lists
  per-event errors.
- If persistence fails mid-batch, the transaction rolls back and the
  response is HTTP 400 `batch_persistence_failed`.
- `?mode=partial`, or `EPCIS_BATCH_TRANSACTIONAL=false`, restores per-event
  processing and HTTP 207 when some events succeed. The dashboard does not
  send `mode`, so a tab upload follows the server default.

The consolidated app also rejects bodies over 10 MB
(`RequestSizeLimitMiddleware` in `server/main.py`). The XML route applies
the same 10 MB cap while reading the body. The tab's helper text says
5 MB; that label is stricter than the API cap, and the page does not
enforce it before the request.

A single-event POST is one event: HTTP 201, or the validation error for
that event. It is not a batch.

## X12 856 and 861, one CTE per item line

An 856 ship notice and an 861 receiving advice used to collapse every item
line into one event and add the quantities under one traceability lot code.
Both routes now keep each line. A failure on any line rejects the
interchange. 850 and 810 are unchanged: each ST/SE set is still one event,
and PO1 or IT1 quantities on that set are summed.

| | 856 ship notice | 861 receiving advice |
| --- | --- | --- |
| CTE | shipping | receiving |
| Item line | One CTE per SN1. SLN is not a CTE. | One CTE per RCD. SLN is not a CTE. |
| Quantity | SN102. Must be a finite number above 0 when the element is present. | RCD02, same rule |
| Unit | SN103, X12 element 355 | RCD03 |
| Lot | LIN `LT`, a `REF*LT` on that line, or an SLN `LT` pair | same |
| Product | LIN qualifiers `SK`, `UP`, `EN`, `VP`, `BP`, else PID05 | same |
| Date | BSN03, with BSN04 time when present | BRA02. BRA01 is the advice number. A purpose-code-first BRA (`BRA*00*...*date`) is HTTP 400 `invalid_edi_date`. |
| Parties | Ship-from is N1 `SF`, `SU`, or `SH`. Ship-to is N1 `ST`, `BT`, or `OB`. | Ship-from is the same. The receiving location uses the ship-to codes. |

A LIN before the quantity segment fills the next SN1 or RCD. A LIN after a
quantity segment that still has no product and no lot fills that line. A
later LIN starts the next item. PID text and `REF*LT` attach to the open
line, or to the draft when no line is open yet.

The line lot is the event TLC, copied verbatim. A GTIN or UPC on the line
does not prefix it. A line with no lot uses the required form field
`traceability_lot_code`. A lot that fails TLC format is HTTP 422
`fsma_validation_failed`, including a one-character lot. The shapes
`FSMAEvent` accepts are listed under
[Accepted TLC shapes](#accepted-tlc-shapes). Two lines that
share a lot both persist. `edi_line_index` on the KDEs separates them.

N104 is stored as the location id whether or not N103 is `UL`. The event
`location_gln` is set only when that id is a 13-digit GS1 GLN with a valid
check digit. The 856 event location is the ship-from GLN. The 861 event
location is the receiving-location GLN.

The event time is the BSN date (and BSN04 time when present). See
[EDI event time](#edi-event-time).

### `POST /api/v1/ingest/edi` (856 only)

One ST/SE set. A second set is HTTP 422 `multiple_transaction_sets`. The
error text still says `/document` emits one CTE per ST/SE pair. For 856
and 861, `/document` emits one CTE per item line.

Required segments are ISA, GS, ST, BSN, HL, SE, GE, and IEA. Each line
must carry a positive quantity, a recognized unit, and a product id or
description. The set must carry a ship-from name and a ship-to name. A
miss on those fields is HTTP 422 `edi_856_missing_required_kdes`, the
rejection is logged, and nothing is persisted. A missing BSN date is
HTTP 400 `missing_edi_date` from the event-time preflight, which runs
before that placeholder check. The route does not fill quantity `1.0`,
unit `units`, product `EDI 856 Shipment`, an unknown location, or
today's date.

`product_description`, `quantity_override`, `unit_of_measure_override`,
`ship_from_location_override`, and `ship_to_location_override` apply to
every line. More than one SN1 plus any of those fields is HTTP 422
`edi_overrides_with_multiple_line_items`.

A success body reports `extracted.event_count`. `extracted.quantity` and
`extracted.unit_of_measure` describe the first line. The response
`traceability_lot_code` is the first event's TLC.

### `POST /api/v1/ingest/edi/document`

856 and 861 join 944 and 945 as line-level sets. The same interchange
rules below apply: one transaction-set type, GE01 must match the ST/SE
count, and any FSMA failure keeps the whole interchange out of the
canonical stream.

On this route a present quantity that is zero or not numeric is HTTP 422
`edi_non_positive_quantity`. A present unit is HTTP 422
`edi_unmapped_unit_of_measure` unless it is an element-355 code this
route maps (`CA` and `CS` cases, `CT` cartons, `BX` boxes, `BG` bags,
`LB` lbs, `KG` kg, `EA` each, `UN` units, `PL` pallets, `PC` and `PK`
pieces), a tolerated non-X12 alias (`CAS`, `CTN`, `BOX`, `LBR`,
`KGM`), or a value that is already an FSMA unit name (`cases`,
`cartons`, `lbs`, and the rest of `VALID_UNITS_OF_MEASURE`). A blank
unit is stored as `units`. A set with no SN1 or RCD
still produces one event: the quantity element is absent, so the
persisted quantity is `1.0`, a missing product becomes `EDI 856 Item`
or `EDI 861 Item`, and a missing location name becomes `Unknown`.

Header KDEs are copied onto every line. 856 copies the ASN number
(BSN02), carrier (TD5), and the reference document (`REF` `BM`, `SI`,
`CN`, `PO`, or `PK`, else the ASN number). 861 copies the advice number,
the PO when `REF*PO` is present, the condition code (RCD05), and the
reference document (`PO`, `BM`, or `SI`, else the advice number).

`extracted.event_count` and `extracted.events` list one summary per line
(`line_index`, lot, quantity, TLC). `extracted.submitted_traceability_lot_code`
echoes the form field. The response `traceability_lot_code` is the first
event's TLC.

```bash
curl -X POST "$BASE/api/v1/ingest/edi/document" \
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \
  -H "X-Partner-ID: $PARTNER_ID" \
  -F "file=@asn_856.edi;type=application/edi-x12" \
  -F "traceability_lot_code=FALLBACK-TLC-WHEN-A-LINE-HAS-NO-LOT" # pragma: allowlist secret
```

## X12 944 and 945 on `POST /api/v1/ingest/edi/document`

The document route auto-detects the transaction set. Supported sets are
856, 850, 810, 861, 944, and 945. 944 is a receiving CTE (warehouse stock
transfer receipt advice). 945 is a shipping CTE (warehouse shipping
advice). 944 and 945 produce one CTE per item line, and a failure on any
line rejects the interchange. 850 and 810 stay one event per ST/SE set.

```bash
curl -X POST "$BASE/api/v1/ingest/edi/document" \
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \
  -H "X-Partner-ID: $PARTNER_ID" \
  -F "file=@receipt_944.edi;type=application/edi-x12" \
  -F "traceability_lot_code=UNUSED-FOR-944" \
  -F "tlc_source_reference=wh-receipt-source"
```

`traceability_lot_code` is still a required form field. For 944 and 945 it
is not the event TLC. Each line's warehouse lot is. The submitted value is
echoed as `extracted.submitted_traceability_lot_code`.
`tlc_source_reference` is copied onto each line's KDEs when present.

### Segments that become the CTE

Envelope segments ISA, GS, ST, SE, GE, and IEA are required on both sets.
944 also requires W17. 945 also requires W06. A missing required segment is
HTTP 422 and names the segment.

| | 944 receipt | 945 shipment |
| --- | --- | --- |
| Header | W17. Date is W1702. Receipt number is W1703. | W06. Ship date is W0603. Shipment id is W0604. |
| Item line | One CTE per W07 | One CTE per W12 |
| Quantity | W0701, quantity received. Must be > 0. | W1203, units shipped. Must be > 0. W1202 is quantity ordered and is stored as `quantity_ordered`. It is not the CTE quantity. |
| Unit | W0702 | W1205 |
| Lot | W0708 | W1209 |
| UPC seed | W0703 | W1206 |
| Description | G69 text on that line, else a product-id qualifier in SK, VN, BP, IN, VP, PI | same |

Product-id pairs are read as (qualifier, value): 944 uses W07 elements
(04,05), (06,07), (18,19), (20,21). 945 uses W12 elements (07,08),
(19,20), (21,22). `UP` fills UPC. `UK`, `EN`, `UI`, `UA`, `EO` fill GTIN.
W0708 and W1209 stay the lot; they are not product-id qualifiers.

A line with no lot, or a quantity that is missing, zero, or not numeric,
fails FSMA validation. In the default strict mode that is HTTP 422
`fsma_validation_failed` and no event from the interchange is persisted.
`?strict=false` or `EDI_STRICT_MODE=false` records the rejection and still
does not write the canonical stream.

If the lot is not already a valid TLC and the line has a GTIN of length
8, 12, 13, or 14, or a UPC of length 12 or 13, the event TLC becomes
`{item id padded to 14}-{lot}`.

### Parties, dates, and references

A GLN is taken from N1 only when N103 is `UL`. Qualifier `92` stays an
assigned id and the GLN stays empty.

- 944 receiving location is N1*WH. If that party is absent, N1 ship-to
  codes (`ST`, `BT`, `OB`) are used. Ship-from is N1*SF (also `SU`, `SH`);
  if none of those appear, the depositor (N1*DE) is the ship-from.
- 945 ship-from is N1*SF when present, otherwise the warehouse (N1*WH).
- The event date prefers the header date (W1702 or W0603). A G62 date is
  used only when that header date is empty. Parsing, rejection codes, and
  the stored UTC timestamp are in [EDI event time](#edi-event-time).
- 944 reference document number is the warehouse receipt number, else the
  shipment id. 945 uses the shipment id, else the depositor order number.
  N9 fills a blank reference (`BM`, `SI`, `PO`, `PK`, `CN`, in that order).
  An N9 `LT` reference is kept only on the line whose lot matches it.

### Interchange rules

- One functional group, one transaction-set type. A mix is HTTP 422
  `mixed_transaction_sets`.
- GE01 must match the number of ST/SE sets. A mismatch ingests nothing.
- The file must be UTF-8 or ISO-8859-1. Other bytes are HTTP 422
  `edi_decode_failed`. Empty or non-EDI content is HTTP 400. The file cap
  is 5 MB.
- `product_description`, `quantity_override`, `unit_of_measure_override`,
  and `location_override` are refused (HTTP 422) when the interchange has
  more than one transaction set
  (`edi_overrides_with_multiple_transaction_sets`), or when an 856, 861,
  944, or 945 has more item lines than transaction sets
  (`edi_overrides_with_multiple_line_items`). The line-item error text
  says "warehouse lines" for all four sets. Post one line, or omit the
  overrides.
- A 944/945 success body includes `extracted.event_count` and
  `extracted.events`, one summary per line (`line_index`, lot, quantity,
  GTIN, UPC). `document_type` is `X12_944` or `X12_945`.

## Tests

```bash
python3 -m pytest services/ingestion/tests/test_csv_xlsx_upload.py -q --no-cov
python3 -m pytest services/ingestion/tests/test_edi_warehouse_944_945.py \
  services/ingestion/tests/test_edi_golden.py \
  services/ingestion/tests/test_edi_wire_format_2974_2976_2978.py \
  services/ingestion/tests/test_edi_preserve_event_time.py \
  services/ingestion/tests/test_edi_date_reject_resend.py -q --no-cov
cd frontend && npm run test:run -- src/__tests__/lib/epcis-upload.test.ts \
  src/__tests__/pages/ingest-epcis.test.tsx
```
