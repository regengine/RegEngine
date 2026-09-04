# NLP Service

## Deployment Reality

NLP is **not a separately deployed service**. It is a router domain mounted into the
consolidated monolith (`server/main.py`) at `/api/v1`:

- `nlp` is excluded from the exact production `ENABLED_ROUTERS` release set, so
  the entire NLP router surface (including `POST /api/v1/query/traceability`
  and the frontend `/api/nlp/ask` proxy) is disabled. Promotion requires
  route-manifest and tenant/auth coverage; the legacy experimental bypass is
  rejected in production.
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
- Demo: `scripts/verify_inflow_to_regengine_e2e.py` sends `X-Request-ID` through the ingestion path. (The previously referenced `scripts/demo/run_state_llm_e2e.py` was removed; the `scripts/demo/` directory no longer exists.)

## LLM Extractor Wiring

`LLMGenerativeExtractor` (`app/extractors/llm_extractor.py:396`) does not wrap a
single client. It builds one at construction time through
`LLMClientFactory.create()` (`llm_extractor.py:367`), which picks one of three
concrete clients by substring-matching `LLM_MODEL`:

| `LLM_MODEL` contains | Client | Also required |
|----------------------|--------|---------------|
| `gpt` | `OpenAILegacyClient` (`llm_extractor.py:257`) | `OPENAI_API_KEY` |
| `gemini` | `VertexAIClient` (`llm_extractor.py:289`) | `GOOGLE_CLOUD_PROJECT` (+ optional `GOOGLE_CLOUD_LOCATION`, default `us-central1`) |
| anything else | `OllamaClient` (`llm_extractor.py:318`) | `OLLAMA_HOST` (default `http://localhost:11434`) |

The default `LLM_MODEL` is **`llama3:8b`**, so with no configuration at all the
factory returns `OllamaClient` pointed at localhost.

**Selection is a fallthrough, not a dispatch.** If the "Also required" variable
for the matched provider is missing, the factory does *not* raise — it falls
through to `OllamaClient`. Setting `LLM_MODEL=gpt-5` without `OPENAI_API_KEY`
therefore silently runs against a local Ollama endpoint rather than OpenAI. The
one exception is production: `REGENGINE_ENV=production` with a loopback
`OLLAMA_HOST` raises `RuntimeError` at construction rather than starting
(`llm_extractor.py:385`).

There is no `SimpleLLMClient` and no `generate_json` method. To add a provider,
subclass `BaseLLMClient` (`llm_extractor.py:245`), implement
`generate(prompt, system_prompt) -> str`, and add a branch to
`LLMClientFactory.create()`.

### Expected JSON Output Schema

The contract is enforced at runtime by a `Draft202012Validator` built from
`LLMGenerativeExtractor.JSON_SCHEMA` (`llm_extractor.py:448`). It is a JSON
**object** with a required `results` array — not a bare array — and
`additionalProperties` is `false` at both levels:

```json
{
  "results": [
    {
      "provision_text": "Exact quote from text",
      "obligation_type": "REQUIREMENT",
      "confidence": 0.87
    }
  ],
  "warnings": []
}
```

- `obligation_type` must be one of exactly `REQUIREMENT`, `PROHIBITION`,
  `REPORTING`, `EXEMPTION`, `UNKNOWN`. Any other value (`RESTRICTION`, for
  example) fails validation.
- `provision_text` is 5–4000 characters; `confidence` is a number in `[0.0, 1.0]`.
- All three item fields are required. `warnings` is optional.

Output that fails validation is retried up to `LLM_MAX_RETRIES` times with the
validation error fed back to the model; exhausting the budget yields no
extractions.

### Hallucination Guard

The extractor drops any item whose `provision_text` does not appear in the
original, non-redacted source text (`_quote_in_original`), and records
`source_span_start` / `source_span_end` offsets for the items it keeps. Items
carrying SQL sentinels are dropped; items carrying prompt-injection markers are
kept but flagged `needs_review` for HITL rather than silently discarded.

### Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `LLM_MODEL` | `llama3:8b` | Model id; also selects the provider (see table above). |
| `OPENAI_API_KEY` | unset | Required for the OpenAI client. **Not** `LLM_API_KEY` — no code reads that name. |
| `GOOGLE_CLOUD_PROJECT` | unset | Required for the Vertex client. |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` | Vertex region. |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint; loopback is refused in production. |
| `LLM_TIMEOUT_S` | `45` | Per-request timeout, seconds. |
| `LLM_MAX_RETRIES` | `3` | Self-correction attempts on invalid JSON. |
| `LLM_MAX_INPUT_CHARS` | `50000` | Input truncation cap. |

### Testing

```zsh
python -m pytest services/nlp/tests/test_llm_extractor_agent.py -v
```

Related suites: `services/nlp/tests/test_llm_prompt_injection.py` (delimiter and
guardrail behavior) and `services/nlp/tests/test_llm_resilience.py` (retry and
failure paths). All inject a stub client, so none of them require a provider
key or a running Ollama.

## Installation

There is no `[nlp]` extras group and the root package is not installable — see
the note at the top of `pyproject.toml`. Dependencies come from
`requirements.lock` (compiled from `requirements.in`), which already includes
`openai`, `jsonschema` and `pdfminer.six` unconditionally.

The Vertex path is the exception: `vertexai` is **not** in `requirements.in`, so
`VertexAIClient` raises `ImportError` on construction unless the SDK is
installed separately.

To exercise the OpenAI path locally:

```zsh
export LLM_MODEL="gpt-5"
export OPENAI_API_KEY="sk-proj-<your-key>"
```

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
