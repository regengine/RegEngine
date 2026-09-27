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
| Tests | `services/shared/tests/test_jev_client.py`, `services/shared/tests/test_jev_header_mapping.py`, `services/ingestion/tests/test_csv_jev_header_mapping.py` |

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
| `auto_apply` | `confidence >= REGENGINE_JEV_AUTO_APPLY_CONFIDENCE` (0.90) | Artifact queued. Applied to rows **only if** all of: `REGENGINE_JEV_APPLY_HEADER_MAPPINGS=1`; `confidence >= 0.85` (agent-artifact human-review threshold); target column not already in the file; no other column in the same band names the same target. |
| `review` | `REGENGINE_JEV_REVIEW_CONFIDENCE` (0.50) `<= confidence <` auto-apply | Artifact queued with `requires_human_review=true`. Never applied. |
| `reject` | below the review bound | Returned on the response only. No artifact, never applied. |
| `no_match` | the model picked the no-match option | Returned on the response only. |

`blocked_reason` on each suggestion names which condition stopped an apply:
`apply_disabled`, `below_auto_apply_threshold`, `below_human_review_threshold`,
`target_present`, `conflict`, `no_match`.

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

## Rollout

1. Set `TYPESAFE_API_KEY` on staging. Upload representative supplier files.
   Suggestions appear on the response and in Agent Reviews (filter: Field
   mapping). Nothing changes in the rows.
2. Compare suggestions against the intended mappings. If `auto_apply`-band
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
python3 -m pytest services/ingestion/tests/test_csv_jev_header_mapping.py -q --no-cov
```

All tests run offline against `httpx2.MockTransport`; no test contacts the
vendor.
