# Design Partner Proof Checklist

Last updated: June 7, 2026
Owner: founder / product
Status: active proof plan, not evidence of traction by itself

## Purpose

This checklist converts the current diligence gaps into measurable proof. It should be used before any investor, buyer, or public claim that RegEngine has moved beyond pre-production product proof.

RegEngine may claim a proof point only when the evidence named below exists and is linked from the relevant deal notes, demo notes, or data-room packet.

## Current Truth

- RegEngine is pre-production.
- No paid customer claim is verified from this repository.
- Founding design partners are the current commercial target.
- Synthetic proof surfaces demonstrate product behavior, not live customer ROI.
- SOC 2, penetration testing, and enterprise procurement artifacts are in preparation unless a completed third-party report is available outside the repo.

## Proof Gates

| Gate | Required proof | Acceptance bar | Evidence location |
| --- | --- | --- | --- |
| Design-partner participation | Named company, role, workflow owner, and permission to use anonymized findings | 3 design partners complete one guided session | Outreach tracker, session notes, signed/emailed participation confirmation |
| Realistic data path | Real or production-like supplier/ERP input enters Inflow Workbench | At least 1 supplier feed per design partner, with source type noted: CSV, EDI, EPCIS, ERP export, spreadsheet, or email-derived file | Workbench run ID, sanitized input hash, demo/session notes |
| Readiness improvement | Baseline and post-fix readiness scores | Each design partner has at least 2 runs showing either score improvement or a documented reason the score cannot improve yet | Workbench readiness snapshots, fix queue export, dashboard screenshot |
| Fix queue utility | Fixes are created, assigned, corrected, or accepted | At least 5 real fix items across all partners, with status movement after founder/operator follow-up | Fix queue export or screenshots, session scorecard |
| Commit-gate risk reduction | Invalid data is blocked before `production_evidence` | At least 1 blocked commit-gate decision per messy feed, with human-readable reason | Workbench run details, commit decision ID, audit note |
| Export turnaround | Validated records produce an FDA-ready export package | Measure start time, export completion time, row count, and manifest/checksum verification for each successful run | FDA export ZIP, manifest, verifier output, session notes |
| Repeat usage | Partner returns after the first demo | 2 partners complete a second session or submit a second file within 30 days | Outreach tracker, calendar notes, Workbench run IDs |
| Procurement readiness | Buyer can review a trust packet without overclaims | Packet includes DPA, security posture, incident response, DR/RTO/RPO posture, SOC 2 status, and pentest status with clear caveats | Data-room packet, trust page link, deal notes |

## Metrics To Capture

| Metric | Definition | Why it matters |
| --- | --- | --- |
| Time to first successful preflight | Minutes from opening the session to first Workbench result | Shows onboarding friction |
| Readiness delta | Latest readiness score minus first readiness score for the same feed or supplier lane | Shows whether Inflow creates measurable data-quality progress |
| Open blocker count | Count of `blocked` fix items after a run | Shows unresolved operational risk |
| Fix closure rate | Corrected or accepted fix items divided by all fix items for the partner | Shows workflow value beyond diagnostics |
| Commit-gate block count | Count of rejected `production_evidence` transitions | Shows audit-risk prevention |
| Export turnaround | Minutes from validated run to completed FDA export package | Candidate killer metric |
| Export verification result | Pass/fail from public or local verifier | Shows evidence integrity |
| Second-session rate | Partners with a second session divided by partners with a first session | Shows workflow pull |

## Minimum Evidence Packet

For each design partner, collect:

- Partner summary: company type, role/title, covered product category, and buyer/champion distinction.
- Input summary: source type, row/event count, CTE types represented, and sanitized input hash.
- Baseline result: readiness score, blocker count, top missing KDEs, and commit-gate decision.
- Follow-up result: corrected readiness score, fix queue status changes, and remaining blockers.
- Export result: export format, row count, generated timestamp, package manifest, and verification outcome.
- Operator notes: what was confusing, what the partner expected, what they would need for a paid pilot.
- Trust review notes: security/procurement objections raised and how they were answered.

Do not store raw customer files in the repo. Use sanitized summaries, hashes, screenshots with sensitive fields redacted, and links to the approved customer evidence location.

## Claim Rules

Allowed after product-only proof:

- "RegEngine can demonstrate the Inflow-to-evidence loop on synthetic or production-like data."
- "The Workbench surfaces readiness, fix queue items, and commit-gate reasons before evidence commit."
- "Export integrity can be verified from generated packages."

Allowed only after design-partner evidence exists:

- "Design partners used RegEngine to identify supplier data gaps."
- "Readiness improved across repeated submissions."
- "RegEngine reduced export preparation time in pilot sessions."

Not allowed until separately verified:

- "Paying customers."
- "SOC 2 certified."
- "Penetration tested."
- "FDA certified" or "FDA approved."
- "Guaranteed compliance."
- "Production SLA" unless backed by a signed contract and measured operational history.

## Procurement Packet Checklist

Use the following packet for buyer review. Mark each item as current, draft, or unavailable.

| Item | Current repo source | Required caveat |
| --- | --- | --- |
| Security posture | `SECURITY.md`, `SECURITY_BOUNDARIES.md`, `docs/security/TRUST_FRAMEWORK.md` | Code posture, not third-party certification |
| DPA | `docs/DATA_PROCESSING_AGREEMENT.md` | Template until executed with customer counsel |
| Incident response | `docs/operations/INCIDENT_RESPONSE.md`, `docs/runbooks/incident-response.md` | Internal runbook unless tested with a partner |
| Disaster recovery / RTO / RPO | `docs/operations/DISASTER_RECOVERY.md`, `docs/runbooks/disaster-recovery.md` | Targets and procedures; confirm latest tested restore status |
| SOC 2 | `docs/security/SOC2_CONTROL_MATRIX.md`, `docs/security/soc2_preparation.md` | Preparation only unless audit report exists |
| Penetration test | `docs/security/PENTEST_SCOPE.md` | Scope template only unless completed report exists |
| FDA export proof | `frontend/public/sdk/verify_chain.py`, proof/export package | Product proof, not FDA endorsement |

## Operating Loop

1. Run the Inflow Workbench design-partner demo with one realistic messy file.
2. Save the Workbench run and capture the run ID, readiness score, blocker count, and commit-gate decision.
3. Assign or discuss the top fix item with the partner.
4. Replay the corrected feed or document why correction is blocked.
5. Generate and verify an export package only after the run is valid for evidence.
6. Record whether the partner will submit a second file, invite another stakeholder, or discuss a paid pilot.
7. Update the proof gate table before using the session in investor or buyer material.

## Operating Templates

- `sales/design_partner_outreach_tracker_template.csv` tracks prospects, stage, latest Workbench metrics, repeat usage, and procurement status.
- Active tracker copies live under `sales/local/` because prospect notes can contain contact data.
- `sales/design_partner_feedback_scorecard.md` captures each session against the proof gates.
- `sales/design_partner_evidence_packet_template.md` rolls session evidence into one partner-level packet.
- `sales/procurement_trust_packet_template.md` gives buyers a trust packet without SOC 2, pentest, FDA, or SLA overclaims.

## Recommended Next Action

Start with three design-partner sessions focused on one wedge:

Mid-market fresh-cut processor QA/compliance teams using supplier CSV, EDI, or ERP-export data that is incomplete enough to create fix queue work.

The first measured claim to earn is:

"RegEngine improves supplier-data readiness before evidence commit."
