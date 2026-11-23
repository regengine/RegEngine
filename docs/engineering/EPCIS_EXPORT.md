# EPCIS export

Three routes build an EPCIS document. They do not share a cap, a store, or
a truncation flag. The production router allowlist is
`PRODUCTION_ENABLED_ROUTERS` in `server/router_policy.py`.

| Route | Router | Allowlist | Store | Over the cap |
| --- | --- | --- | --- | --- |
| `GET /api/v1/epcis/export` | `epcis_ingestion` | production | `fsma.cte_events` | 2,000 events, newest first. The body says so. |
| `POST /api/v1/export/epcis` | `export` | experimental | `fsma.cte_events` plus KDE joins | HTTP 413 at 50,001 rows. No partial file. |
| `GET /api/v1/fsma/compliance/export/epcis` | `graph` | experimental | Neo4j | HTTP 413 at 50,001 events. Needs Neo4j. |

`POST /api/v1/export/fda` is the experimental CSV sibling of the JSON-LD
route. It is not `GET /api/v1/fda/export` and not
`GET /v1/fsma/audit/spreadsheet`. Those two are the release-enabled FDA
spreadsheets.

Public sample EPCIS downloads are a separate proof surface.

## Production replay: `GET /api/v1/epcis/export`

`services/ingestion/app/epcis/router.py` returns events already stored for
the authenticated tenant. The query uses `require_tenant_context`. The
`X-Tenant-ID` header on this route is not read.

```bash
curl "$BASE/api/v1/epcis/export?start_date=2026-01-01T00:00:00Z&end_date=2026-02-01T00:00:00Z" \
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY"
```

`start_date` and `end_date` must be ISO 8601. Anything else is HTTP 400
before the database is touched. The SQL filter then receives those original
strings: `event_timestamp >= start_date` and `event_timestamp < end_date`.
A zone-less value is not rewritten to UTC on this path. The in-memory
fallback does treat a zone-less bound as UTC, and a stored event time it
cannot parse is kept rather than dropped. `product_id` is applied in
Python after the SQL limit, and it matches the `product_id` KDE only.

The database path reads `EXPORT_EVENT_LIMIT + 1` rows (2,000) from
`services/ingestion/app/epcis/persistence.py`, ordered by
`event_timestamp DESC`. The extra row is not returned. The response states
the cut in `regengine:metadata`:

| Field | Meaning |
| --- | --- |
| `regengine:event_count` | Events in this body |
| `regengine:limit` | 2000 on the database path. `null` on the in-memory fallback. |
| `regengine:truncated` | True when the date window had more rows than the limit. Decided before the `product_id` filter, so a short list can still be truncated. |
| `regengine:ordering` | `event_timestamp desc` |

A database error is HTTP 503 `Database unavailable`, unless
`ALLOW_EPCIS_IN_MEMORY_FALLBACK` is `1`/`true`/`yes`. When that variable is
unset, the fallback is on outside production. The fallback has no cap, so
`regengine:limit` is null and `regengine:truncated` is false. Do not read
that as "the tenant has 2,000 or fewer events."

An empty tenant is HTTP 200 with an empty `eventList` and
`regengine:message` `No data yet`.

## Experimental builder: `POST /api/v1/export/epcis`

`services/ingestion/app/epcis_export.py` rebuilds a GS1 EPCIS 2.0 JSON-LD
document from `fsma.cte_events`. The router is mounted only when `export`
is enabled. Production does not enable it. The document is labeled Preview
(`regengine:exportMetadata.preview` is true). `integrityVerified` and
`chainHashVerified` stay false: the route copies stored hashes and does
not recompute them.

The JSON body requires `tenant_id`. The query ignores it and uses
`ctx.tenant_id`. A body that names some other tenant still exports the
authenticated tenant.

```bash
curl -X POST "$BASE/api/v1/export/epcis?validate=true" \
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"tenant_id":"ignored-use-the-api-key-tenant","format":"epcis","lot_code":"LOT-A","date_from":"2026-01-01","date_to":"2026-02-01"}'
```

`date_from` is inclusive and `date_to` is exclusive on `event_timestamp`.
This route does not validate those strings. A database error, including a
cast failure, is HTTP 503 `Event storage unavailable; export not generated`.
The same 503 is used when the database cannot be read. An empty match is
HTTP 200, `dataSource` `empty`, and `regengine:message` `No data yet`.

`?validate=true` adds `regengine:validation` and
`X-RegEngine-Schema-Valid`. Validation checks the document this route just
built. It does not call a GS1 schema file.

`GET /api/v1/export/formats` lists `epcis` and `fda` only, both `preview`.

### Cap

`_MAX_EXPORT_EVENTS` is 50,000. The unfiltered query reads one extra row.
More than 50,000 rows is HTTP 413 with no file. Rows are counted before
events are skipped, so a tenant can receive 413 even though a rebuilt
document would have held fewer than 50,000 events.

A `lot_code` filter does not apply `LIMIT` in SQL. Other lots whose class
URIs merely share a suffix must not fill the cap and hide the requested
lot. The route streams candidates and keeps a row only when
`_row_matches_lot` says the lot token is exactly the requested token, or
the stored value is exactly the requested URI. The 413 fires when exact
matches exceed 50,000.

### Lot identity

`LOT_IDENTITY_LOSSLESS` defaults off (`services/shared/epcis_lot_identity.py`).
Off, canonical writes keep the bare lot token. On, they store the full
LGTIN or GS1 Digital Link, which changes the event hash and the
idempotency key. Leave it off until a dual-key path exists.

The export filter reads both shapes either way. A bare `lot_code` also
matches a stored class URI whose decoded lot token is that exact token. A
full class URI also matches a historical bare-token row. A URI that failed
the class parse is not treated as a lot token.

### Which KDEs are read

`_query_tenant_events` left-joins `fsma.cte_kdes` through a
`tenant_kdes` CTE scoped to the tenant. Every join also requires
`alias.tenant_id = e.tenant_id`.

| `kde_key` | Row alias | Where it is written |
| --- | --- | --- |
| `ship_from_location` | `ship_from` | FDA CSV `Ship_From_Location`, else `location_name` |
| `ship_from_gln` | `ship_from_gln` | FDA CSV only. The JSON-LD read point uses the `location_gln` column. |
| `ship_to_location` | `ship_to` | FDA CSV |
| `ship_to_gln` | `ship_to_gln` | FDA CSV |
| `carrier_name` | `carrier` | FDA CSV |
| `temperature_celsius` | `temperature_c` | FDA CSV |
| `gtin` | `gtin` | JSON-LD class URI, after `product_id` when `gtin` is empty |
| `product_id` | `product_id` | Class URI, or an SGTIN instance URN |
| `epc_class` | `epc_class` | Class URI when it already passes `_valid_class_uri` |
| `epcis_document_json` | `epcis_document_json` | Class URI and transformation inputs, from quantity lists |
| `reference_document` | `reference_document` | Selected only. Not in the JSON-LD event or the FDA CSV. |
| `tlc_source_reference` | `tlc_source_reference` | Selected only |
| `immediate_previous_source` | `immediate_previous_source` | Selected only. Not the transformation input. |
| `field_id` | `field_id` | Selected only |
| `harvester_name` | `harvester_name` | Selected only |
| `harvester_business_name` | `harvester_business_name` | Selected only |
| `harvester_business_phone` | `harvester_business_phone` | Selected only |

The last seven aliases are the Phase B join (`#3721`). A later format can
read them from the row. This builder does not emit them.

### What becomes an EPCIS event

Rows are newest first. A row is skipped, counted under
`regengine:exportMetadata.skippedEventsByReason`, and up to 50 skips are
copied to `skippedEvents` (`reason`, `eventType`, `eventId`, `tlc`).

| Reason | When |
| --- | --- |
| `missing_timestamp` | `event_timestamp` is empty |
| `invalid_timestamp` | A string timestamp is not ISO 8601 |
| `unsupported_epcis_event_type` | `epcis_event_type` is set and is not `ObjectEvent` or `TransformationEvent` |
| `unsupported_action` | `epcis_action` is set and is not `ADD`, `OBSERVE`, or `DELETE` |
| `missing_epc_class` | No valid class URI and no valid SGTIN instance URN |

`epcis_event_type` null is allowed and becomes an ObjectEvent, unless
`event_type` is `transformation`. A null action is written as `OBSERVE`.

