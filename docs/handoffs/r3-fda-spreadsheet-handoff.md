# R3 handoff: FDA sortable spreadsheet failures (for Hermes, SEL-504 / SEL-519)

Context: the spreadsheet answers FDA's 24-hour records request, 21 CFR 1.1455(c)(1).
Export code is in `services/compliance/app/fsma_spreadsheet.py` (not edited by R3).
Tests: `services/compliance/tests/test_fda_spreadsheet_r3_checks.py` (each case is `xfail(strict=True)`; a fix flips it to XPASS, which fails CI until the marker is removed).
Fixture: `services/ingestion/tests/fixtures/01_harvesting.csv`, row 1 (GLN `0061414100014`, harvest_date `2026-03-12`).
Header source: FDA template https://www.fda.gov/media/179616/download (PDF, sha256 `632ed553…f5212a4`), checked by `scripts/check_fda_spreadsheet_headers.py`.

## Code path
The spreadsheet does **not** share the EPCIS code path. `fsma_spreadsheet.py` imports only `csv_safety`; EPCIS is built separately in `services/graph/app/routers/fsma/compliance.py::export_epcis` and `services/ingestion/app/epcis_export.py`. Both read the same graph event records, so a GLN/GTIN fix in the data layer helps both, but a fix in the spreadsheet builder does not reach EPCIS. (Observation, not tested here: graph `export_epcis` builds `urn:epc:id:sgtin:{tlc}` from the lot code, which is not a GTIN-based SGTIN.)

## Cases

| ID | Function | Input | Actual | Expected |
|---|---|---|---|---|
| R3-A1 | `generate_fda_csv` | any | one untitled CSV | one FDA-named tab for each CTE in the request, e.g. only Harvesting for a harvesting-only request (the FDA template defines 13 CTE tabs; tabs for CTEs not in the request are not required) |
| R3-A2 | `FDA_HEADERS` | FDA template PDF | 29/29 headers do not match a whole header cell on an FDA tab; 9 equal a header cell on some FDA tab | headers per tab exactly as FDA's tab |
| R3-B1 | `_parse_timestamp` | fixture date + runtime local offset, e.g. `2026-03-12T01:11:00-07:00` | Event Time `01:11:00` | `01:11:00-07:00` (offset kept) |
| R3-B2 | `_parse_timestamp` / `_normalise_event` | fixture `harvest_date` `2026-03-12` (date only) | Event Time `00:00:00` (invented midnight, no zone) | reject, or emit no time and flag it (a zoned time is also fine) |
| R3-B3 | `_normalise_event` (`kdes.event_time` override) | `kdes.event_time` = `01:11:00` with tz-aware event_date | `01:11:00` | reject, or emit a zoned time, or emit no time and flag it |
| R3-C1 | `_normalise_event` origin GLN | fixture GLN with check digit +1: `0061414100015` | exported `0061414100015`, Risk Flag empty | reject (GS1 check digit fails) |
| R3-C2 | `_normalise_event` origin GLN | fixture row with GLN `""` | Origin GLN `""`, Risk Flag empty | reject or flag |
| R3-C3 | `FDA_HEADERS` | n/a | no GTIN column | a product GTIN column (SEL-504) |

Note on R3-C1: `0061414100015` is a deliberate bad-check-digit negative case, derived from the fixture's real GLN `0061414100014` by changing only the check digit, under C.Lee's R3 fixture exception. It is not a real GLN.
