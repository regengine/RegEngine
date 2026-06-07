# Design Partner Feedback Scorecard

Use this scorecard immediately after each design-partner session. It is the source record for the proof gates in `docs/product/DESIGN_PARTNER_PROOF_CHECKLIST.md`.

Do not store raw customer files, private contact data, API keys, tokens, or unredacted operational data in this file. Store sanitized summaries, hashes, run IDs, and links to the approved evidence location.

## Session Header

| Field | Value |
| --- | --- |
| Date | YYYY-MM-DD |
| Company |  |
| Segment | Fresh-cut processor / importer / distributor / co-packer / other |
| Contact role/title |  |
| Buyer role | Economic buyer / champion / user / technical evaluator |
| Covered product category |  |
| Session type | First walkthrough / correction replay / export review / procurement review |
| Evidence owner |  |
| Approved evidence location |  |

## Input Summary

| Field | Value |
| --- | --- |
| Source type | CSV / EDI / EPCIS / ERP export / spreadsheet / email-derived file / synthetic |
| Row or event count |  |
| CTE types represented |  |
| Supplier or lane summary |  |
| Sanitized input hash |  |
| Workbench run ID |  |
| Workbench result hash |  |
| Customer data caveat | Raw file not stored in repo |

## Proof Gate Capture

| Gate | Session result | Evidence link or note |
| --- | --- | --- |
| Design-partner participation | Not captured / captured |  |
| Realistic data path | Synthetic / production-like / real |  |
| Readiness improvement | Not measured / baseline only / improved / blocked |  |
| Fix queue utility | No fixes / fixes created / fixes moved |  |
| Commit-gate risk reduction | Not tested / allowed / blocked |  |
| Export turnaround | Not tested / measured |  |
| Repeat usage | Not asked / scheduled / declined |  |
| Procurement readiness | Not asked / packet sent / objection captured |  |

## Metrics

| Metric | Value |
| --- | ---: |
| Time to first successful preflight, minutes |  |
| Baseline readiness score |  |
| Follow-up readiness score |  |
| Readiness delta |  |
| Open blocker count |  |
| Fix items created |  |
| Fix items corrected or accepted |  |
| Fix closure rate |  |
| Commit-gate block count |  |
| Export turnaround, minutes |  |
| Export row count |  |
| Export verification result | Pass / fail / not run |

## Observed Friction

- Verbatim confusion:
- Error messages seen:
- Where they paused:
- What made the workflow click:
- One thing to improve this week:

## Trust And Procurement Notes

| Topic | Question or objection | Answer given | Follow-up |
| --- | --- | --- | --- |
| SOC 2 |  |  |  |
| Penetration test |  |  |  |
| DPA |  |  |  |
| Incident response |  |  |  |
| DR / RTO / RPO |  |  |  |
| Data ownership / deletion |  |  |  |
| FDA endorsement |  |  |  |

## Claim Eligibility

Mark only claims supported by this session.

- [ ] Partner used RegEngine to identify supplier data gaps.
- [ ] Readiness improved across repeated submissions.
- [ ] Fix queue work moved after partner/operator follow-up.
- [ ] Invalid data was blocked before evidence commit.
- [ ] Export turnaround was measured.
- [ ] Export verification passed.
- [ ] Partner agreed to submit a second file or hold a second session.

## Next Action

One next action only:

- Owner:
- Due date:
- Success condition:
- Follow-up artifact:
