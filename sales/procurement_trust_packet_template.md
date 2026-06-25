# Procurement Trust Packet Template

Status: template
Audience: design partner, buyer, procurement, security review

Use this when a prospect asks whether RegEngine is ready for enterprise review. The goal is to be useful without overclaiming.

## Cover Note

RegEngine is a pre-production FSMA 204 traceability evidence system. The current buyer packet describes implemented controls, operating runbooks, and certification-readiness materials. It does not claim SOC 2 certification, a certification timeline, completed penetration testing, FDA endorsement, or public availability commitments unless separate executed evidence is attached.

## Packet Index

| Item | Status | Source | Caveat |
| --- | --- | --- | --- |
| Security policy | Current | `SECURITY.md` | Vulnerability disclosure posture, not a third-party audit |
| Security boundaries | Current | `SECURITY_BOUNDARIES.md` | Engineering boundary policy |
| Trust claims matrix | Current control sheet | `docs/security/TRUST_CLAIMS_MATRIX.md` | Use this before drafting buyer-facing claims |
| Trust framework | Internal draft / needs review | `docs/security/TRUST_FRAMEWORK.md` | Do not send externally without scrub against the claims matrix |
| DPA | Public summary plus draft/template | `/dpa`, `docs/DATA_PROCESSING_AGREEMENT.md` | Executed agreement controls |
| Incident response | Current internal runbook | `docs/operations/INCIDENT_RESPONSE.md` | Exercise status must be stated separately |
| Disaster recovery | Current target/runbook | `docs/operations/DISASTER_RECOVERY.md` | RTO/RPO are targets unless tested evidence is attached |
| SOC 2 control matrix | Preparation | `docs/security/SOC2_CONTROL_MATRIX.md` | Not a SOC 2 report |
| SOC 2 preparation checklist | Preparation | `docs/security/soc2_preparation.md` | Gap list, not certification |
| Pentest scope | Template | `docs/security/PENTEST_SCOPE.md` | Scope template only; no completed assessment claimed |
| FDA export verifier | Product proof | `frontend/public/sdk/verify_chain.py` | Verifies package integrity, not FDA endorsement |
| Commercial terms | Contract-only | Order form / design-partner agreement | Pricing, renewals, add-ons, taxes, and plan changes are controlled by executed terms |
| Integration scope | Contract-only | Integration appendix or implementation estimate | Named vendor/retailer workflows require scope confirmation and evidence review |
| Public availability status | Current posture | `/trust`, `docs/security/TRUST_CLAIMS_MATRIX.md` | Pre-production/design-partner posture; no public service-level commitment |
| Subprocessor/data residency | Current list plus executed DPA | `/dpa`, `frontend/src/lib/trust-subprocessors.ts` | Verify current deployment region before sending |
| Tested DR evidence | Request/NDA | Latest restore/failover exercise notes | Attach only if completed and approved |

## Standard Answers

### Do you have SOC 2?

Not yet. RegEngine maintains a SOC 2 preparation checklist and control matrix, but should be described as preparation-only unless a signed auditor report is attached.

### Have you completed a penetration test?

Not from repo evidence. RegEngine has an internal penetration-test scope template. Do not claim completion unless a third-party report and remediation status are attached.

### Do you have FDA certification or endorsement?

No. RegEngine can generate and verify FSMA 204 evidence packages, but FDA endorsement is not claimed from repo evidence.

### What are your RTO and RPO?

Current docs define RTO/RPO targets and recovery procedures. Treat them as operating targets unless the latest restore/failover exercise evidence is attached.

### Can we use our own counsel's DPA?

Yes. The repo includes a DPA template for baseline review, but customer counsel can redline or replace it during procurement.

### Where is customer data stored?

Fill before sending: current default posture is US-default infrastructure with provider-specific locations controlled by the DPA and executed agreement. Do not infer storage location from stale docs. If the deployment target changes, update the packet before sending.

## Evidence To Attach Before Sending

- [ ] Current product description.
- [ ] Trust claims matrix.
- [ ] Security policy and security boundaries.
- [ ] DPA template or customer-provided DPA.
- [ ] Incident response runbook.
- [ ] Disaster recovery/RTO/RPO summary.
- [ ] SOC 2 preparation status.
- [ ] Pentest status.
- [ ] Export/verifier proof package.
- [ ] Order form or design-partner commercial terms.
- [ ] Integration scope statement for named systems.
- [ ] Subprocessor/data-residency evidence current as of send date.
- [ ] Latest approved DR/restore test evidence, if any.
- [ ] Contact for security follow-up.

## Buyer-Specific Notes

| Question | Answer given | Follow-up owner | Due date |
| --- | --- | --- | --- |
|  |  |  |  |
