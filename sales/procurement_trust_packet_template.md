# Procurement Trust Packet Template

Status: template
Audience: design partner, buyer, procurement, security review

Use this when a prospect asks whether RegEngine is ready for enterprise review. The goal is to be useful without overclaiming.

## Cover Note

RegEngine is a pre-production FSMA 204 traceability evidence system. The current buyer packet describes implemented controls, operating runbooks, and planned certification work. It does not claim SOC 2 certification, completed penetration testing, FDA approval, or production SLAs unless separate executed evidence is attached.

## Packet Index

| Item | Status | Source | Caveat |
| --- | --- | --- | --- |
| Security policy | Current | `SECURITY.md` | Vulnerability disclosure posture, not a third-party audit |
| Security boundaries | Current | `SECURITY_BOUNDARIES.md` | Engineering boundary policy |
| Trust framework | Current / needs review | `docs/security/TRUST_FRAMEWORK.md` | Verify claims against current code before external use |
| DPA | Draft/template | `docs/DATA_PROCESSING_AGREEMENT.md` | Needs customer counsel review and execution |
| Incident response | Current internal runbook | `docs/operations/INCIDENT_RESPONSE.md` | Exercise status must be stated separately |
| Disaster recovery | Current target/runbook | `docs/operations/DISASTER_RECOVERY.md` | RTO/RPO are targets unless tested evidence is attached |
| SOC 2 control matrix | Preparation | `docs/security/SOC2_CONTROL_MATRIX.md` | Not a SOC 2 report |
| SOC 2 preparation checklist | Preparation | `docs/security/soc2_preparation.md` | Gap list, not certification |
| Pentest scope | Template | `docs/security/PENTEST_SCOPE.md` | Not a completed pentest |
| FDA export verifier | Product proof | `frontend/public/sdk/verify_chain.py` | Verifies package integrity, not FDA endorsement |

## Standard Answers

### Do you have SOC 2?

Not yet. RegEngine maintains a SOC 2 preparation checklist and control matrix, but should be described as preparation-only unless a signed auditor report is attached.

### Have you completed a penetration test?

Not from repo evidence. RegEngine has an internal penetration-test scope template. Do not claim completion unless a third-party report and remediation status are attached.

### Are you FDA certified or approved?

No. RegEngine can generate and verify FSMA 204 evidence packages, but FDA does not certify this product from the repo evidence.

### What are your RTO and RPO?

Current docs define RTO/RPO targets and recovery procedures. Treat them as operating targets unless the latest restore/failover exercise evidence is attached.

### Can we use our own counsel's DPA?

Yes. The repo includes a DPA template for baseline review, but customer counsel can redline or replace it during procurement.

### Where is customer data stored?

Answer from the current deployment and customer agreement. Do not infer storage location from stale docs. If the deployment target changes, update the packet before sending.

## Evidence To Attach Before Sending

- [ ] Current product description.
- [ ] Security policy and security boundaries.
- [ ] DPA template or customer-provided DPA.
- [ ] Incident response runbook.
- [ ] Disaster recovery/RTO/RPO summary.
- [ ] SOC 2 preparation status.
- [ ] Pentest status.
- [ ] Export/verifier proof package.
- [ ] Contact for security follow-up.

## Buyer-Specific Notes

| Question | Answer given | Follow-up owner | Due date |
| --- | --- | --- | --- |
|  |  |  |  |
