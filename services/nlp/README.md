# NLP Service

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
