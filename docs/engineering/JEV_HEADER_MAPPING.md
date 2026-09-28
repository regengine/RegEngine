# Jev header-mapping suggestions on CSV ingestion

Decision record: `docs/architecture/decisions/ADR-005-jev-header-mapping-suggestions.md`.

Jev answers two questions about a CSV upload, both from its header row:

1. Which canonical FSMA 204 field is each unrecognised column? (header
   mapping, most of this document)
2. For a file that declares no CTE, which critical tracking event do its
   rows record? ([File CTE suggestion](#file-cte-suggestion-uploads-that-declare-no-cte))

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
| Question set, vocabulary, apply policy, artifact builder | `services/shared/jev/header_mapping.py` (header mapping), `services/shared/jev/cte_classification.py` (file CTE) |
| Integration point | `services/ingestion/app/csv_templates.py` (`_suggest_header_mappings_for_upload`, `_record_header_mapping_evidence`, `parse_csv_rows(header_mapping=...)`; `_suggest_file_cte_for_upload`, `_record_file_cte_evidence`) |
| Response fields | `services/ingestion/app/webhook_models.py` (`HeaderMappingSuggestionResult`, `HeaderMappingEngineResult`, `CteTypeSuggestionResult`) |
| Upload UI ("Import as <CTE>") | `frontend/src/lib/cte-suggestion.ts`, `frontend/src/components/fsma/CteSuggestionPrompt.tsx`, used by `/ingest` and the Data Import Hub |
| Startup log | `server/main.py`: `jev_configured enabled=... key_present=... apply_header_mappings=... apply_file_cte_type=...` (never the key) |
| Operator preview CLI | `scripts/jev_header_preview.py` (see [Preview suggestions on your own files](#preview-suggestions-on-your-own-files)) |
| Evaluation on labelled data | `scripts/jev_eval.py` with `docs/engineering/examples/jev_eval_cases.json` (see [Measure Jev on RegEngine data](#measure-jev-on-regengine-data)) |
| Tests | `services/shared/tests/test_jev_client.py`, `services/shared/tests/test_jev_header_mapping.py`, `services/shared/tests/test_jev_cte_classification.py`, `services/ingestion/tests/test_csv_jev_header_mapping.py`, `services/ingestion/tests/test_csv_jev_file_cte.py`, `services/ingestion/tests/test_jev_header_preview_script.py`, `frontend/src/__tests__/lib/cte-suggestion.test.ts` |

Only `POST /api/v1/ingest/csv` calls Jev. The inbound-email path
(`services/ingestion/app/email_ingest/service.py`) calls the same route
function (`ingest_csv`) for each CSV attachment with no `cte_type`, so its
attachments get both questions and the same apply switches.

## Request flow

1. The route reads the header row. If it is malformed (it spans more than
   one physical line, a header contains a line break, or a header is longer
   than 128 characters after stripping), nothing is sent, not even the
   header row, and the status is `malformed_header`; see
   [Failure modes](#failure-modes). An unterminated quote is the usual
   cause: the reader then takes the rest of the file as one "header", so
   sending it would send whole rows. Headers the parser recognises
   (`_RECOGNIZED_COLUMNS` in `csv_templates.py`: every column
   `parse_csv_rows`, the templates, the required-KDE table and the canonical
   normalizer read by name) are skipped. Blank and duplicate headers are
   skipped. If nothing is left, no request is made.
2. One request goes to `https://api.typesafe.ai/v1/systemone` (or
   `TYPESAFE_BASE_URL`) with state
   `{"csv_headers": [...], "columns_to_map": [{"index", "header", "sample_values"?}], "file_cte_type"?}`
   and one `Choice` question per column over the canonical vocabulary plus
   `no_match`. `file_cte_type` is present only when the upload passes the
   `cte_type` form field **and** no row can contradict it (see
   [Declare the CTE on single-type uploads](#declare-the-cte-on-single-type-uploads)):
   it carries the canonical CTE the route normalised it to (`Shipping` and
   `ship` both become `shipping`). Otherwise the key is absent, not null,
   so the state is exactly what it was before the key existed.
   Reading the upload for the request (header row, sample values, the CTE
   value scan below) and the call itself both run in the threadpool
   (`_read_upload_for_jev`, then `suggest_header_mappings`), so the event
   loop is not blocked. At most 48 columns are asked about per upload.
3. Each answer is banded by confidence and passed through the apply policy
   below. Rows are then parsed exactly as before, with any applied mapping
   copied under the canonical key (source column left in place).
4. After `ingest_events` returns, every actionable suggestion is queued as a
   `field_mapping_suggestion` agent artifact
   (`shared.agent_task_bridge.enqueue_agent_artifact_task`). The bridge
   persists it to `fsma.agent_artifacts` and appends a receipt to the
   ingestion run's ledger. The artifact carries `model_name`
   (`typesafe/<model>`), `agent_version` (the question-set version), the
   vendor request id, and in its rationale the question-set version, what
   the state said about the file's CTE (`State file_cte_type: shipping.`, or
   `none` with the reason), the top probabilities and thresholds, and
   whether code applied it. The CTE note is in the rationale text rather
   than a field of its own because the artifact and payload contracts are
   closed (`extra="forbid"`, `data-schemas/events/agent.artifact.schema.json`
   with `additionalProperties: false`) and the payload is copied into the
   hashed ledger receipt; a new field would change both.
5. The response gains `header_mapping_suggestions` (one entry per asked
   column) and `header_mapping_engine` (status, model, request id,
   thresholds, artifacts queued). Both are null/empty when Jev is not
   configured, so existing clients see no change. When no row parses, the
   400 detail carries the same `header_mapping_suggestions` list (only when
   there are suggestions), so the uploader learns which column to rename.
6. The upload pages (`/ingest`, Data Import Hub) list each unapplied
   suggestion that names a field and is not in the `reject` band:
   "“Lot #” looks like Traceability Lot Code (97% confidence). Rename the
   column to “Traceability Lot Code” and upload again." The labels live in
   `frontend/src/lib/column-suggestions.ts`; each normalises to the field
   name, so the renamed column parses. A test pins that the labels cover the
   vocabulary exactly. Nothing is applied from the page: renaming is the
   uploader's decision.

### Declare the CTE on single-type uploads

Jev reads headers literally. `Ship Dt` or `Qty Shpd` is easier to place
when it knows every row is a shipment. For a file that records one CTE,
pass the `cte_type` form field on `POST /api/v1/ingest/csv` (and
`--cte-type` in the [preview](#preview-suggestions-on-your-own-files)).
The route already uses it as the fallback CTE for rows; the same
normalised value is what Jev sees as `file_cte_type`. Leave it out for
mixed-type files.

**Precedence follows the parser.** The form field is only a fallback:
`_detect_row_cte_type` reads a row's own CTE first and uses the declared one
only when the row has none (blank, or not a known CTE). A row's own CTE can
come from two places, and `_file_cte_type_for_jev` (the one helper the route
and the preview share) withholds `file_cte_type` whenever either could
contradict the declared CTE:

| Source of a per-row CTE | Withheld when | Reason |
| --- | --- | --- |
| A per-row CTE column the parser reads: `cte_type`, `event_type`, `type` or `cte` after the parser's header normalisation (so `Event Type` and `CTE` count, `Event-Type` does not) | the header is present, whatever its values | `file has a per-row CTE column: Event Type` |
| An unrecognised column that Jev may map onto `cte_type` (`Activity`, `Event Kind`, `Event-Type`, `Transaction Type`, ...) | any non-empty value, normalised the way `_detect_row_cte_type` normalises values, resolves through `_CTE_TYPE_ALIASES` to a different CTE | `column Activity holds per-row CTE values` |

The value scan reads exactly the rows `parse_csv_rows` reads: the first
`MAX_CSV_ROWS` (500) rows the same `csv.DictReader` yields, where comment
rows and all-empty rows count and blank lines do not. A value in a row the
parser discards cannot become a row's CTE, so it never withholds. It skips
comment rows exactly as the parser does, ignores recognised columns (never
sent to Jev, so never mapped), normalises the header row once rather than
per cell, and stops at the first contradiction. It errs on withholding, which only costs Jev a hint: `_CTE_TYPE_ALIASES` maps
single letters (`S`, `R`, `H`, `C`, `P`, `T`), so a `Grade` column of `S`
and `R` withholds a declared `shipping`. A file whose rows cannot be read
withholds too.

The result is an invariant the tests pin: whenever `file_cte_type=X` is
sent, every row the parser produces has CTE `X`, with or without an
applied `cte_type` mapping. Values that agree with `X` (`shipping`, `S`,
`Ship`) or are not a CTE at all (`load dock 4`) keep it sent.

The rows always get the form field as their fallback, exactly as before.
The preview report and the artifact rationale say when a declared CTE was
withheld and why, and the route logs `csv_header_mapping_file_cte_withheld`.
An auto-apply `cte_type` mapping is applied exactly as it is without a
declared CTE. When a CTE was declared, its rationale adds that the declared
CTE remains the fallback for rows where the column is blank or not a known
CTE, and that per-row values from the column override it.

### Question-set version

`QUESTIONS_VERSION` in `services/shared/jev/header_mapping.py` is recorded
with every answer (`header_mapping_engine.questions_version`, the Jev
evidence) and as `agent_version` on every `field_mapping_suggestion`
artifact. Bump it whenever the question text, the vocabulary or the meaning
of a state key changes.

| Version | Change |
| --- | --- |
| `csv-header-mapping.v1` | Initial question set. |
| `csv-header-mapping.v2` | The task text adds: "When the state has `file_cte_type`, it names the FSMA 204 critical tracking event that every row in the file records." Asked on every upload, with or without `file_cte_type`. |

Nothing in RegEngine compares the version string: it is free text on the
response, the evidence and `fsma.agent_artifacts.agent_version`, so v1 and
v2 artifacts sit side by side and each says which question set produced it.

## Apply policy (single source: `services/shared/jev/header_mapping.py`)

| Band | Condition | What code does |
| --- | --- | --- |
| `auto_apply` | `confidence >= REGENGINE_JEV_AUTO_APPLY_CONFIDENCE` (0.90) | Artifact queued. Applied to rows **only if** all of: `REGENGINE_JEV_APPLY_HEADER_MAPPINGS=1`; `confidence >= 0.85` (agent-artifact human-review threshold); target column not already in the file; no column the parser reads *after* the target is in the file either (`tlc` for `traceability_lot_code`, `qty` for `quantity`, any later date column for `event_date`, ...: a mapped column must never outrank a value the file carries); no other column in the same band names the same target. A declared file CTE never blocks a `cte_type` mapping: rows keep the parser's precedence (their own CTE first, the declared one as fallback). |
| `review` | `REGENGINE_JEV_REVIEW_CONFIDENCE` (0.50) `<= confidence <` auto-apply | Artifact queued with `requires_human_review=true`. Never applied. |
| `reject` | below the review bound | Returned on the response only. No artifact, never applied. |
| `no_match` | the model picked the no-match option | Returned on the response only. |

`blocked_reason` on each suggestion names which condition stopped an apply:
`apply_disabled`, `below_auto_apply_threshold`, `below_human_review_threshold`,
`target_present`, `shadows_existing_column`, `conflict`, `no_match`. It is a
free string on the response (`HeaderMappingSuggestionResult`)
and appears in the artifact only inside the rationale text. The
parser's fallback chains (`_COLUMN_PRECEDENCE` in
`services/ingestion/app/csv_templates.py`) are the single source for
`shadows_existing_column`; the artifact rationale names the column that
would have been outranked. `parse_csv_rows` applies the same rule per row:
a mapped value is copied only when the row has neither the canonical key
nor a later column in its chain filled in.

Applied mappings are also written to the application log as
`csv_header_mappings_applied` (column names only).

## File CTE suggestion (uploads that declare no CTE)

**Why.** The upload UI (`/ingest`, the Data Import Hub) never sends the
`cte_type` form field, and RegEngine's own templates
(`GET /api/v1/templates/{cte_type}`) have no CTE column. So a filled-in
template uploaded from the UI has every row rejected with `No CTE type`:
all seven templates fail this way
(`test_every_template_without_a_declared_cte_is_rejected_today`). The same
holds for supplier exports that record one kind of event per file.

**When it is asked.** Once per upload, when the upload declares no
`cte_type` and no header is a column the parser reads a row's CTE from
(`cte_type`, `event_type`, `type`, `cte` after normalisation). With a
declared CTE nothing is asked and `cte_type_suggestion` is null. With a
per-row CTE column nothing is asked and the status is `per_row_cte_column`.
When the header mapping also asks (the file has unrecognised columns), the
two requests run concurrently, each with its own question set and version,
so the slower one bounds the added latency. Either way a request is
bounded by `REGENGINE_JEV_TIMEOUT_SECONDS` per attempt and
`REGENGINE_JEV_MAX_RETRIES`, and a failure never changes the outcome.

**The question** (`services/shared/jev/cte_classification.py`,
`csv-file-cte.v1`): one `Choice` over the seven FDA CTEs plus
`mixed_or_unclear`, each described with what it is, what it is not, and
typical headers. The state is `{"csv_headers": [...]}` plus
`sample_values` only when `REGENGINE_JEV_HEADER_SAMPLE_VALUES` is set (the
same redacted values the header mapping sends for unrecognised columns).
`growing` is never offered: it is not an FDA CTE.

**Policy.**

| Answer | What code does |
| --- | --- |
| One CTE, `auto_apply` band, `confidence >= 0.85`, `REGENGINE_JEV_APPLY_FILE_CTE_TYPE=1`, and no row names a different CTE | Used as the file's fallback CTE (`applied: true`). A row's own CTE still wins. Artifact recorded with `requires_human_review=false`; `csv_file_cte_applied` logged. |
| One CTE, any other case | Advisory: returned on the response and in the 400 body with `blocked_reason` (`apply_disabled`, `below_auto_apply_threshold`, `below_human_review_threshold`, `row_values_contradict`). Artifact recorded with `requires_human_review=true` unless the band is `reject`. |
| `mixed_or_unclear`, or a label outside the vocabulary | `cte_type: null`, `blocked_reason: mixed_or_unclear`. Nothing offered, no artifact. |

`row_values_contradict` reuses the scan that withholds a declared CTE from
the header mapping (`_file_cte_type_for_jev`): if any unrecognised column
holds a value that resolves through `_CTE_TYPE_ALIASES` to a different CTE
in the rows the parser reads, the answer is not applied. The reason on the
response is fixed; the column name is only logged
(`csv_file_cte_not_applied`).

**Where the uploader sees it.** When no row parses, the 400 detail
(`{"message": "No valid rows found", "errors": [...]}`) gains
`cte_type_suggestion` (`CteTypeSuggestionResult`: `status`, `cte_type`,
`confidence`, `band`, `applied`, `blocked_reason`, `model`, `request_id`,
`questions_version`, `apply_enabled`, `artifacts_recorded`). The upload
pages show "These rows look like Receiving events (97% confidence)" with an
**Import as Receiving** button that re-uploads the same file with
`cte_type=receiving`; the server then treats it as declared. Nothing is
imported until the click, and a re-upload that still fails offers nothing
again. A successful upload carries the same object as
`cte_type_suggestion` on the response.

**Evidence.** An actionable answer is queued as a
`field_mapping_suggestion` artifact after the run is retained:
`source_field: "csv_file"`, `source_value` the header row,
`target_canonical_field: "cte_type"`, `normalized_value` the CTE,
`agent_name: jev-csv-cte-classifier`, `agent_version: csv-file-cte.v1`. A
400 retains no run, so it records no artifact.

**Statuses** (`cte_type_suggestion.status`): `ok`, `per_row_cte_column`,
`no_headers`, `malformed_header` (nothing sent), `unavailable:<reason>`,
`no_answer`, `error`. In every non-`ok` case the upload is processed
exactly as without Jev.

## What leaves the process

- Always (when configured), for header mapping when a column is
  unrecognised and for the file CTE question when the upload declares no
  CTE: the CSV header row, but only a well-formed one:
  a single physical line, no line breaks inside a header, and no header
  over 128 characters after stripping (`MAX_HEADER_CHARS` in
  `services/shared/jev/header_mapping.py`; RegEngine's own longest column
  name is 25 characters). Otherwise nothing at all is sent
  (`malformed_header`), so row data can never leave as a "header".
- Only when the upload passes the `cte_type` form field and no row can
  contradict it: its canonical CTE name (for example `shipping`) as
  `file_cte_type`. Listed in the TypeSafe entry of
  `frontend/src/lib/trust-subprocessors.ts` (rendered on `/dpa` and `/trust`).
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
| `REGENGINE_JEV_APPLY_FILE_CTE_TYPE` | `0` | `1` lets an `auto_apply`-band file CTE become the fallback CTE of an upload that declares none. Independent of the header-mapping switch. |

Invalid values fall back to the default with a `jev.settings.*` warning; the
request path never fails on configuration.

To confirm a deployment picked up the key without reading the variable,
search its startup logs for `jev_configured`: `enabled=True
key_present=True` means the key is set and the kill switch is off.

## Preview suggestions on your own files

`scripts/jev_header_preview.py` runs the route's own suggestion step
(`_suggest_header_mappings_for_upload`) on a local CSV. It needs no running
service, database or tenant, and it ingests, persists and queues nothing. It
reads the variables in [Configuration](#configuration) and sends what the
route sends: the header row, the declared CTE name only with `--cte-type`
and only when no row can contradict it, redacted sample values only if
asked, never rows. Run it from the repo root in the Python environment used for the
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
| `--simulate-apply` | Compute `would_apply` as if `REGENGINE_JEV_APPLY_HEADER_MAPPINGS=1` (and, with `--file-cte`, `REGENGINE_JEV_APPLY_FILE_CTE_TYPE=1`). Nothing else changes. |
| `--file-cte` | Also ask the [file CTE question](#file-cte-suggestion-uploads-that-declare-no-cte) the route asks of an upload that declares no CTE, through the route's own helper (`_suggest_file_cte_for_upload`), concurrently with the header mapping. Adds a `File CTE:` line to the table and a `file_cte` section to `--json` (`status`, `cte_type`, `confidence`, `band`, `probabilities`, `would_apply`, `blocked_reason`, model, request id, latency, question-set version); without the flag the report is unchanged. The exit code is the more severe of the two questions'. Not with `--cte-type`: the route never asks when a CTE is declared. |
| `--prompt-key` | Read the key from a hidden terminal prompt (or from stdin when there is no terminal), for this run only, instead of `TYPESAFE_API_KEY`. The script never prints, logs or saves it. |
| `--cte-type CTE` | The CTE every row of the file records, as the route's `cte_type` form field: same accepted values and aliases (`_CTE_TYPE_ALIASES`), same normalisation, same withholding rule. An empty value (`--cte-type ""`) means not declared, like an empty form field; a blank-but-not-empty one is a usage error, as the route rejects it. When sent, it is shown on the `Sent:` line and as `request.file_cte_type` in `--json`. When withheld, `request.file_cte_type` is null, `request.file_cte_type_dropped` gives the reason, and the table prints a `CTE:` line. `request.file_cte_type` comes from the route helper's result: what was sent on `ok`, what was attempted on `unavailable:*` and `error` (the request may never have left), and null when nothing was built (for example without a key). Without a key the reason is still computed from the file with the same helper (`_file_cte_type_for_jev`), so the report says the `--cte-type` would be withheld. An unknown value is a usage error (exit 1) and nothing is sent. Omit it for mixed-type files. |

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

The demo file names each row's CTE in its own `cte_type` column, so it is
a per-row file: adding `--cte-type shipping` sends no `file_cte_type` and
the report shows `file has a per-row CTE column: cte_type`.

With `--simulate-apply` and answers in the `auto_apply` band, the four
headers whose canonical column is already in the file (`Lot #`, `Item Desc`,
`Qty Shpd`, `Ship Dt`) stay blocked with `target_present`, and `Ship-To GLN`
and `Trucking Co` show `would_apply: yes`, since the file has no
`ship_to_gln` or `carrier` column. `Internal Notes` is never applied.

Exit codes: `0` suggestions received, or no unrecognised headers (no request
made); `1` bad usage (including an unknown `--cte-type`), an unreadable, oversized (over 5 MB) or non-UTF-8
file (stdout stays empty, the message goes to stderr), a malformed header
row (status `malformed_header`, with or without a key: the report on stdout
names the problem, never the header's content, says `Sent: nothing`, and a
hint goes to stderr), or an unexpected error
(status `error`, for example a malformed `TYPESAFE_BASE_URL`); `2` not configured (`TYPESAFE_API_KEY` unset) or switched off
(`REGENGINE_JEV_ENABLED=0`); `3` vendor unavailable. For `2` and `3` the
status (for example `unavailable:auth`) and a one-line hint go to stderr.

Keep the key out of shell history and tracked files. Use `--prompt-key`, or
enter it silently for the current shell with
`read -rs TYPESAFE_API_KEY && export TYPESAFE_API_KEY`. Keep the stored copy
in a password manager or the environment's secret variables, not in the
repository. (`.env` is excluded from commits but is still plaintext on disk.)

## Measure Jev on RegEngine data

`scripts/jev_eval.py` scores both questions on labelled header rows before
any apply switch goes on. The cases are:

- RegEngine's seven CSV templates, built from `CTE_COLUMNS` and labelled with
  their own CTE;
- `docs/engineering/examples/jev_eval_cases.json`: 15 supplier-style header
  rows (shipping, receiving, harvesting, cooling, initial packing,
  transformation, first land-based receiving, two mixed or unclear files,
  one with a per-row CTE column) with the acceptable CTE and about 100
  acceptable canonical fields for unrecognised columns.

Labels list every acceptable answer (`["quantity", "unit_of_measure"]` for
`Pallets`). The headers are spelled as supplier exports spell them, not
copied from the example headers in the question vocabulary, so the prompt
does not grade itself. The loader rejects unknown labels, and a test fails
if a labelled header is one the parser already reads (it would never be
asked).

```bash
python3 scripts/jev_eval.py --prompt-key            # table
python3 scripts/jev_eval.py --prompt-key --json     # machine-readable
python3 scripts/jev_eval.py --cases mine.json --no-templates
```

Only header rows are sent (the cases hold no values; sample values are
forced off). About 22 requests per question set, four at a time.

For each question set the report gives:

- accuracy over the answers;
- mean confidence of right and wrong answers;
- for thresholds 0.50 to 0.98: how many answers would be applied (they name
  a CTE or a field; `mixed_or_unclear` and `no_match` apply nothing), how
  many of those are wrong, precision and coverage;
- every answer that would be applied at the current threshold and is wrong;
- the recommended auto-apply threshold.

The recommendation is the lowest swept threshold at or above 0.85 (the
agent-artifact review floor) at which nothing applied was wrong. It is a
starting floor on this data, not a guarantee: a set this size can show
errors, never prove their absence. Add every real file that goes wrong to
the cases file.

Exit codes: 0 ran, 1 bad usage or cases file, 2 not configured, 3 vendor
unavailable for at least one request.

## Ask Jev from the command line (agent sidecar)

`scripts/jev_ask.py` asks Jev any typed question about a state you give it.
Coding agents use it to get a second opinion alongside a user's request. The
procedure is in `.claude/skills/jev-sidecar/SKILL.md`, and `AGENTS.md` points
every agent to it.

```bash
venv/bin/python scripts/jev_ask.py \
  --state '{"headers": ["Ship Dte", "Cust Name", "Lot No."]}' \
  --choice cte "Which FSMA 204 CTE do rows with these headers record?" \
    "shipping=goods leaving the sender" "receiving=goods arriving" "unclear" \
  --noul has_lot "Does one of the headers name a traceability lot code column?" \
  --score risk "How likely is this file to be rejected as-is?" low medium high
```

- **Question kinds:** `--choice ID TEXT OPTION...`, where an option is `name`
  or `name=description`; `--noul ID TEXT`; `--score ID TEXT LEVEL...`, with 2
  to 10 levels, lowest first.
- **Questions file:** `--questions-file` takes questions in the API's format.
- **State:** `--state`, `--state-file`, or stdin with `--state-file -`. The
  value is JSON, or plain text when it does not parse as JSON.
- **Output:** one line per answer with its confidence, or `--json`.
- **Key:** it reads `TYPESAFE_API_KEY`, or with `--prompt-key` a hidden prompt.
  The key is never printed.
- **What is sent:** the state goes to `api.typesafe.ai`. It must never hold
  secrets or customer data.
- **Logs:** the client logs only metadata under the purpose `agent_sidecar`.
- **Exit codes:** 0 answered, 1 bad usage, 2 not configured, 3 Jev unavailable.
  With 1 or 2 nothing is sent. Code 2 covers no key, Jev switched off, or
  missing packages.

## Rollout

1. Set `TYPESAFE_API_KEY` on staging. Upload representative supplier files.
   Suggestions appear on the response and in Agent Reviews (filter: Field
   mapping). Nothing changes in the rows.
2. Run `python3 scripts/jev_eval.py --prompt-key` and read the
   recommendation and the wrong answers for both question sets. Compare
   suggestions against the intended mappings. To check a file before
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
5. File CTE: for each RegEngine template (`GET /api/v1/templates/{cte}`)
   and representative supplier exports, run
   `python3 scripts/jev_header_preview.py FILE --file-cte` (or upload the
   file with no `cte_type` and read `cte_type_suggestion` on the 400).
   When the answers are right, turn on
   `REGENGINE_JEV_APPLY_FILE_CTE_TYPE=1`; roll back with `0`.

## Failure modes

`header_mapping_engine.status` on the response says what happened:

| Status | Meaning |
| --- | --- |
| `ok` | Answers received and recorded. |
| `no_unrecognized_headers` | Every column was already known; no request made. |
| `malformed_header` | The header row spans lines, contains a line break, or has a header over 128 characters (usually an unterminated quote). No request made, no sample values collected, no artifacts; `csv_header_mapping_malformed_header` is logged with the reason, never the header. Such a file usually fails row parsing too (400); if its rows parse, they ingest exactly as without Jev. |
| `unavailable:disabled` | Kill switch or no key (engine field is null in this case). |
| `unavailable:auth` | 401/403 from the vendor: check the key. |
| `unavailable:rate_limited` | 429 after retries. |
| `unavailable:timeout`, `unavailable:connection` | Network; upload proceeds unmapped. |
| `unavailable:server_error`, `unavailable:invalid_response` | Vendor-side; upload proceeds unmapped. |
| `error` | Unexpected exception in RegEngine code; see `csv_header_mapping_failed` in the log. |

In every non-`ok` case the upload is processed exactly as without Jev.
The SDK types confidences and probabilities as unbounded floats; the
wrapper clamps them to `[0, 1]` and reads a non-finite value as `0.0`
(`_unit` in `services/shared/jev/client.py`), so vendor float noise can
never fail the bounded response models after rows were stored. A
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
  validated on RegEngine data yet; that is step 2 of the rollout
  (`scripts/jev_eval.py`).
- The file CTE question is skipped whenever a header is a per-row CTE
  column the parser reads, even if its values are blank or are not CTEs
  (a `Type` column of pallet types): those rows are still rejected with
  `No CTE type`.

## Verification

```bash
python3 -m pytest services/shared/tests/test_jev_client.py services/shared/tests/test_jev_header_mapping.py services/shared/tests/test_jev_cte_classification.py -q --no-cov
python3 -m pytest services/ingestion/tests/test_csv_jev_header_mapping.py services/ingestion/tests/test_csv_jev_file_cte.py services/ingestion/tests/test_jev_header_preview_script.py services/ingestion/tests/test_jev_eval_script.py -q --no-cov
cd frontend && npx vitest run src/__tests__/lib/cte-suggestion.test.ts src/__tests__/pages/ingest-csv.test.tsx src/__tests__/pages/data-import.test.tsx
```

All tests run offline against `httpx2.MockTransport`; no test contacts the
vendor.
