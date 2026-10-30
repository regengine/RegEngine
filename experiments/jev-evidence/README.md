# Standalone Jev evidence experiment

This experimental package evaluates supplied synthetic evidence with pinned `jev-1.13.0`. It is not imported by the application and does not change production behavior. The decision policy remains uncalibrated.

The final omission-aware prompt preserves all combined prompt criteria and appends a clarification: missing proof is not an incompatible fact, necessary conditions do not imply sufficiency, and an explicitly exhaustive applicable account can establish absence.

## Verified result

| Set | Combined reference | Final omission-aware candidate |
|---|---:|---:|
| Previously exposed regression cases | 33/34 | 34/34 |
| Fresh held-out synthetic cases | 16/16 | 16/16 |

HS04 is corrected to `insufficient`; B02 and B08 retain their correct outcomes. There were no new false decisive verdicts or observed regressions. This is a single-run synthetic result, not evidence of production calibration or repeated-run reliability.

The first attempted revision fixed HS04 but regressed B08 and was rejected. `rejected-v1/` retains its ledger, complete result summary, prompt, and B08 evidence. Original evaluation artifacts remain unchanged in the source delivery bundle. The final candidate is not automatically selected by any application.

## Offline verification

Node >=22.18.0 is required. No dependencies, credentials, installation, or network are needed for tests.

- `npm test`: replays the saved final responses, checks all 34 regression labels, preserves original responses, checks fresh-case acceptance, and mocks runner failures/duplicate protection.
- `npm run preflight`: validates all 100 frozen payloads without dispatch.
- `npm run analyze`: regenerates `results-summary.json` and `results.csv` from saved responses without dispatch.

The repository PR gate runs `npm test` on Node24 for changes to this directory or its workflow. It provides no Jev credentials and makes no model calls.

`run-compare.mjs` is retained as live-run provenance. Its existing exclusive ledger blocks another dispatch in this directory. A new live experiment needs separately authorized budget accounting and a fresh frozen plan; deleting the ledger is not a supported rerun mechanism.

## Evidence and budget

See `REPORT.md`, `results-summary.json`, `results.csv`, `comparison-ledger.json`, and `records/`. Expected labels and rationales are stored separately from transmitted payloads. All inputs are synthetic. All model/threshold/source/prompt hashes are pinned.

Across the original evaluation, earlier prompt comparison, rejected first revision, and final revision: 256 requests; cumulative usage-derived Jev cost $0.011251716; remaining original $1 cap $0.988748284. Invoice debit was not independently verified.
