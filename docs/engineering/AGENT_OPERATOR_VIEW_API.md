# Agent Operator View API

Version: `agent-review-item.v1`

The first operator-view endpoint returns persisted advisory agent activity,
linked ingestion-run and receipt metadata, and deterministic risk evaluation in
one read model.

## Endpoint

```http
GET /v1/agent-reviews/items
```

Query parameters:

- `tenant_id`: optional, sysadmin only. Regular operators use their
  authenticated tenant context.
- `ingestion_run_id`: optional UUID filter.
- `review_status`: optional `pending`, `accepted`, `rejected`, or
  `needs_more_evidence`.
- `artifact_type`: optional AgentArtifact type.
- `created_after`: optional ISO timestamp.
- `created_before`: optional ISO timestamp.
- `limit`: default `50`, max `200`.
- `offset`: default `0`.

The endpoint is read-only. It resolves a tenant context before querying and
continues to rely on Postgres RLS for tenant isolation.

## Response

```json
{
  "items": [
    {
      "artifact_id": "11111111-1111-4111-8111-111111111111",
      "tenant_id": "22222222-2222-4222-8222-222222222222",
      "artifact_type": "field_mapping_suggestion",
      "created_at": "2026-05-13T15:00:00Z",
      "agent_name": "fsma-risk-agent",
      "suggestion": "Map Supplier TLC to traceability_lot_code.",
      "confidence": 0.82,
      "requires_human_review": true,
      "review_id": null,
      "review_status": "pending",
      "reviewed_by": null,
      "reviewed_at": null,
      "risk_score": 72.2,
      "risk_breakdown": {
        "score": 72.2,
        "uncapped_score": 72.2,
        "confidence_risk": 7.2,
        "review_risk": 25.0,
        "artifact_type_risk": 15.0,
        "evidence_gap_risk": 15.0,
        "rule_gap_risk": 10.0
      },
      "compliance_gap_count": 4,
      "compliance_gaps": [
        {
          "code": "low_confidence",
          "message": "Artifact confidence is below the human-review threshold (0.85)."
        }
      ],
      "ingestion_run_id": "33333333-3333-4333-8333-333333333333",
      "ingestion_run_status": "processing",
      "source_system": "csv_upload",
      "source_file_name": "receiving.csv",
      "advisory_receipt_id": "44444444-4444-4444-8444-444444444444",
      "advisory_receipt_state": "needs_review",
      "receipt_hash": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
      "chain_valid": true,
      "evidence_ids": [],
      "canonical_event_ids": [],
      "source_hashes": [
        "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
      ],
      "rule_id": null,
      "rule_version": null
    }
  ],
  "total": 1,
  "limit": 50,
  "offset": 0
}
```

Source of truth:

- Contract and retrieval: `services/shared/agent_operator_view.py`
- Endpoint: `services/admin/app/agent_review_routes.py`
- Risk math: `services/shared/agent_risk_engine.py`
