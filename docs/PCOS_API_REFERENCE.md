# PCOS API Reference

## Overview

The Production Compliance Operating System (PCOS) provides a comprehensive REST API for entertainment production compliance management.

**Base Path**: `/pcos`  
**Authentication**: API Key header or Bearer token

---

## Budget Endpoints

### POST /projects/{project_id}/budgets
Upload and create a new budget for a project.

### GET /projects/{project_id}/budgets
List all budgets for a project.

### GET /budgets/{budget_id}
Get budget details with line items.

### POST /budgets/{budget_id}/validate-rates
Validate line items against union rate tables.

### GET /budgets/{budget_id}/rate-checks
Get stored rate validation results.

### GET /budgets/{budget_id}/fringe-analysis
Analyze fringe costs and detect shortfalls.

---

## Tax Credit Endpoints

### GET /projects/{project_id}/tax-credits
Analyze eligibility for CA Film Tax Credit.

---

## Form Generation Endpoints

### GET /projects/{project_id}/forms/filmla
Generate FilmLA permit application auto-fill data.

---

## Classification Endpoints

### POST /engagements/{engagement_id}/classify
Run ABC Test worker classification analysis.

**Response**:
```json
{
  "overall_result": "contractor",
  "overall_score": 75,
  "confidence": "high",
  "risk_level": "low",
  "prong_a": { "passed": true, "score": 80 },
  "prong_b": { "passed": true, "score": 70 },
  "prong_c": { "passed": true, "score": 75 },
  "recommended_action": "Document independence factors"
}
```

### GET /engagements/{engagement_id}/classification
Get stored classification result.

---

## Paperwork Endpoints

### GET /projects/{project_id}/paperwork-status
Get document completion status for all engagements.

**Response**:
```json
{
  "overall_completion_pct": 75.5,
  "total_docs": 24,
  "total_received": 18,
  "total_pending": 6,
  "engagements": [...]
}
```

---

## Visa Endpoints

### GET /people/{person_id}/visa-timeline
Get visa status with expiration warnings.

---

## Compliance Snapshot Endpoints

### POST /projects/{project_id}/compliance-snapshots
Create a point-in-time compliance snapshot.

**Query Params**:
- `snapshot_type`: manual, pre_greenlight, scheduled
- `snapshot_name`: Optional display name

### GET /projects/{project_id}/compliance-snapshots
List snapshots for a project.

### GET /compliance-snapshots/{snapshot_id}
Get snapshot details.

**Query Params**:
- `include_evaluations`: Include rule evaluation details (default: false)

### GET /compliance-snapshots/{snap1}/compare/{snap2}
Compare two snapshots.

---

## Audit Pack Endpoints

### GET /projects/{project_id}/audit-pack
Generate comprehensive audit pack.

**Query Params**:
- `snapshot_id`: Use specific snapshot (default: latest)
- `include_evidence`: Include evidence inventory (default: true)
- `include_budget`: Include budget summary (default: true)

---

## Attestation Endpoints

### POST /compliance-snapshots/{snapshot_id}/attest
Attest to a compliance snapshot.

**Query Params**:
- `attestation_notes`: Optional notes

---

## Audit Event Endpoints

### GET /projects/{project_id}/audit-events
List audit events for a project.

**Query Params**:
- `event_type`: Filter by type (attestation, gate_transition, etc.)
- `limit`: Max results (default: 50)

---

## Health Check

### GET /health
PCOS module health check.

```json
{
  "status": "healthy",
  "module": "Production Compliance OS",
  "version": "1.0.0"
}
```