The class URI is the first valid value among `epc_class`, `product_id`,
`traceability_lot_code`, and `epcClass` inside `quantityList`,
`outputQuantityList`, or `inputQuantityList` of `epcis_document_json`. A
valid LGTIN has a company prefix plus item reference of 13 digits and is
not the placeholder `0000000.000000`. A valid Digital Link is
`https://id.gs1.org/01/{GTIN-14}/10/{lot}` with a GS1 check digit. If none
of those is present, a GTIN with a valid check digit plus a bare lot token
is rebuilt as that Digital Link. A full class URI is never passed through
as the lot segment of a second URI. GTIN digits are not split into an EPC
URN company prefix. A lot with no GTIN and no stored class URI is skipped.

`product_id` is an instance EPC only when it is
`urn:epc:id:sgtin:{company}.{item}.{serial}` with the same 13-digit rule
and a company prefix other than `0000000`. Object events with an instance
EPC and no class use `epcList`. Otherwise they use `quantityList`.

`eventTime` is the stored timestamp's ISO form. `eventTimeZoneOffset`
comes from that timestamp's zone, or `+00:00` when the stored value has
none. `readPoint.id` is set only from `location_gln`: an SGLN URN, a
dotted SGLN, or a 13-digit GLN with a valid check digit (emitted as
`https://id.gs1.org/414/{gln}`). Placeholder GLNs that contain
`0000000000000` or `0000000.00000` are omitted.

`bizStep` prefers `epcis_biz_step` when that term is in the CBV set this
module allows. Otherwise it uses the CTE map: receiving and first land
based receiving → `receiving`, shipping → `shipping`, transformation →
`commissioning`, initial packing → `packing`, harvesting →
`creating_class_instance`, cooling → `storing`. An ObjectEvent with no
mapped term omits `bizStep`. A transformation with no mapped term still
writes `commissioning`.

Quantity is copied when present. A unit that is already 2–3 uppercase
letters or digits is `uom`. Names such as `cases`, `lbs`, and `kg` map to
UN/CEFACT (`CS`, `LBR`, `KGM`). Anything else is omitted from `uom` and
copied to `regengine:unitOfMeasure`.

A transformation writes `outputQuantityList` or `outputEPCList`, and
`inputQuantityList` only when `epcis_document_json` already holds a valid
input class. `transformationID` is `urn:sha256:{sha256_hash}` when the row
has a hash. The hash is also `regengine:sha256` on every emitted event.

### Experimental FDA CSV

`POST /api/v1/export/fda` uses the same query, tenant rule, 503, and 413.
It does not skip rows that lack an EPC class. The header is:

```text
CTE_Type,Traceability_Lot_Code,Product_Description,Quantity,Unit_of_Measure,Event_Date,Event_Time,Ship_From_Location,Ship_From_GLN,Ship_To_Location,Ship_To_GLN,Carrier,Temperature_C,SHA256_Hash
```

`Event_Time` is `strftime("%H:%M:%SZ")` on the stored datetime. The route
does not convert that clock to UTC before appending `Z`. A value stored at
`-07:00` keeps that hour and minute and gains a `Z`. A non-datetime
timestamp is not parsed here (the JSON-LD route does parse ISO strings).
The release-enabled spreadsheet
(`services/compliance/app/fsma_spreadsheet.py`) is the path that keeps
`kdes.event_time` and its zone. This preview CSV does not.

`Ship_From_GLN` prefers the `ship_from_gln` KDE, then the `location_gln`
column. Description, location, and carrier cells are passed through
`sanitize_cell`, and commas in those cells become semicolons.

## Graph export: `GET /api/v1/fsma/compliance/export/epcis`

`services/graph/app/routers/fsma/compliance.py`, mounted with the `graph`
router at `/api/v1`. Experimental. Local `docker-compose.dev.yml` does not
start Neo4j.

`start_date` and `end_date` are required. `format` is `json-ld` (default)
or `xml`. The route is limited to 10 requests per minute. Tenant scope is
the API key, reconciled with the request tenant before the read.

The handler asks Neo4j for `EXPORT_EVENT_CAP + 1` events (50,000). Over
that is HTTP 413 and no file. A bare TLC is not turned into an SGTIN URN.
When the lot and a GTIN are both present, the event uses a GS1 Digital
Link class in `quantityList`. Harvesting maps to `creating_class_instance`.

## Tests

```bash
python3 -m pytest services/ingestion/tests/test_epcis_export_1342.py \
  services/ingestion/tests/test_epcis_export_kde_joins.py \
  services/ingestion/tests/test_epcis_export_gs1_2.py -q --no-cov
python3 -m pytest services/graph/tests/test_epcis_export_gs1_2.py \
  services/graph/tests/test_fda_request_export_cap.py -q --no-cov
```
