# Traceability file intake

How three intake surfaces turn a file into FSMA Critical Tracking Events.
All three are on the production router allowlist (`csv`, `edi`,
`epcis_ingestion` in `server/router_policy.py`). Tenant identity comes from
the authenticated principal. A caller-supplied tenant id is only an
assertion and must match that principal.

| Surface | Route | Permission | What changed |
| --- | --- | --- | --- |
| Excel workbook on the CSV route | `POST /api/v1/ingest/csv` | `webhooks.ingest` | `.xlsx` is converted to CSV text, then the existing CSV path runs |
| EPCIS 2.0 upload on `/ingest` | `POST /api/v1/epcis/events`, `/events/batch`, `/events/xml` | tenant context (`require_tenant_context`) | The dashboard tab posts JSON or XML to those routes |
| Warehouse advices | `POST /api/v1/ingest/edi/document` | `edi.ingest` | X12 944 and 945, one CTE per item line |

The dedicated `POST /api/v1/ingest/edi` route is still 856 only. 944 and 945
belong on `/document`.

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
to ingest the XML file directly. A sample document is linked from the tab
at `/samples/sample_epcis_2.0.json`.

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

## X12 944 and 945 on `POST /api/v1/ingest/edi/document`

The document route auto-detects the transaction set. Supported sets are
856, 850, 810, 861, 944, and 945. 944 is a receiving CTE (warehouse stock
transfer receipt advice). 945 is a shipping CTE (warehouse shipping
advice). Other sets on this route still produce one event per ST/SE
transaction set. 944 and 945 produce one CTE per item line, and a failure
on any line rejects the interchange.

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
  used only when that header date is empty. Unparseable dates fall back to
  the ingest time.
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
  more than one transaction set, or when a 944/945 has more than one item
  line. Post one line, or omit the overrides.
- A 944/945 success body includes `extracted.event_count` and
  `extracted.events`, one summary per line (`line_index`, lot, quantity,
  GTIN, UPC). `document_type` is `X12_944` or `X12_945`.

## Tests

```bash
python3 -m pytest services/ingestion/tests/test_csv_xlsx_upload.py -q --no-cov
python3 -m pytest services/ingestion/tests/test_edi_warehouse_944_945.py \
  services/ingestion/tests/test_edi_golden.py -q --no-cov
cd frontend && npm run test:run -- src/__tests__/lib/epcis-upload.test.ts \
  src/__tests__/pages/ingest-epcis.test.tsx
```
