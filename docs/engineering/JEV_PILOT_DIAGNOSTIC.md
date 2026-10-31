# Jev supplier-file diagnostic preview

Status: local implementation; human review required. This endpoint diagnoses
parser issues without ingesting events, changing records, assigning owners, or
determining regulatory completeness.

## API contract

`POST /api/v1/ingest/csv/diagnostic` accepts multipart `file` (CSV or XLSX),
optional `cte_type`, `tenant_id`, `sheet_name`, and `semantic_review` (default
`false`). It uses the existing CSV router, `webhooks.ingest` permission, and
principal-bound tenant resolution before application file reads, parsing, or Jev.

The existing upload byte limit applies. The preview rejects more than 500 parsed
data records with 413 instead of returning a partial success. XLSX uses the
existing converter with strict scan-limit rejection: a worksheet that cannot be
fully inspected within 20,000 worksheet rows is rejected. Empty worksheet rows
are skipped, and the first nonempty row is the header. The first worksheet is
used unless a sheet name is supplied; other worksheets are outside this preview.
Strict previews ignore declared worksheet dimensions so inaccurate metadata
cannot silently omit stored rows or bypass the record limit.

The response groups canonical parser observations by reason, field, disposition,
and file-level status. Each group includes exact record indices. CSV indices
count parsed records including the header, not physical text lines. XLSX indices
count converted records including the header, not original worksheet rows.
File-level issues have no invented row coordinates. Counts distinguish valid,
rejected, skipped, and unparsed records.

The response always contains `persisted_event_count: 0`,
`automatic_assignment_enabled: false`, and
`regulatory_completeness: "not_determined"`. A valid parsed event can still have
missing KDEs. A clean preview does not establish complete operational records or
compliance.

## Optional semantic review

Explicit `semantic_review=true` enables at most eight aggregate-only Mode A
reviews. The state contains canonical issue and field identifiers, counts,
known CTE types, and explicitly absent evidence context. Raw cell values,
uploaded headers, file names, tenant identifiers, and free-text parser errors
are excluded. All deterministic issue groups remain in the response even when
semantic review is unavailable or capped. The loop stops after the first
unavailable response and marks remaining groups unreviewed.

The shared Jev client's existing disabled/configuration behavior and default
`jev-1.14.0` are unchanged. Strict review validation is opt-in and validates raw
HTTP JSON before the existing SDK normalization. It rejects missing or extra
answers, wrong types, numeric coercion, invalid probability mass, inconsistent
winners, and inconsistent score distributions or legends. Invalid responses are
processing failures, never evidence labels.

Mode B is available as the pure `adjudicate_evidence` policy, with separate
technical polarity and cross-source conflict observations. Callers must establish
authoritative scope outside the model before supported/contradicted verdicts are
eligible. Neither uploaded flags nor model output establishes verification.

Mode A source, origin, effort, and external follow-up suggestions require
independently verified evidence flags. The HTTP endpoint supplies no such flags.
Owner output is always manual triage; candidate probabilities are uncalibrated
model signals. No threshold or environment flag enables automatic assignment.

## Evaluation and release decision

`scripts/jev_review_eval.py` replays exactly 24 preserved historical controls and
separate frozen synthetic holdouts against pinned Jev 1.14.0 and 1.13.0. For
controls, the repeated request changes only Choice option order. Expected labels
and trusted evidence flags are never sent to the provider.

The evaluator defaults to dry run. Live mode requires the runtime credential and
an explicit budget no greater than $1. It uses a fixed HTTPS endpoint, refuses
redirects, records a conservative token-cost reservation before each request,
and never automatically retries an ambiguous send. Completed identical requests
can be skipped; changed requests, missing responses, or ambiguous ledger entries
require investigation. Credentials and provider error bodies are not recorded.

The 2026-10-29 execution used 136 requests and 144,466 recorded input tokens.
Of those responses, 133 passed the strict contract and three from Jev 1.13.0
were rejected. Both models matched all 12 synthetic Mode B holdouts. Gated
historical-control agreement was 19/24 for 1.14.0 and 20/24 for 1.13.0 on the
base requests. Option-order stability was 21/24 for 1.14.0 and 16/22 valid pairs
for 1.13.0, with two rejected reordered responses excluded from that denominator.
All eight valid 1.14.0 Mode A cases matched the expected owner, source, and origin
choices; 1.13.0 matched those choices on seven valid cases and rejected one.
These results do not approve automatic routing or a model-default change.
At the published $0.042 per million input tokens, the estimated batch cost was
$0.006067572. A separate repository-required sidecar reserved at most $0.002688.
These are usage estimates and bounds, not an invoice. Raw responses, frozen
inputs, hashes, threshold analysis, and synthetic CSV/XLSX before/after artifacts
are in the accompanying review package.

The original controls are historical paraphrases and code summaries, not current
production evidence. Three preset labels have document-presence/world-claim
ambiguity. The new holdouts are a small synthetic sanity set, not customer
ground truth. Automatic owner assignment remains disabled pending independent,
customer-confirmed ownership examples and a separately reviewed activation.

## Validation boundary

Focused tests exercise strict malformed-response handling, existing advisory
client compatibility, permission/tenant rejection before file processing,
CSV/XLSX limits (including sparse sheets), replay without persistence, aggregate
privacy, bounded model review, and evaluator budget/timeout safeguards.
Synthetic TestClient demonstrations override authentication and persistence
dependencies. They do not verify live identity infrastructure, database
integration, multi-replica rate limiting, or deployed traffic.
