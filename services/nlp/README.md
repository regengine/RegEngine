# NLP Service

## Deployment Reality

NLP is **not a separately deployed service**. It is a router domain mounted into the
consolidated monolith (`server/main.py`) at `/api/v1`:

- `nlp` is in `_EXPERIMENTAL_ROUTERS`, so the entire NLP router surface (including
  `POST /api/v1/query/traceability` and the frontend `/api/nlp/ask` proxy) is
  **auto-disabled in production** unless `ENABLE_EXPERIMENTAL_ROUTERS` is truthy.
- The standalone entrypoint `services/nlp/main.py` is local-debug only —
  `assert_legacy_entrypoint_not_in_production` blocks it in production.
- The Kafka consumer pipeline (`app/consumer/`) is deprecated; it only starts from the
  standalone entrypoint with `EVENT_BACKBONE=kafka` (default is `pg`).
- The production extraction path is the PostgreSQL task queue:
  `server/workers/task_processor.py` handles `nlp_extraction` rows by calling
  `services.nlp.app.extractor.extract_entities` (the regex backstop extractor — the
  LLM extractor described below is only wired into the deprecated Kafka path).

## Request Correlation

- Header `X-Request-ID`: Provide a UUID to correlate logs across ingestion → NLP → graph. If omitted, services generate one and echo it back.
- Logging: Services bind `request_id` into structured logs via `structlog`, visible in all entries during the request.
- Demo: `scripts/demo/run_state_llm_e2e.py` sends `X-Request-ID` to ingestion and reuses it for extractor calls.

## LLM Extractor Wiring

The `LLMGenerativeExtractor` uses a minimal wrapper `SimpleLLMClient` with env-configurable model selection via `LLM_MODEL` (defaults to `gemini-3-pro`). Replace `SimpleLLMClient.generate_json(prompt)` with the actual SDK call (Gemini 3 Pro / GPT-5) and ensure it returns a JSON string per the expected schema.

### Expected JSON Output Schema

```json
[
  {
    "provision_text": "Exact quote from text",
    "obligation_type": "REPORTING|RESTRICTION|etc",
    "confidence": 0.0-1.0
  }
]
```

### Hallucination Guard

The extractor validates that `provision_text` appears in the source `text` before including it in results. Consider adding stricter validations (e.g., fuzzy matching, span offsets) for noisy sources.

### Environment

- `LLM_MODEL`: model id string (e.g., `gemini-3-pro`, `gpt-5`).
- `LLM_API_KEY`: provider API key (OpenAI for `gpt-*`).

### Testing

Unit tests under `tests/nlp/test_llm_extractor.py` validate JSON parsing and quote checks by injecting a dummy client.

## Installation

Install the NLP optional dependency group to enable OpenAI SDK:

```zsh
pip install -e .[nlp]
```

Then set environment variables and run tests or the demo:

```zsh
export LLM_MODEL="gpt-5"
export LLM_API_KEY="sk-proj-<your-key>"
python -m pytest tests/nlp/test_llm_extractor.py -v
```

For PDF text extraction, `pdfminer.six` is included in the `[nlp]` extras.

## Traceability Query API (Phase 4)

NLP service now exposes a deterministic natural-language query endpoint:

- `POST /api/v1/query/traceability`

### Request

```json
{
  "query": "show me all lettuce from Supplier X in the last 30 days",
  "limit": 50
}
```

### Behavior

- Uses rule-based intent parsing (no LLM calls in v1).
- Converts natural language into an allowlisted query plan.
- Delegates execution to graph-service FSMA endpoints.
- Returns `answer`, `results`, `evidence`, `confidence`, and `warnings`.

### Required scope

- API key must include `graph.query` (or wildcard equivalent).
