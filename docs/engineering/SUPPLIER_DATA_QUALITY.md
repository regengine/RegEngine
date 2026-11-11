# Supplier data quality and gap time to fix

The suppliers dashboard (`/dashboard/suppliers`) shows two readouts for
the facilities the signed-in supplier user owns. Both routes live on
the admin supplier router (`services/admin/app/supplier_compliance_routes.py`),
mounted at `/v1` on the consolidated app. `admin` is on the production
router allowlist.

A supplier here is one `supplier_facilities` row. `supplier_key` is that
row's id. The caller must have a tenant context. A missing tenant is
HTTP 400 `Tenant context required`. Another user's facility is not in
the summary. The records route returns HTTP 404 for a facility the
caller does not own, and HTTP 400 for an id that is not a UUID.

## Data quality

`GET /v1/supplier/data-quality?window_days=30`

`window_days` defaults to 30 and must be from 1 to 365. The window
opens at `now` minus that many days. The response repeats
`window_days`, `min_records` (20), `late_cte_label`, and
`evaluated_at`, then one entry per owned facility.

Four metrics stay separate. There is no combined score. A share is
present only when the denominator is at least 20. Below that,
`status` is `not_enough_data`, `share` is null, and the numerator and
denominator are still returned.

| `key` | What the share counts | Drilldown |
| --- | --- | --- |
| `missing_kde` | CTE records (`supplier_cte_events`) received in the window that lack a required KDE in `kde_data` | yes |
| `unlinked_lot` | Lot codes active in the window that do not link upstream | yes |
| `late_cte` | Records received (`created_at`) more than the facility's agreed sending hours after `event_time` | yes |
| `epcis_failed` | EPCIS documents received in the window whose latest receipt is `rejected` | no |

`missing_kde` uses the webhook required-KDE table, minus the fields a
supplier record already stores as columns: the lot code, the event
time, and the recording facility's own location. The denominator is
every CTE record received in the window. An unknown CTE type has an
empty required list, so that record stays in the denominator and adds
nothing to the numerator.

`unlinked_lot` uses one denominator per distinct lot, not per record.

A lot counts as linked when it is the output of
`fsma.transformation_links`, when one of the caller's records for it
carries a linkage KDE (`tlc_source_reference`, `tlc_source_gln`,
`immediate_previous_source`, `input_lot_codes`,
`input_traceability_lot_codes`, `input_tlcs`,
`harvester_business_name`), or when the chain starts at that facility
(`harvesting`, or `first_receiver` including the
`first_land_based_receiving` alias). Linkage looks at all of the
caller's records for the lot, including records older than the window.
A lot is active only when the caller sent a record for it in the
window. Another supplier's record does not activate it.

`late_cte` is the product's measure against the agreed sending time.
The response label says it is not a regulatory requirement. The
denominator is records in the window that have both `event_time` and
`created_at`. A record is late when `created_at - event_time` is
greater than the agreed hours. With no agreed hours, status is
`not_enough_data`, the counts are null, and `reason` says the sending
time is unset.

`epcis_failed` is the tenant's count, repeated on every facility.
An EPCIS upload has no facility. Retries of the same request body count
once: the metric uses the latest receipt per document SHA-256 in
`fsma.epcis_document_receipts`. `reason` says the count is account-wide.
When that table cannot be read, status is `unavailable` and the other
metrics still return. Writing a receipt during ingest is fail-open and
does not change the ingest response.

### Records behind a metric

```bash
curl "$BASE/v1/supplier/data-quality/$FACILITY_ID/records?metric=missing_kde&window_days=30&limit=50&offset=0" \
  -H "Cookie: __Host-regengine_session=$SESSION"
```

`metric` is `missing_kde`, `unlinked_lot`, or `late_cte`. `limit`
defaults to 50, maximum 200. `offset` defaults to 0. `total` is the
full flagged set; `items` is the page. `late_cte` for a facility with
no agreed hours is HTTP 409 `No agreed sending time is set for this
facility`.

`missing_kde` items include `record_id`, `lot_code`, `cte_type`, and
`missing_kdes`. `late_cte` items include `event_time` and `received_at`.
`unlinked_lot` items include `lot_id` and `lot_code`.

The dashboard loads this from
`frontend/src/app/dashboard/suppliers/data-quality.tsx` in pages of 25.

### Agreed sending hours

`PUT /v1/supplier/admin/facilities/{facility_id}/agreed-sending-hours`

Body: `{ "agreed_sending_hours": 24 }` or `{ "agreed_sending_hours": null }`
to clear it. The value is a strict integer greater than 0, up to the
Postgres integer maximum. A string, float, or boolean is HTTP 422.

The caller must be an Owner or Admin of the bound tenant
(`tenant.admin`). Anyone else is HTTP 403. A missing tenant context is
HTTP 403 `E_NO_TENANT_CONTEXT`. A facility outside the tenant is HTTP
404. The supplier data-quality view can read the value and cannot
change it. The dashboard labels it as set by the customer.

## Gap time to fix

`GET /v1/supplier/gap-time-to-fix`

One row per owned facility:

| Field | Meaning |
| --- | --- |
| `open_gap_count` | Open rows in `public.data_gap_events` for that facility |
| `median_time_to_fix_seconds` | Median of `closed_at - opened_at` for closed gaps. Null when nothing has been fixed. |
| `oldest_open_gap_opened_at` | Earliest `opened_at` still open |
| `past_internal_target` | True when any open gap has been open for more than 24 hours |
| `at_risk` / `at_risk_gap_count` | Gaps whose lot is on an unanswered request case and that are still open at that case's `response_due_at` |
| `has_data` | True when the facility has an open gap or a closed one |
| `internal_target_seconds` | 86400. This target is internal. It is not the FDA response deadline. |

`at_risk` joins `fsma.request_cases` on the lot. A case counts while
`package_status` is outside `submitted` and `amended`. A gap counts
when it opened at or before `response_due_at` and had not closed by
then.

### How a gap opens and closes

`services/shared/data_gap_tracking.py` records two kinds:
`missing_kde` (one gap per missing KDE name) and
`cte_validation_failed` (keyed on the rule id). A failed record opens
gaps and leaves existing gaps open. A record that passes validation
closes every open gap for that lot and CTE.

A close stores `closing_record_id` and `closing_record_hash`. The hash
must be a lowercase SHA-256 hex digest of the persisted record. A pass
without that receipt does not close the gap.

The writer runs after the ingest transaction commits. It catches its
own errors, logs them, and returns. A gap-log failure does not roll
back an accepted event. An open insert is idempotent on the partial
unique index of open rows. A lot with no supplier facility is stored
under `supplier_key` `unassigned`. That key is not a facility id, so
the per-facility summary does not list it.

The dashboard panel is
`frontend/src/app/dashboard/suppliers/gap-time-to-fix.tsx`.

## Tests

```bash
python3 -m pytest services/admin/tests/test_supplier_data_quality_routes.py -q --no-cov
python3 -m pytest services/shared/tests/test_supplier_data_quality.py \
  services/shared/tests/test_data_gap_tracking.py \
  services/shared/tests/test_epcis_receipts.py -q --no-cov
cd frontend && npm run test:run -- src/__tests__/components/supplier-data-quality.test.tsx \
  src/__tests__/components/gap-time-to-fix.test.tsx
```
