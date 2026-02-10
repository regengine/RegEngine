# Agent Output Schema

> Every agent in the Fractal Agent Swarm must produce structured output conforming to this schema.
> This enables automated validation, CI integration, and chain orchestration.

## JSON Schema

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "AgentOutput",
  "type": "object",
  "required": ["agent", "task", "timestamp", "status", "confidence", "files_changed", "tests"],
  "properties": {
    "agent": {
      "type": "string",
      "description": "Persona name (e.g., Bot-FSMA)",
      "enum": ["Bot-FSMA", "Bot-PCOS", "Bot-Security", "Bot-Infra", "Bot-UI", "Bot-Energy", "Bot-Health", "Bot-Aero", "Bot-QA"]
    },
    "task": {
      "type": "string",
      "description": "Brief description of the task performed"
    },
    "timestamp": {
      "type": "string",
      "format": "date-time"
    },
    "status": {
      "type": "string",
      "enum": ["completed", "completed_with_warnings", "blocked", "handoff", "failed"]
    },
    "confidence": {
      "type": "number",
      "minimum": 0.0,
      "maximum": 1.0,
      "description": "Agent's confidence in the quality of its output"
    },
    "files_changed": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["path", "action"],
        "properties": {
          "path": { "type": "string" },
          "action": { "type": "string", "enum": ["created", "modified", "deleted"] },
          "lines_added": { "type": "integer" },
          "lines_removed": { "type": "integer" }
        }
      }
    },
    "tests": {
      "type": "object",
      "required": ["added", "all_passing"],
      "properties": {
        "added": { "type": "integer" },
        "modified": { "type": "integer" },
        "all_passing": { "type": "boolean" },
        "coverage_delta": { "type": "string", "description": "e.g., '+2.3%'" }
      }
    },
    "risks": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["severity", "description"],
        "properties": {
          "severity": { "type": "string", "enum": ["critical", "high", "medium", "low"] },
          "description": { "type": "string" },
          "mitigation": { "type": "string" }
        }
      }
    },
    "recommendations": {
      "type": "array",
      "items": { "type": "string" }
    },
    "handoff": {
      "type": ["object", "null"],
      "properties": {
        "to_agent": { "type": "string" },
        "priority": { "type": "string", "enum": ["critical", "high", "medium", "low"] },
        "action_required": { "type": "string" }
      }
    }
  }
}
```

## Example Output

```json
{
  "agent": "Bot-FSMA",
  "task": "Implement TLC validation endpoint",
  "timestamp": "2026-02-09T22:15:00Z",
  "status": "completed_with_warnings",
  "confidence": 0.88,
  "files_changed": [
    {"path": "services/graph/app/routers/fsma/validate.py", "action": "created", "lines_added": 145},
    {"path": "services/graph/tests/test_fsma_validate.py", "action": "created", "lines_added": 210},
    {"path": "shared/schemas.py", "action": "modified", "lines_added": 12, "lines_removed": 0}
  ],
  "tests": {
    "added": 12,
    "modified": 0,
    "all_passing": true,
    "coverage_delta": "+1.8%"
  },
  "risks": [
    {
      "severity": "medium",
      "description": "New endpoint accepts TLC strings — needs IDOR review",
      "mitigation": "Handoff to Bot-Security for review"
    }
  ],
  "recommendations": [
    "Add rate limiting to the new endpoint",
    "Consider caching TLC lookups for performance"
  ],
  "handoff": {
    "to_agent": "Bot-Security",
    "priority": "high",
    "action_required": "Review for IDOR vulnerabilities and tenant isolation"
  }
}
```

## Validation Rules

1. **`agent` must match an active persona** in `.agent/personas/`.
2. **`status: blocked`** requires at least one `risk` with `severity: critical`.
3. **`handoff` is required** if `status` is `handoff`.
4. **`handoff: null`** is required if `status` is `completed` (chain terminates).
5. **`tests.all_passing` must be `true`** for `status: completed`. If tests fail, status must be `failed` or `blocked`.
6. **`confidence < 0.7`** triggers automatic handoff to Bot-QA for validation.
