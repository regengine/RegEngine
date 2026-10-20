# ADR-005: TypeSafe Jev for CSV Header-Mapping Suggestions

**Status:** Proposed
**Date:** 2026-09-27
**Decision owner:** RegEngine engineering

## Context

`POST /api/v1/ingest/csv` is the production CSV intake. Its row mapper
(`services/ingestion/app/csv_templates.py`, `parse_csv_rows`) recognises a
fixed set of column names. A supplier file whose headers say `Lot #`,
`Ship Dt` or `Recv Loc` passes those columns through as opaque KDEs, so the
row misses required fields and is either rejected or lands incomplete. The
only remedies today are hand-edited templates or one of eight duplicated alias
tables spread across sandbox, remediation, connector and admin code
(see the vocabulary list in `docs/engineering/JEV_HEADER_MAPPING.md`).

Every existing model integration in the repository is generative (OpenAI,
Vertex AI, Groq via LangChain). None runs on the production CTE path, and the
repository caps generative output at 0.60 confidence so it can never
auto-approve (#2947). `docs/security/MODEL_GOVERNANCE.md` sets a 0.85
human-review threshold, and the agent-artifact contract
(`docs/engineering/AGENT_ARTIFACT_SPEC.md`) already defines an advisory
`field_mapping_suggestion` artifact with a review queue and UI that nothing in
production writes to.

TypeSafe AI's Jev is a "System One" model: it does not generate text. A
request carries state plus typed questions (`Choice`, `Score`, `Noul`) and
returns one answer per question with a probability distribution and a
confidence in `[0, 1]`. That shape fits a header-mapping decision exactly: a
`Choice` over the canonical vocabulary plus `no_match`, with confidence code
can gate on.

## Decision

1. Add the vendor SDK (`typesafe-sdk`, pinned `>=0.7.2,<0.8`) and a thin,
   fail-open wrapper in `services/shared/jev/`. The wrapper is optional
   (no `TYPESAFE_API_KEY`, no behaviour change), converts every SDK failure
   into `JevUnavailable`, bounds latency (5 s per attempt, one retry by
   default), never logs state, and attaches provenance (model, request id,
   latency, usage, question-set version) to every answer.
2. Ask Jev, once per CSV upload and only about headers the parser does not
   recognise, which canonical FSMA 204 field each column represents. The
   vocabulary, wording and thresholds live in one reviewable module,
   `services/shared/jev/header_mapping.py`.
3. Record every actionable answer as an advisory `field_mapping_suggestion`
   agent artifact anchored to the upload's SHA-256 and ingestion run, queued
   through the existing agent bridge so it reaches `fsma.agent_artifacts`,
   the run ledger and the Agent Reviews queue. Return the suggestions and
   their provenance on the upload response.
4. Keep rows unchanged by default. Only when an operator sets
   `REGENGINE_JEV_APPLY_HEADER_MAPPINGS=1` does deterministic code copy a
   column under its canonical name, and only when the answer is in the
   `AUTO_APPLY` band (default `>= 0.90`), clears the agent-artifact
   human-review threshold (`0.85`), the target column is absent from the
   file, no column the parser would consult after the target is present
   either (a mapped column must never outrank a value the file carries, e.g.
   `tlc` when the target is `traceability_lot_code`), and no other column
   competes for the same target. The source column is left in place so
   nothing leaves the evidence trail.
5. Pin the model (`jev-1.13.0`) rather than the floating `jev-latest` alias,
   because the confidence thresholds are calibrated against a specific
   model. The concrete model name from each response is recorded anyway.

## Rationale

The production spine is `ingest -> canonicalize -> validate -> persist
evidence -> export`. This change strengthens canonicalization without
weakening the rest: schema validation still runs on every row, the applied
mapping is deterministic code acting on a recorded, reviewable suggestion,
and the vendor call can neither block nor reject an upload.

### Alternatives Considered

1. **Extend the hand-written alias tables** - Deterministic and free.
   - Pros: no vendor, no data leaves the process.
   - Cons: eight tables already drift; every new supplier vocabulary is a
     code change; no measure of how sure the mapping is.

2. **Generative LLM mapping (existing Groq / OpenAI stack)** - Prompt for a
   JSON mapping and parse it.
   - Pros: already a dependency.
   - Cons: seconds of latency on the upload path, free-text output to parse,
     no calibrated confidence, and the repository's own 0.60 cap means it
     could never be applied automatically.

3. **Embedding similarity against the canonical vocabulary** - Nearest
   canonical field by cosine similarity.
   - Pros: cheap, local.
   - Cons: similarity is not a calibrated probability; needs a model
     dependency and an evaluation corpus RegEngine does not have yet.

4. **Do nothing** - Keep templates as the only path.
   - Cons: the current onboarding friction is the problem being solved.

## Consequences

### Positive
- Unrecognised supplier columns get a typed, confidence-scored suggestion
  with provenance, visible to operators in the review queue and on the
  response, at sub-second latency.
- The apply path is opt-in and gated, so the first rollout is
  observe-and-review; thresholds can be tuned on real uploads before any row
  changes.
- No new router, table or migration: the artifact contract, bridge, ledger
  and review UI already exist.

### Negative
- A new external processor. Column headers (and, only if explicitly enabled,
  PII-redacted sample values) leave the process. TypeSafe AI is listed as a
  where-configured subprocessor; the DPA question is the operator's before
  turning it on for a customer tenant.
  - *Amended 2026-09-28:* when the uploader declares a single CTE for the
    file (the `cte_type` form field) and no row can contradict it, that
    canonical CTE name (for example `shipping`) is also sent, as
    `file_cte_type` (question set `csv-header-mapping.v2`). The subprocessor
    disclosure in `frontend/src/lib/trust-subprocessors.ts` says so.
- Jev reads instructions literally and does no arithmetic or date
  comparison (vendor's published limitations). The question set therefore
  asks only "which field is this column", never "what is this value".
- A pre-1.0 SDK. The dependency is capped at the next minor and Dependabot
  proposes bumps.

### Neutral
- Thresholds (`0.90` auto-apply, `0.50` review) are the vendor's published
  starting points, not RegEngine-validated numbers. They are environment
  overridable and the rollout plan in
  `docs/engineering/JEV_HEADER_MAPPING.md` says how to validate them.

## Addendum (2026-09-28): the file's CTE when the upload declares none

**Context.** The upload UI never sends `cte_type`, and RegEngine's own CSV
templates have no CTE column, so every row of a filled-in template uploaded
from the UI is rejected with `No CTE type`.

**Decision.** A second question set (`services/shared/jev/cte_classification.py`,
`csv-file-cte.v1`) asks one `Choice` over the seven FDA CTEs plus
`mixed_or_unclear`, from the header row, only when the upload declares no
CTE and has no per-row CTE column. The same principles as above apply:

- Advisory by default. The answer is returned on the response and in the
  400 body, and the upload UI offers it as a one-click re-upload with
  `cte_type` set; the uploader's click is the decision.
- Applied by code only behind its own switch
  (`REGENGINE_JEV_APPLY_FILE_CTE_TYPE`), only in the `auto_apply` band and
  at or above the artifact human-review threshold, only when it names one
  CTE, and only when no row names a different CTE. A row's own CTE always
  wins.
- Recorded as an advisory `field_mapping_suggestion` artifact targeting
  `cte_type`, reusing the existing artifact type (the `artifact_type` CHECK
  constraint is unchanged).
- No new data category leaves the process: the header row, plus the same
  redacted samples only where enabled. The request is now also made for a
  file whose columns are all recognised, when it declares no CTE.

**Alternative considered.** Inferring the CTE from CTE-specific date
columns (`receive_date` means receiving) deterministically. It would cover
RegEngine's templates without a vendor, but it is a product decision about
accepting files that declare nothing, and it does not cover supplier
exports. Left open; the advisory answer and the UI prompt keep a human in
the loop either way.

## Amendment (2026-10-03): request size and option order

Reviewed against the current TypeSafe documentation (SDK 0.7.2, model
`jev-1.13.0`; no SDK 1.x exists). Two changes:

* **Request size.** TypeSafe caps a request at 64k tokens. Header-mapping
  questions carry the full vocabulary (~1.8k tokens each), so uploads with
  more than ~35 unrecognised columns were rejected and got no suggestions.
  Columns are now sent in batches under ~40k tokens
  (`csv-header-mapping.v3`).
* **Option order.** Jev 1.13 leans toward the first option of a `Choice`.
  An answer may change rows only if it also holds with the options
  reversed: the file-CTE question carries a reversed twin in the same
  request (`csv-file-cte.v2`); header mappings get a second request, only
  for answers about to be applied. A missing or different reversed answer
  leaves rows unchanged (`order_check_unavailable`, `order_inconsistent`).

Everything else already matched the vendor guidance and is unchanged: the
pinned model, fail-open client with bounded retries, `no_match` and
`mixed_or_unclear` options, structured `what`/`not_for`/`examples`
criteria, all questions for one state in one request, and confidence-banded
policy in code.

## Addendum 2026-10-19: model pin moved to `jev-1.14.0`

Decision 5 pinned `jev-1.13.0`. The pin is now `jev-1.14.0`
(`DEFAULT_MODEL` in `services/shared/jev/settings.py`), and the client now
rejects a response whose model differs from the pin
(`unavailable:invalid_response`, fail-open) unless the pin is `jev-latest` or
`jev-preview`.

`scripts/jev_eval.py` was re-run on both models against the same 22 cases
before the change. Thresholds are unchanged (auto-apply 0.90, review 0.50):
nothing applied was wrong at 0.90 on either model, and the highest-confidence
wrong field answer fell from 0.88 to 0.77. The numbers are in the
"Calibration record" of `docs/engineering/JEV_HEADER_MAPPING.md`.
