# Incident Response Plan

## Purpose

Define RegEngine's process for identifying, containing, and resolving
security incidents. This plan applies to all systems under RegEngine's
control and all personnel with access to production infrastructure.

## Severity Levels

| Level    | Definition                                           | Response Time |
|----------|------------------------------------------------------|---------------|
| Critical | Active exploitation, data breach, production down    | 1 hour        |
| High     | Exploitable vulnerability, no active exploitation    | 4 hours       |
| Medium   | Vulnerability with limited impact or mitigations     | 1 business day|
| Low      | Informational, best-practice deviation               | 5 business days|

## Response Phases

### 1. Detection & Triage
- Monitor: CI security pipeline alerts, ZAP reports, VDP inbox
- Triage: Assign severity level, confirm scope
- Owner: Assign an incident lead (currently CEO for all severities)

### 2. Containment
- Isolate affected systems/tenants
- Revoke compromised credentials or API keys
- Preserve evidence (logs, artifacts, screenshots)

### 3. Eradication
- Identify and fix root cause
- Deploy patch to staging → verify → promote to production
- Update dependencies if supply chain issue

### 4. Recovery
- Restore affected services
- Verify tenant data integrity
- Monitor for recurrence (24–72 hours)

### 5. Post-Incident Review
- Conduct blameless retrospective within 5 business days
- Document: timeline, root cause, response effectiveness, improvements
- Update this plan and CI pipeline as needed

## Communication

| Audience            | Channel                    | Timing              |
|---------------------|----------------------------|----------------------|
| Reporter (via VDP)  | security@regengine.co      | Per VDP SLA         |
| Affected customers  | Email + status page        | Within 24 hours     |
| Internal team       | Slack #security-incidents  | Immediately         |
| Regulatory (if req) | Per applicable regulations | Per legal timeline  |

## Contacts

| Role             | Name                  | Contact                     |
|------------------|-----------------------|-----------------------------|
| Incident Lead    | Christopher Sellers   | security@regengine.co       |
| Backup           | [FILL]                | [FILL]                      |

## Review Cadence

This plan is reviewed quarterly or after any Critical/High incident,
whichever comes first. Last reviewed: 2026-02-06.
