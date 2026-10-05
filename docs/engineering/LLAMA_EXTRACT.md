# LlamaCloud Extract v2.5: document data extraction

Extract is LlamaIndex's hosted, schema-guided document extraction service
(LlamaCloud). A call sends one document plus a JSON Schema and returns JSON
that conforms to the schema, with a citation and a confidence score per field.
Version 2.5 (released 2026-10-01) is the pinned default here. It is not a
downloadable model: documents leave the process for the vendor's API.

RegEngine uses it for the paperwork that arrives next to the structured feeds
(CSV, EDI, EPCIS): invoices, bills of lading, receiving logs, packing lists and
certificates whose key data elements would otherwise be keyed by hand.
Validation, tenant scoping and evidence persistence stay in RegEngine code; the
vendor only proposes field values.

Vendor references: [announcement](https://www.llamaindex.ai/blog/introducing-extract-v2-5),
[Python SDK](https://developers.llamaindex.ai/python/cloud/llamaextract/) (`llama-cloud`).

## Where it runs

| Piece | Path |
| --- | --- |
| Settings (env-driven, optional feature) | `services/shared/llama_extract/settings.py` |
| Fail-open client, result and evidence records | `services/shared/llama_extract/client.py` |
| Command line: one document, one schema | `scripts/extract_document.py` |
| Offline tests (mock transport, nothing on the wire) | `services/shared/tests/test_llama_extract_client.py`, `services/shared/tests/test_extract_document_script.py` |
| Startup log line confirming a key is live (never the key) | `server/main.py` (`llama_extract_configured ...`) |

No ingestion route calls it yet. The wrapper is the integration seam: a route
or task handler calls `get_document_extractor().extract(...)`, validates the
returned data with the existing FSMA validators, and persists the result with
its `ExtractionEvidence` as an agent artifact under the tenant.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `LLAMA_CLOUD_API_KEY` | unset | Vendor credential. Unset = disabled; every call raises `LlamaExtractUnavailable("disabled")` and nothing is sent. |
| `LLAMA_CLOUD_BASE_URL` | SDK default | Gateway, proxy or region override. |
| `LLAMA_CLOUD_PROJECT_ID` | unset | LlamaCloud project for uploads and jobs; unset = the key's default project. |
| `REGENGINE_LLAMA_EXTRACT_ENABLED` | `1` | Kill switch; `0` disables even with a key. |
| `REGENGINE_LLAMA_EXTRACT_TIER` | `agentic` | `cost_effective`, `agentic`, `agentic_plus` or `turbo`. |
| `REGENGINE_LLAMA_EXTRACT_VERSION` | `2.5` | Extract release. Pinned so results stay comparable; `latest` floats. The job's resolved version is recorded in evidence either way. |
| `REGENGINE_LLAMA_EXTRACT_TIMEOUT_SECONDS` | `600` | Upload plus polling budget per document. |
| `REGENGINE_LLAMA_EXTRACT_MAX_PAGES` | `0` | Page cap per document; `0` = none. |
| `REGENGINE_LLAMA_EXTRACT_CITE_SOURCES` | `1` | Per-field citations (page and matching text) in the result. |
| `REGENGINE_LLAMA_EXTRACT_CONFIDENCE_SCORES` | `1` | Per-field confidence in the result. |
| `REGENGINE_LLAMA_EXTRACT_DISABLE_CACHE` | `1` | Vendor does not keep or reuse extraction results. |

Where the key goes, by place: the claude.ai cloud environment settings for
agent sessions, the RegEngine Key Drop page or the Railway dashboard for
production and staging (then seal it). One key per place. See the Secrets
section of `AGENTS.md`.

## Using it from code

```python
from pydantic import BaseModel, Field
from shared.llama_extract import LlamaExtractUnavailable, get_document_extractor


class ReceivingLog(BaseModel):
    traceability_lot_code: str = Field(description="Lot code as printed on the document")
    receive_date: str = Field(description="Date received, ISO 8601")
    quantity: float | None = Field(default=None, description="Quantity received")
    unit_of_measure: str | None = None


extractor = get_document_extractor()
try:
    result = extractor.extract(
        upload_bytes,
        file_name="receiving-2026-09-30.pdf",
        data_schema=ReceivingLog,
        purpose="receiving_log",
    )
except LlamaExtractUnavailable as exc:
    # exc.reason is one of: disabled, auth, rate_limited, timeout, connection,
    # bad_request, invalid_response, server_error, api_error, job_failed,
    # sdk_error, empty_result. Fall back to manual keying; never block the upload.
    ...
else:
    result.data            # {"traceability_lot_code": "LOT-4471", ...}
    result.field_metadata  # {"target": "per_doc", "fields": {"traceability_lot_code": {"citation": [...], "confidence": 0.97}, ...}}
    result.evidence        # ExtractionEvidence: tier, requested/resolved version, job_id, file_id, pages_billed, credits, schema_sha256, sdk_version
```

`data_schema` is a pydantic model class or a plain JSON Schema dict.
`extraction_target` is `per_doc` (default), `per_page` or `per_table_row`;
`target_pages`, `max_pages`, `system_prompt`, `spreadsheet_mode`, `tier` and
`version` override the settings for one call.

## Command line

```bash
venv/bin/python scripts/extract_document.py --file invoice.pdf --schema schema.json
venv/bin/python scripts/extract_document.py --file bol.pdf \
    --schema-inline '{"type":"object","properties":{"lot_code":{"type":"string"}}}' \
    --tier agentic_plus --pages 1-2 --json --out bol.json
```

Exit codes: `0` extracted, `1` bad usage, `2` not configured (no key, kill
switch, or packages missing; nothing sent), `3` vendor unavailable or job
failed. `--prompt-key` reads the key from a hidden prompt for one run.

## Guarantees

- **Optional and fail-open.** No key, kill switch, auth failure, rate limit,
  timeout, 5xx or failed job all surface as `LlamaExtractUnavailable` with a
  stable `reason`. Callers keep their deterministic path.
- **Bounded.** One document never takes longer than the configured budget.
- **No content in logs.** RegEngine logs purpose, tier, version, job id,
  latency, pages and credits. The SDK's own DEBUG logging (request bodies) is
  capped at INFO unless `LLAMA_CLOUD_LOG` is set deliberately.
- **Evidence.** Every result carries provider, product, tier, requested and
  resolved version, job and file ids, latency, pages billed, credits, SDK
  version and a SHA-256 of the schema, ready to persist next to the record.
- **Tenant isolation is the caller's.** Send only the file the caller is
  authorised to read; persist the result under that tenant.

## Cost

Vendor pricing per page at the time of writing: `cost_effective` 5 credits,
`agentic` 15, `turbo` 35, `agentic_plus` 50. Set `REGENGINE_LLAMA_EXTRACT_MAX_PAGES`
before pointing it at multi-hundred-page scans.
