# LlamaIndex Extract v2.5 on supplier PDFs

Decision record: `docs/architecture/decisions/ADR-006-llamaindex-extract-supplier-pdfs.md`.

Extract is LlamaIndex's schema-guided document extraction agent, hosted on
LlamaCloud. Extract v2.5 (released 2026-10-01) is the first release RegEngine
runs. It answers one question about a document: *fill this JSON Schema from
it*, and returns the filled object with a citation and a confidence per field.

RegEngine uses it in two places:

1. `POST /api/v1/supplier/bulk-upload/parse` for a PDF the deterministic
   parser cannot read (no tables, no JSON block): scanned onboarding forms,
   letters, mixed layouts. ([Where it runs](#where-it-runs))
2. `scripts/extract_document.py` for operator extraction of any local document
   against the supplier schema or any JSON Schema.
   ([Extract a document yourself](#extract-a-document-yourself))

It is an API service, not a model that runs in the container. There is no
weight download and no GPU; the SDK (`llama-cloud`) is pure Python.

## What Extract is

| Thing | Value |
| --- | --- |
| Vendor, product | LlamaIndex, Extract (part of LlamaParse / LlamaCloud) |
| SDK | `llama-cloud` (Stainless-generated; pinned `>=2.16.0,<3` in `requirements.in`) |
| API root | `https://api.cloud.llamaindex.ai` (`LLAMA_CLOUD_BASE_URL` overrides) |
| Credential | `LLAMA_CLOUD_API_KEY` (the SDK also reads `LLAMA_PARSE_API_KEY`) |
| Tiers | `cost_effective` (5 credits/page), `agentic` (15), `agentic_plus` (50), `turbo` (35) |
| Versioning | `version` is `latest` or a `YYYY-MM-DD` date resolving to the nearest release at or before it. RegEngine pins `2026-10-01` (the v2.5 release). The job response reports the concrete version it ran, which lands in evidence. |
| Granularity | `extraction_target`: `per_doc` (one object), `per_page`, `per_table_row` |
| Grounding | `cite_sources` (citations; bounding boxes on `agentic` and above), `confidence_scores` (per field, `[0, 1]`) |

Vendor references: [Extract v2.5 announcement](https://www.llamaindex.ai/blog/introducing-extract-v2-5),
[Python SDK on PyPI](https://pypi.org/project/llama-cloud/).

## Where it runs

| Piece | Path |
| --- | --- |
| SDK wrapper: settings, fail-open client, evidence | `services/shared/document_extract/settings.py`, `services/shared/document_extract/client.py` |
| FSMA 204 supplier schema and conversion to parser rows | `services/shared/document_extract/supplier_schema.py` |
| Integration point | `services/admin/app/bulk_upload/parsers.py` (`_extract_pdf_with_agent`, called from `parse_incoming_file` after `_parse_pdf_bytes` when no rows came out) |
| Response field | `services/admin/app/bulk_upload/routes.py` (`BulkUploadParseResponse.extraction`), `frontend/src/types/api.ts` (`SupplierBulkUploadParseResponse.extraction`) |
| Startup log | `server/main.py`: `document_extract_configured enabled=... key_present=... tier=... version=...` (never the key) |
| Operator CLI | `scripts/extract_document.py` |
| Tests | `services/shared/tests/test_document_extract_client.py`, `services/admin/tests/test_bulk_upload_extract_fallback.py` |

Only the bulk-upload PDF path calls Extract. CSV, JSON and XLSX uploads never
do, and `POST /api/v1/ingest/csv` is untouched.

## Request flow (bulk upload)

1. `_parse_pdf_bytes` runs exactly as before: page-count guard
   (`BULK_UPLOAD_MAX_PDF_PAGES`, default 200, HTTP 413 above it), pdfplumber
   tables, matrix tables, then a JSON blob in the page text.
2. If that produced zero rows across `facilities`, `ftl_scopes`, `tlcs` and
   `events`, and `DocumentExtractSettings.from_env().enabled` is true, the
   whole PDF is sent:
   1. `files.create(purpose="extract")` uploads the bytes.
   2. `extract.run(...)` creates the job with the supplier schema, the pinned
      tier and version, `max_pages = min(REGENGINE_DOC_EXTRACT_MAX_PAGES,
      BULK_UPLOAD_MAX_PDF_PAGES)`, `cite_sources`, `confidence_scores` and
      `disable_cache`, and polls until it finishes or the job budget
      (`REGENGINE_DOC_EXTRACT_JOB_TIMEOUT_SECONDS`, default 240 s) runs out.
   3. `files.delete(file_id)` removes the vendor-side file, best effort, in
      a `finally` so it runs on failure too.
3. The returned sections become rows tagged with `record_type`
   (`rows_from_extraction`) and go through the parser's own `_classify_row`
   and `_normalize_row`. From there validation, the review step and commit
   are the same as for a CSV.
4. `parsed["extraction"]` carries the evidence and is stored on the upload
   session and returned by `/parse`:

```json
{
  "evidence": {
    "purpose": "bulk_upload_pdf", "provider": "llamaindex", "product": "extract",
    "requested_tier": "agentic", "requested_version": "2026-10-01",
    "tier": "agentic", "version": "2026-10-01",
    "job_id": "...", "file_id": "...", "parse_job_id": "...",
    "extraction_target": "per_doc", "schema_version": "1",
    "pages_extracted": 2, "pages_billed": 2, "credits": 30.0,
    "latency_ms": 8120, "sdk_version": "2.16.0"
  },
  "confidence": {"fields": 23, "min": 0.61, "mean": 0.93},
  "field_metadata": {"facilities": [{"name": {"confidence": 0.98, "citation": [...]}}]},
  "rows": 4
}
```

5. Warnings tell the reviewer what happened: `N rows extracted by LlamaIndex
   Extract (tier=..., version=...); review before commit`, or `Document
   extraction agent unavailable (<reason>); PDF parsed by tables only`, or
   `Document extraction agent found no FSMA 204 records in this PDF`.

## Failure modes

Every failure is fail-open: the upload ends exactly as the deterministic pass
left it, with one warning naming the reason.

| `reason` | Cause |
| --- | --- |
| `disabled` | No key, or `REGENGINE_DOC_EXTRACT_ENABLED=0` (the fallback is skipped silently; no warning) |
| `auth` | 401/403 from the vendor |
| `rate_limited` | 429 |
| `timeout`, `connection` | HTTP timeout or network failure (after `REGENGINE_DOC_EXTRACT_MAX_RETRIES`) |
| `bad_request` | 400/422, usually a schema the vendor rejects |
| `not_found` | 404 (wrong project id, file already gone) |
| `server_error`, `api_error` | 5xx, other 4xx |
| `job_failed` | Job reached `FAILED` or `CANCELLED` |
| `job_timeout` | Job did not finish inside `REGENGINE_DOC_EXTRACT_JOB_TIMEOUT_SECONDS` |
| `empty_result` | Job completed with no data |
| `invalid_response`, `sdk_error` | Response the SDK could not parse; any other SDK error |

A programming error (anything that is not an SDK or polling exception)
propagates; it must be seen, not swallowed.

## Data handling

- **What leaves the process:** the entire PDF, up to the page caps. This is
  more than Jev (header row only). Set the key only on deployments whose
  tenants have agreed to third-party document processing; see the
  processing addendum in `docs/DATA_PROCESSING_AGREEMENT.md`.
- **Retention at the vendor:** the uploaded file is deleted when the job
  ends; `disable_cache` is on by default so results are not reused across
  jobs. Job records remain on the vendor side as its own audit log.
- **Logs:** metadata only (purpose, job id, tier, version, pages, latency,
  confidence summary). Extracted values and the document never appear in
  RegEngine log records; the tests assert it.
- **Tenant isolation:** one tenant's document per call; the result is written
  only to that tenant's upload session.
- **Never auto-committed:** rows land in the parse session like any other
  upload and go through validate and the human commit step. Per-field
  confidence and citations are on the session for the reviewer.

## Configure it

Production or staging: put `LLAMA_CLOUD_API_KEY` on Railway through the
RegEngine Key Drop page (see `CLAUDE.md`, Secrets), then seal it. Agent and
local sessions: environment variables. The full list with defaults is in
`.env.example` and in the module docstring of
`services/shared/document_extract/settings.py`.

| Variable | Default | Notes |
| --- | --- | --- |
| `LLAMA_CLOUD_API_KEY` | unset | Unset = feature off |
| `REGENGINE_DOC_EXTRACT_ENABLED` | `1` | Kill switch |
| `REGENGINE_DOC_EXTRACT_TIER` | `agentic` | `cost_effective` is cheaper; `agentic_plus` for hard scans |
| `REGENGINE_DOC_EXTRACT_VERSION` | `2026-10-01` | Extract v2.5. `latest` floats |
| `REGENGINE_DOC_EXTRACT_MAX_PAGES` | `50` | Cost ceiling per document |
| `REGENGINE_DOC_EXTRACT_JOB_TIMEOUT_SECONDS` | `240` | Under the 300 s admin proxy limit |
| `REGENGINE_DOC_EXTRACT_DISABLE_CACHE` | `1` | `0` lets the vendor reuse results |

Verify by effect, never by reading the key: the deploy log shows
`document_extract_configured enabled=True key_present=True ...` at startup,
and a table-less PDF upload returns an `extraction` block.

## Extract a document yourself

```bash
venv/bin/python scripts/extract_document.py supplier_packet.pdf            # supplier schema, text report
venv/bin/python scripts/extract_document.py supplier_packet.pdf --rows     # plus bulk-upload parser rows
venv/bin/python scripts/extract_document.py invoice.pdf --schema invoice.json --json
venv/bin/python scripts/extract_document.py scan.png --tier agentic_plus --target per_page
venv/bin/python scripts/extract_document.py packet.pdf --prompt-key        # key for this run only
```

Exit codes: `0` extraction received, `1` usage or file problem, `2` not
configured, `3` vendor unavailable. The script never prints the key.

## Change the schema

`SUPPLIER_DOCUMENT_SCHEMA` in `supplier_schema.py` mirrors the four sections
and canonical field names of the bulk-upload parser. Keep it flat, keep
`description` text specific (Extract reads it), and bump
`SUPPLIER_SCHEMA_VERSION` on any field change so evidence stays
interpretable. New fields on `events` need no parser change: unknown keys
land in `kde_data`. New fields on `facilities`, `ftl_scopes` or `tlcs` must
be read by `_classify_row` to have any effect.
