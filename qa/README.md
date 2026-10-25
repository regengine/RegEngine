# QA Pipeline

## Non-Negotiables

These checks **block merge**. No exceptions, no softening.

| Rule | Check | Script |
|---|---|---|
| FSMA 204 CTE count | Fails if fsma-204/page.tsx says 6 CTEs or doesn't state 7 | `fsma-cte-count-check.js` |
| No hardcoded credentials | No API keys, JWTs, or AWS keys in source | `frontend-security-scan.js` |
| Bad data rejection | Invalid CTEs blocked, empty lot codes rejected | `bad-data.js` |

## Regression Patterns (must always fail)

These are the canonical "known bad" cases. If any of these ever passes, the pipeline is broken.

| Case | What breaks | Expected result |
|---|---|---|
| Add hardcoded API key to source | Credential scan | `frontend-security-scan.js` exits 1 |
| Submit row with empty lot code | Bad data validator | `bad-data.js` exits 1 |

## Pipeline Stages

```
fast-gate          → unit tests + FSMA compliance + tenant isolation
  ↓
system-sim         → full flow + bad data + export validation
  ↓
ai-analysis        → regulatory precision + pricing + competitive claims
  ↓
decision           → aggregates fast-gate + system-sim, blocks deploy on failure
```

## Branch Protection (main)

- Required checks: Fast Gate, System Simulation, AI Content Analysis, Deploy Decision
- Strict status checks: enabled
- Enforce admins: yes
- Force pushes: blocked
- Stale review dismissal: enabled

## Running Locally

```bash
node qa/frontend-security-scan.js        # 15 checks
node qa/bad-data.js           # 18 checks
node qa/ai-analysis.js        # 7 checks + warnings
node qa/decision.js           # requires FAST_GATE_RESULT and SYSTEM_SIM_RESULT env vars
```

## Drill History

| Date | Drill | Result | PR |
|---|---|---|---|
| 2026-03-19 | Tampered Merkle hash + "6 CTEs" regression | Blocked (Fast Gate failed, Decision failed, merge blocked) | #157 |
