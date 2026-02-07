# Incident Response Runbook

## 1. Severity Levels

| Level | Description | Example | Response SLA |
|-------|-------------|---------|--------------|
| **SEV1 (Critical)** | Core system down, Data loss risk, Security breach | API 500s > 10%, Database unreachable | 15 mins |
| **SEV2 (High)** | Major feature broken, Performance degradation | Recall engine failing, Latency > 2s | 1 hour |
| **SEV3 (Medium)** | Minor feature broken, Workaround available | Export CSV failing, Dashboard glitch | 4 hours |
| **SEV4 (Low)** | Cosmetic issue, Non-urgent bug | Typo in UI, Non-critical log warning | 24 hours |

## 2. Escalation Path

### On-Call Engineer (Primary)
*   **Role**: First responder, triage, stabilization.
*   **Actions**: Acknowledge alert, assess severity, initiate Incident Channel.

### Engineering Manager (Secondary)
*   **Role**: Communication handling, resource allocation.
*   **Trigger**: If SEV1/2 not resolved in 30 mins.

### CTO / Legal (Tertiary)
*   **Role**: External communication, compliance/legal assessment.
*   **Trigger**: Confirmed Data Breach or FDA Audit failure risk.

## 3. Incident Lifecycle

### Phase 1: Detection & Triage
1.  **Alert Received**: Via PagerDuty/Slack/Email.
2.  **Verify**: Log into proper environment (Staging/Prod) and confirm issue.
3.  **Declare**:
    *   Open Slack channel `#incident-[date]-[name]`.
    *   Set Topic: "SEV[X] - [Description] - Commander: [Name]"

### Phase 2: Containment & Mitigation
1.  **Stop the Bleeding**:
    *   If bad deploy -> **Rollback**.
    *   If DDoS/Load -> **Enable Rate Limiting / WAF**.
    *   If Logic Bug -> **Feature Flag off**.
2.  **Status Page Update**: "Investigating - We are currently investigating an issue with..."

### Phase 3: Resolution
1.  **Fix**: Apply hotfix or configuration change.
2.  **Verify**: Monitor metrics for stability (wait 10-15 mins).
3.  **Recover**: Replay failed jobs or restore missing data if applicable.

### Phase 4: Post-Mortem
*   **Required for**: All SEV1 and SEV2 incidents.
*   **Timeline**: Within 48 hours of resolution.
*   **Artifact**: `docs/post_mortems/YYYY-MM-DD-incident-name.md`.
*   **Content**: 5 Whys, Timeline, Root Cause, Action Items (preventative).

## 4. Communication Templates

### Public Status Update
> **[Investigating]** We are currently investigating issues with RegEngine [Service]. Users may experience [Symptoms]. Our team is working to identify the root cause.

### Internal Exec Update
> **SEV1 Incident Update**
> *   **Impact**: FSMA Recall Service is unavailable.
> *   **Current Status**: Database failover initiated. Restoring from backup.
> *   **ETA**: ~30 minutes.
> *   **Blockers**: None.

## 5. Key Contacts
*   **DevOps Lead**: [Phone/Email]
*   **Compliance Officer**: [Phone/Email]
*   **Infrastructure Provider (AWS)**: [Support Portal Link]
