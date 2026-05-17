# Agent Risk Engine

Version: `agent-risk.v1`

The operator view uses a deterministic risk calculation over validated
`AgentArtifact` data and optional ledger verification flags. The engine is pure:
it performs no database reads, network calls, or time-based logic.

## Formula

```text
risk_score = min(100,
  confidence_risk
  + review_risk
  + artifact_type_risk
  + evidence_gap_risk
  + rule_gap_risk
)
```

Weights:

- `confidence_risk = (1 - confidence) * 40`
- `review_risk = 25` when `requires_human_review=true`, else `0`
- `artifact_type_risk`
  - `identity_match_suggestion`: `20`
  - `field_mapping_suggestion`: `15`
  - `validation_explanation`: `15`
  - `review_routing_suggestion`: `10`
  - `export_readiness_summary`: `25` when `exportable=false`, else `5`
- `evidence_gap_risk = 15` when both `evidence_ids` and
  `canonical_event_ids` are empty
- `rule_gap_risk = 10` when `rule_id/rule_version` is absent

## Compliance Gaps

The V1 engine emits these deterministic gap codes:

- `low_confidence`: `confidence < 0.85`
- `human_review_required`: `requires_human_review=true`
- `missing_evidence_anchor`: no `evidence_ids` and no `canonical_event_ids`
- `missing_rule_reference`: no `rule_id/rule_version`
- `export_blocker`: export readiness summary says `exportable=false`
- `ledger_unlinked`: caller reports no advisory receipt link
- `chain_unverified`: caller reports failed receipt-chain verification

Source of truth: `services/shared/agent_risk_engine.py`.
