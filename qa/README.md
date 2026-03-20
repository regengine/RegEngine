# QA Pipeline

## Non-Negotiables

These checks **block merge**. No exceptions, no softening.

| Rule | Check | Script |
|---|---|---|
| Merkle chain integrity | Every hash cryptographically verified against its predecessor | `fsma-lite-check.js` |
| FSMA 204 CTE count | Must reference 7 CTEs, never 6 | `fsma-lite-check.js` |
| KDE completeness | All required fields present on every event | `fsma-lite-check.js` |
| Cross-format consistency | JSON, CSV, verification report, and manifest must agree on every hash | `full-flow.js` |
| Export artifact presence | All 5 files exist, valid format, correct record counts | `export-validate.js` |
| No hardcoded credentials | No API keys, JWTs, or AWS keys in source | `tenant-test.js` |
| Bad data rejection | Invalid CTEs blocked, empty lot codes rejected | `bad-data.js` |

## Regression Patterns (must always fail)

These are the canonical "known bad" cases. If any of these ever passes, the pipeline is broken.

| Case | What breaks | Expected result |
|---|---|---|
| Tamper any Merkle hash | Chain verification | `fsma-lite-check.js` exits 1, `full-flow.js` exits 1 |
| Change "7 CTEs" to "6 CTEs" in fsma-204/page.tsx | Regulatory copy check | `fsma-lite-check.js` exits 1 |
| Delete any sample artifact file | Export validation | `export-validate.js` exits 1 |
| Add hardcoded API key to source | Credential scan | `tenant-test.js` exits 1 |
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
node qa/fsma-lite-check.js    # 31 checks
node qa/tenant-test.js        # 15 checks
node qa/full-flow.js          # 68 checks
node qa/bad-data.js           # 18 checks
node qa/export-validate.js    # 25 checks
node qa/ai-analysis.js        # 7 checks + warnings
node qa/decision.js           # requires FAST_GATE_RESULT and SYSTEM_SIM_RESULT env vars
```

## Drill History

| Date | Drill | Result | PR |
|---|---|---|---|
| 2026-03-19 | Tampered Merkle hash + "6 CTEs" regression | Blocked (Fast Gate failed, Decision failed, merge blocked) | #157 |
