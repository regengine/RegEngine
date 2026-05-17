# Agent Artifact Specification

Version: `agent-artifact.v1`

This contract defines the advisory output language for FSMA agents. Agent
artifacts may explain, suggest, summarize, or route work for review. They do
not mutate canonical evidence records, rule evaluations, hash chains, or FDA
export artifacts.

## Contract Rules

- Every artifact uses `AgentArtifact` from `services/shared/agent_artifacts.py`.
- Every artifact must include at least one traceability anchor in `context`:
  `evidence_ids`, `canonical_event_ids`, `ingestion_run_id`, or `source_hashes`.
- `source_hashes` must be SHA-256 hex strings.
- `rule_id` and `rule_version` must be provided together.
- `confidence` must be between `0.0` and `1.0`.
- `confidence < 0.85` requires `requires_human_review=true`.
- `artifact_type` must match the payload shape.
- Unknown fields are rejected on the envelope, context, and payload models.

## Artifact Types

`field_mapping_suggestion`
: Suggests how source fields map to canonical FSMA fields.

`identity_match_suggestion`
: Suggests possible canonical entity matches for deterministic review.

`validation_explanation`
: Explains a deterministic rule evaluation and remediation path.

`review_routing_suggestion`
: Suggests which human review queue should receive the item.

`export_readiness_summary`
: Summarizes whether existing evidence appears ready for export.

## Example

```json
{
  "artifact_id": "11111111-1111-4111-8111-111111111111",
  "artifact_version": "agent-artifact.v1",
  "artifact_type": "field_mapping_suggestion",
  "tenant_id": "22222222-2222-4222-8222-222222222222",
  "created_at": "2026-05-13T12:00:00Z",
  "agent_name": "fsma-contract-agent",
  "agent_version": "1.0.0",
  "model_name": "gpt-5",
  "suggestion": "Map Supplier TLC to traceability_lot_code.",
  "confidence": 0.92,
  "requires_human_review": false,
  "context": {
    "evidence_ids": [],
    "canonical_event_ids": [],
    "ingestion_run_id": null,
    "source_hashes": [
      "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
    ],
    "rule_id": "fsma-receiving-tlc-source",
    "rule_version": 1,
    "citation_reference": "21 CFR 1.1345(b)(3)",
    "request_id": "req-test-001"
  },
  "payload": {
    "source_field": "Supplier TLC",
    "source_value": "LOT-123",
    "target_canonical_field": "traceability_lot_code",
    "normalized_value": "LOT-123",
    "rationale": "The supplier column carries the traceability lot code."
  }
}
```

Non-Python consumers should validate against
`data-schemas/events/agent.artifact.schema.json`.
