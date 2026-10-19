# ADR-006: LlamaIndex Extract v2.5 for Supplier PDFs the Table Parser Cannot Read

**Status:** Proposed
**Date:** 2026-10-05
**Decision owner:** RegEngine engineering

## Context

`POST /api/v1/supplier/bulk-upload/parse` accepts CSV, JSON, XLSX and PDF.
The PDF path (`services/admin/app/bulk_upload/parsers.py`,
`_parse_pdf_bytes`) reads tables with pdfplumber and, failing that, looks for
a JSON block in the page text. A scanned onboarding form, a cover letter
listing facilities and lots, or a packet whose tables are images produces
`PDF parsed but no structured rows detected` and the supplier is asked for a
spreadsheet. Those are the documents small suppliers actually have.

The repository already treats external models as advisory inputs behind
confidence (ADR-005, Jev). Extract v2.5 (LlamaIndex, released 2026-10-01) is
a schema-guided extraction agent: it returns the filled JSON Schema with a
citation and a confidence per field, with published accuracy above
general-purpose LLMs on document extraction and per-page pricing. That shape
fits the gap: the bulk-upload parser already has a canonical row shape, so
the agent's output can be routed through the existing classify, validate and
human-commit steps unchanged.

## Decision

1. Add the vendor SDK (`llama-cloud`, pinned `>=2.16.0,<3`) and a thin,
   fail-open wrapper in `services/shared/document_extract/`, modelled on the
   Jev wrapper: optional (no `LLAMA_CLOUD_API_KEY`, no behaviour change),
   every SDK failure becomes `DocumentExtractUnavailable`, bounded latency,
   metadata-only logging, evidence on every result.
2. Pin the Extract release by date (`2026-10-01`, v2.5) and the tier
   (`agentic`) by default; record the concrete version the job ran.
3. Run it only as a second pass on the bulk-upload PDF path, only when the
   deterministic pass produced no rows. Its rows go through the same
   `_classify_row` as every other format; nothing is auto-committed.
4. Minimise what the vendor keeps: delete the uploaded file when the job
   ends, disable result caching by default, cap pages per document.
5. Keep the evidence (job id, tier, version, pages, credits, per-field
   confidence and citations) on the upload session and return it from
   `/parse` so the reviewer and the audit trail see where rows came from.
6. Ship an operator CLI (`scripts/extract_document.py`) that runs the same
   wrapper against any local document and any JSON Schema.

## Rationale

### Alternatives considered

1. **Tesseract OCR plus the existing regexes** (already in the ingestion
   service for text extraction)
   - Pros: runs in-container, no data leaves.
   - Cons: OCR text still needs structure; the regex/alias approach is what
     fails on these documents today.
2. **A generative LLM with a prompt-and-parse step** (OpenAI, Groq and
   Vertex are already dependencies)
   - Pros: no new vendor.
   - Cons: no per-field grounding or calibrated confidence; the repository
     caps generative output at 0.60 confidence for that reason (#2947);
     prompt-injection surface on untrusted PDFs is the application's problem.
3. **Self-hosted open extraction model**
   - Pros: data stays in-house.
   - Cons: GPU hosting the project does not have; accuracy below the hosted
     agents on scanned forms; operational load on a one-person team.
4. **Make Extract the primary PDF parser**
   - Cons: cost per page on every upload, vendor on the critical path, and
     the deterministic parser already handles clean tabular PDFs.

## Consequences

### Positive
- Table-less supplier PDFs produce reviewable rows instead of a dead end.
- Grounding (citations, confidence) is on the session for every row the
  agent produced; the commit step is unchanged.
- The wrapper is reusable for other document types (COAs, BOLs) by passing a
  different schema.

### Negative
- The whole document leaves the process. The key must only be set where
  tenants have agreed to third-party processing.
- Per-page cost; bounded by page caps and the "second pass only" rule.
- A vendor outage degrades to today's behaviour, not to a better one.

### Neutral
- One more optional vendor credential to rotate; same key-handling rules as
  the others (`CLAUDE.md`, Secrets).

## References

- `docs/engineering/DOCUMENT_EXTRACT.md`
- `docs/architecture/decisions/ADR-005-jev-header-mapping-suggestions.md`
- https://www.llamaindex.ai/blog/introducing-extract-v2-5
