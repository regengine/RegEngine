# Jev header-mapping suggestions on CSV ingestion

Decision record: `docs/architecture/decisions/ADR-005-jev-header-mapping-suggestions.md`.

## What Jev is

Jev is TypeSafe AI's "System One" model. It does not generate text. One
request carries *state* (a string, JSON object or array) and named, typed
*questions*; the response carries one typed answer per question:

| Question | Answer |
| --- | --- |
| `Choice` (pick one of up to 255 options) | `choice`, `probabilities` over the options, `confidence` in `[0, 1]` |
| `Score` (rate against 2-10 ordered levels) | `score`, `probabilities`, `confidence`, `legend` |
| `Noul` (yes/no) | `noul`: probability of yes |

All questions in a request are evaluated in parallel against the same state.
RegEngine uses one `Choice` per unrecognised CSV column.

Vendor references: [docs](https://docs.typesafe.ai/llms.txt),
[API](https://docs.typesafe.ai/api.md),
[Python SDK](https://docs.typesafe.ai/sdk/python.md),
[known limitations of Jev 1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13.md).
The vendor's agent skill is vendored at `.claude/skills/typesafe-ai/SKILL.md`
for coding-agent sessions.

## Where it runs

| Piece | Path |
| --- | --- |
| SDK wrapper: settings, fail-open client, evidence, confidence bands | `services/shared/jev/settings.py`, `services/shared/jev/client.py`, `services/shared/jev/routing.py` |
| Question set, vocabulary, apply policy, artifact builder | `services/shared/jev/header_mapping.py` |
| Integration point | `services/ingestion/app/csv_templates.py` (`_suggest_header_mappings_for_upload`, `_record_header_mapping_evidence`, `parse_csv_rows(header_mapping=...)`) |
| Response fields | `services/ingestion/app/webhook_models.py` (`HeaderMappingSuggestionResult`, `HeaderMappingEngineResult`) |
| Operator preview CLI | `scripts/jev_header_preview.py` (see [Preview suggestions on your own files](#preview-suggestions-on-your-own-files)) |
| Tests | `services/shared/tests/test_jev_client.py`, `services/shared/tests/test_jev_header_mapping.py`, `services/ingestion/tests/test_csv_jev_header_mapping.py`, `services/ingestion/tests/test_jev_header_preview_script.py` |

Only `POST /api/v1/ingest/csv` calls Jev. The inbound-email CSV path shares
`parse_csv_rows` but passes no mapping, so it is unchanged.

## Request flow

1. The route reads the header row. Headers the parser recognises
   (`_RECOGNIZED_COLUMNS` in `csv_templates.py`: every column
   `parse_csv_rows`, the templates, the required-KDE table and the canonical
   normalizer read by name) are skipped. Blank and duplicate headers are
   skipped. If nothing is left, no request is made.
2. One request goes to `https://api.typesafe.ai/v1/systemone` (or
   `TYPESAFE_BASE_URL`) with state
   `{"csv_headers": [...], "columns_to_map": [{"index", "header", "sample_values"?}]}`
   and one `Choice` question per column over the canonical vocabulary plus
   `no_match`. The call runs in a worker thread so the event loop is not
   blocked. At most 48 columns are asked about per upload.
3. Each answer is banded by confidence and passed through the apply policy
   below. Rows are then parsed exactly as before, with any applied mapping
   copied under the canonical key (source column left in place).
4. After `ingest_events` returns, every actionable suggestion is queued as a
   `field_mapping_suggestion` agent artifact
   (`shared.agent_task_bridge.enqueue_agent_artifact_task`). The bridge
   persists it to `fsma.agent_artifacts` and appends a receipt to the
   ingestion run's ledger. The artifact carries `model_name`
   (`typesafe/<model>`), `agent_version` (the question-set version), the
   vendor request id, the top probabilities and thresholds in its rationale,
   and whether code applied it.
5. The response gains `header_mapping_suggestions` (one entry per asked
   column) and `header_mapping_engine` (status, model, request id,
   thresholds, artifacts queued). Both are null/empty when Jev is not
   configured, so existing clients see no change.

## Apply policy (single source: `services/shared/jev/header_mapping.py`)

| Band | Condition | What code does |
| --- | --- | --- |
| `auto_apply` | `confidence >= REGENGINE_JEV_AUTO_APPLY_CONFIDENCE` (0.90) | Artifact queued. Applied to rows **only if** all of: `REGENGINE_JEV_APPLY_HEADER_MAPPINGS=1`; `confidence >= 0.85` (agent-artifact human-review threshold); target column not already in the file; no column the parser reads *after* the target is in the file either (`tlc` for `traceability_lot_code`, `qty` for `quantity`, any later date column for `event_date`, ...: a mapped column must never outrank a value the file carries); no other column in the same band names the same target. |
| `review` | `REGENGINE_JEV_REVIEW_CONFIDENCE` (0.50) `<= confidence <` auto-apply | Artifact queued with `requires_human_review=true`. Never applied. |
| `reject` | below the review bound | Returned on the response only. No artifact, never applied. |
| `no_match` | the model picked the no-match option | Returned on the response only. |

`blocked_reason` on each suggestion names which condition stopped an apply:
`apply_disabled`, `below_auto_apply_threshold`, `below_human_review_threshold`,
`target_present`, `shadows_existing_column`, `conflict`, `no_match`. The
parser's fallback chains (`_COLUMN_PRECEDENCE` in
`services/ingestion/app/csv_templates.py`) are the single source for
`shadows_existing_column`; the artifact rationale names the column that
would have been outranked. `parse_csv_rows` applies the same rule per row:
a mapped value is copied only when the row has neither the canonical key
nor a later column in its chain filled in.

Applied mappings are also written to the application log as
`csv_header_mappings_applied` (column names only).

## What leaves the process

- Always (when configured): the CSV header row.
- Only with `REGENGINE_JEV_HEADER_SAMPLE_VALUES` set to 1-5: that many
  distinct cell values per unrecognised column from the first 50 rows,
  passed through `shared.pii.redact_pii` (SSN, phone, email, street
  address patterns) and truncated to 64 characters.
- Never: whole rows, files, tenant ids, or recognised columns.

The SDK logger (`typesafe_sdk`) prints request bodies at `DEBUG`. The
wrapper caps it at `INFO` unless `TYPESAFE_LOG_LEVEL` is set explicitly. Do
not set `TYPESAFE_LOG_LEVEL=debug` on a deployed environment.

Vendor terms as published: services hosted in the United States; the
privacy policy states inputs are not used to train or fine-tune models; a
DPA is offered at https://typesafe.ai/legal/data-processing and a
zero-data-retention option is available on request. TypeSafe AI is listed as
a where-configured subprocessor in `frontend/src/lib/trust-subprocessors.ts`.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | unset | Enables the integration. Unset = disabled. |
| `TYPESAFE_DEFAULT_MODEL` | `jev-1.13.0` | Model name. RegEngine pins a version; `jev-latest` floats. |
| `TYPESAFE_BASE_URL` | vendor default | API root override (gateway, proxy). |
| `REGENGINE_JEV_ENABLED` | `1` | Kill switch; `0` disables even with a key. |
| `REGENGINE_JEV_TIMEOUT_SECONDS` | `5` | Per HTTP attempt. |
| `REGENGINE_JEV_MAX_RETRIES` | `1` | Retries after the first attempt (429, 5xx, timeouts, connection errors). |
| `REGENGINE_JEV_AUTO_APPLY_CONFIDENCE` | `0.90` | Lower bound of the `auto_apply` band. |
| `REGENGINE_JEV_REVIEW_CONFIDENCE` | `0.50` | Lower bound of the `review` band. |
| `REGENGINE_JEV_APPLY_HEADER_MAPPINGS` | `0` | `1` lets `auto_apply`-band answers change rows. |
| `REGENGINE_JEV_HEADER_SAMPLE_VALUES` | `0` | 0-5 redacted sample values per unrecognised column. |

Invalid values fall back to the default with a `jev.settings.*` warning; the
request path never fails on configuration.

## Preview suggestions on your own files

`scripts/jev_header_preview.py` runs the route's own suggestion step
(`_suggest_header_mappings_for_upload`) on a local CSV. It needs no running
service, database or tenant, and it ingests, persists and queues nothing. It
reads the variables in [Configuration](#configuration) and sends what the
route sends: the header row, redacted sample values only if asked, never
rows. Run it from the repo root in the Python environment used for the
ingestion tests, because it imports `services/ingestion`. Without one, create
it from the root lock file (the same install CI uses):

```bash
python3.11 -m venv .venv
.venv/bin/pip install --require-hashes -r requirements.lock
.venv/bin/python3 scripts/jev_header_preview.py path/to/supplier.csv --prompt-key
```

With the environment active, the short form is:

```bash
python3 scripts/jev_header_preview.py path/to/supplier.csv
```

```text
column   suggested_field        confidence  band        would_apply  blocked_reason
-------  ---------------------  ----------  ----------  -----------  --------------------------
Lot #    traceability_lot_code  0.970       auto_apply  no           apply_disabled
Ship Dt  ship_date              0.710       review      no           below_auto_apply_threshold
Notes    (no match)             0.980       auto_apply  no           no_match
```

Above the table it prints the status, model, request id, latency and the
thresholds in force. The values shown are illustrative.

| Flag | Effect |
| --- | --- |
| `--json` | Machine-readable report on stdout. Logs go to stderr. |
| `--sample-values N` | Send N (0-5) redacted sample values per unrecognised column. Overrides `REGENGINE_JEV_HEADER_SAMPLE_VALUES`. |
| `--simulate-apply` | Compute `would_apply` as if `REGENGINE_JEV_APPLY_HEADER_MAPPINGS=1`. Nothing else changes. |
| `--prompt-key` | Read the key from a hidden terminal prompt (or from stdin when there is no terminal), for this run only, instead of `TYPESAFE_API_KEY`. The script never prints, logs or saves it. |

### Demo file

`docs/engineering/examples/jev_demo_shipping.csv` is a synthetic shipping
file (fictional companies marked "(demo)", lot codes `DEMO-JEV-*`). It
carries every column the parser needs, so it is valid on its own, plus seven
extra headers the parser does not recognise. Those seven are what Jev is
asked about; the intended answers are:

| Header | Intended field |
| --- | --- |
| `Lot #` | `traceability_lot_code` |
| `Item Desc` | `product_description` |
| `Qty Shpd` | `quantity` |
| `Ship Dt` | `ship_date` |
| `Ship-To GLN` | `ship_to_gln` |
| `Trucking Co` | `carrier` |
| `Internal Notes` | `no_match` |

```bash
python3 scripts/jev_header_preview.py docs/engineering/examples/jev_demo_shipping.csv --prompt-key
```

With `--simulate-apply` and answers in the `auto_apply` band, the four
headers whose canonical column is already in the file (`Lot #`, `Item Desc`,
`Qty Shpd`, `Ship Dt`) stay blocked with `target_present`, and `Ship-To GLN`
and `Trucking Co` show `would_apply: yes`, since the file has no
`ship_to_gln` or `carrier` column. `Internal Notes` is never applied.

Exit codes: `0` suggestions received, or no unrecognised headers (no request
made); `1` bad usage, an unreadable, oversized (over 5 MB) or non-UTF-8
file (stdout stays empty, the message goes to stderr), or an unexpected error
(status `error`, for example a malformed `TYPESAFE_BASE_URL`); `2` not configured (`TYPESAFE_API_KEY` unset) or switched off
(`REGENGINE_JEV_ENABLED=0`); `3` vendor unavailable. For `2` and `3` the
status (for example `unavailable:auth`) and a one-line hint go to stderr.

Keep the key out of shell history and tracked files. Use `--prompt-key`, or
enter it silently for the current shell with
`read -rs TYPESAFE_API_KEY && export TYPESAFE_API_KEY`. Keep the stored copy
in a password manager or the environment's secret variables, not in the
repository. (`.env` is excluded from commits but is still plaintext on disk.)

## Rollout

1. Set `TYPESAFE_API_KEY` on staging. Upload representative supplier files.
   Suggestions appear on the response and in Agent Reviews (filter: Field
   mapping). Nothing changes in the rows.
2. Compare suggestions against the intended mappings. To check a file before
   (or without) uploading it, run the
   [preview](#preview-suggestions-on-your-own-files) on it; add
   `--simulate-apply` to see what apply mode would change. If `auto_apply`-band
   answers are wrong for your data, raise
   `REGENGINE_JEV_AUTO_APPLY_CONFIDENCE`; if good answers sit in `review`,
   consider lowering it (never below 0.85: the artifact contract still forces
   review below that, and the apply policy refuses).
3. Turn on `REGENGINE_JEV_APPLY_HEADER_MAPPINGS=1`. Applied mappings show
   `applied: true` on the response, `csv_header_mappings_applied` in the
   log, and `requires_human_review=false` artifacts on the run ledger.
4. Roll back at any time with `REGENGINE_JEV_APPLY_HEADER_MAPPINGS=0`
   (suggestions continue) or `REGENGINE_JEV_ENABLED=0` (no calls).

## Failure modes

`header_mapping_engine.status` on the response says what happened:

| Status | Meaning |
| --- | --- |
| `ok` | Answers received and recorded. |
| `no_unrecognized_headers` | Every column was already known; no request made. |
| `unavailable:disabled` | Kill switch or no key (engine field is null in this case). |
| `unavailable:auth` | 401/403 from the vendor: check the key. |
| `unavailable:rate_limited` | 429 after retries. |
| `unavailable:timeout`, `unavailable:connection` | Network; upload proceeds unmapped. |
| `unavailable:server_error`, `unavailable:invalid_response` | Vendor-side; upload proceeds unmapped. |
| `error` | Unexpected exception in RegEngine code; see `csv_header_mapping_failed` in the log. |

In every non-`ok` case the upload is processed exactly as without Jev. A
failure to queue evidence after a successful call is logged as
`csv_header_mapping_evidence_failed` with the upload hash and run id and
reports `artifacts_recorded: 0`; it does not reject the upload.

## Known limitations

- Jev reads instructions literally, does no arithmetic and no date
  comparison. The question set therefore asks only which field a column is,
  never what a value means.
- English-first; non-English headers get lower accuracy.
- 48 unrecognised columns per upload; more are ignored and counted in the
  log (`truncated_columns`).
- Thresholds are the vendor's published starting points and have not been
  validated on RegEngine data yet; that is step 2 of the rollout.

## Verification

```bash
python3 -m pytest services/shared/tests/test_jev_client.py services/shared/tests/test_jev_header_mapping.py -q --no-cov
python3 -m pytest services/ingestion/tests/test_csv_jev_header_mapping.py services/ingestion/tests/test_jev_header_preview_script.py -q --no-cov
```

All tests run offline against `httpx2.MockTransport`; no test contacts the
vendor.
