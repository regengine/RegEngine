# Archived PCOS API Reference

This file described a non-FSMA PCOS surface and is not part of the current product wedge.

Use FSMA references instead:

- `README.md`
- `docs/specs/FSMA_204_MVP_SPEC.md`

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
