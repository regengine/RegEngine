# RegEngine Incident Response Runbook

## Severity Tiers

### SEV-1: Critical

Production down or data integrity compromised. All users affected, or FSMA 204 compliance capability lost.

**Examples:** API returns 500 for all tenants, database corruption, auth system broken, audit trail integrity violated, Stripe webhooks failing (billing impact).

**Response:** Immediate (< 15 min). Founder directly.

### SEV-2: High

Major feature degraded. Subset of users affected or key workflow broken.

**Examples:** CSV ingestion failing, trace queries timing out for large supply chains, Neo4j connection pool exhausted, compliance score returning stale data.

**Response:** < 1 hour. Founder via Slack/phone.

### SEV-3: Medium

Minor feature issue. Workaround available, no compliance impact.

**Examples:** Dashboard chart not rendering, non-critical background job failing, email delivery delayed, UI cosmetic issues.

**Response:** < 4 hours during business hours. GitHub issue.

### SEV-4: Low

Cosmetic or non-impacting.

**Response:** Next business day. GitHub issue, backlog.

---

## FSMA 204: FDA 24-Hour Records Request

If the FDA issues a records request under FSMA 204 (21 CFR Part 1, Subpart S), RegEngine must produce traceability records within 24 hours. If the system is down during an active request:

1. **This is automatically SEV-1** regardless of scope
2. Check trace query endpoint: `GET /v1/fsma/trace/forward/{tlc}` and `GET /v1/fsma/trace/backward/{tlc}`
3. Check database connectivity (Postgres on Railway, Neo4j for graph)
4. If API is down, export directly via admin endpoint: `GET /v1/fsma/export/fda-request?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
5. If all services are down, query Postgres directly for `supplier_cte_events` table as a last-resort fallback

---

## Diagnostic Checklist

### Railway (Backend Services)

- **Dashboard:** [railway.app/dashboard](https://railway.app/dashboard)
- **Services:** admin-api (:8400), ingestion-service (:8000), compliance-api (:8500), graph-service (:8200)
- **Health checks:** Each service exposes `GET /health`
- **Rollback:** Railway supports instant rollback to previous deploy
- **Logs:** Railway dashboard > service > Logs tab (real-time streaming)
- **Database:** Check Postgres connection pool via Railway metrics, look for `max_connections` exhaustion

### Vercel (Frontend)

- **Dashboard:** [vercel.com](https://vercel.com) > RegEngine project
- **Deployment status:** Check for failed builds or edge function errors
- **Rollback:** Vercel supports instant rollback to any previous deployment
- **Logs:** Vercel dashboard > Deployments > Function logs

### Redis

- **Purpose:** Session storage, JWT key registry, rate limiting, token revocation blocklist
- **Check connection:** Production startup must emit `auth_runtime_ready` with
  `redis_backed=true`. A missing or unreachable Redis backend aborts startup.
- **If Redis is down in production:**
  - Bearer-token revocation checks, refresh/session operations, and key-registry
    reads or mutations fail closed. Authentication uncertainty returns 503; it
    must never fall back to a static signing key or process-local revocation.
  - Invalid privileged/workload authentication also fails closed when its
    shared throttle cannot be evaluated.
  - Do not restore service by enabling an in-memory session store, legacy
    JTI-free tokens, or a static-key verification fallback.
- **JWT registry concurrency:** Registry mutations use an atomic compare-and-set
  over `regengine:jwt:keys`; they do not acquire a persistent Redis mutex. An
  old `regengine:jwt:keys:mutation-lock` key may remain after upgrading from a
  pre-CAS build, but current code ignores it. Remove it only after confirming no
  old application version is running.
- **JWT registry upgrade constraint:** Do not rotate or revoke registry keys
  during a mixed-version rollout. Drain every pre-CAS replica first; those
  builds use unconditional Redis writes and can overwrite a concurrent CAS
  mutation. Confirm the all-current replica set before resuming key changes.

### Neo4j

- **Purpose:** Supply chain graph, trace queries, EPCIS data, compliance scoring
- **If Neo4j is down:**
  - Trace queries (`/v1/fsma/trace/*`) will fail with 500
  - CTE ingestion to Postgres still works
  - Compliance score returns demo/fallback data
  - FDA export from Postgres (`supplier_cte_events`) is unaffected

### Stripe

- **Dashboard:** [dashboard.stripe.com](https://dashboard.stripe.com)
- **Webhook delivery:** Developers > Webhooks > select endpoint > Recent deliveries
- **Webhook endpoint:** `POST /api/v1/billing/webhooks` (signature verified via `STRIPE_WEBHOOK_SECRET`)
- **If webhooks fail:** Stripe retries automatically for up to 72 hours. Check the signing secret hasn't rotated.

### Supabase

- **Purpose:** Optional compatibility integration outside production. Production
  bearer authentication accepts only RegEngine-issued JWTs in the shared
  Redis/JTI/session/token-version revocation domain; it never sends bearer
  tokens to Supabase for validation.
- **If Supabase is down:** Production bearer authentication is unaffected.
  Investigate only explicitly enabled non-production compatibility flows; do
  not introduce a production fallback or bypass to restore them.

---

## Communication Templates

### Internal (Slack/Email)

```
Subject: [SEV-{N}] {Brief description}

What happened: {description}
Impact: {who is affected, what's broken}
Status: {investigating | identified | mitigating | resolved}
ETA: {if known}
Next update: {time}
```

### External (to affected design partners)

```
Subject: RegEngine Service Update

We're aware of an issue affecting {description}.
Our team is actively working on a resolution.
{Workaround if available}
We'll provide an update by {time}.

Contact: support@regengine.co
```

---

## Postmortem Template

After any SEV-1 or SEV-2 incident, create a postmortem within 48 hours in `docs/postmortems/YYYY-MM-DD-title.md`.

```markdown
# [Date] Incident Summary

## Timeline (UTC)
- HH:MM — Issue detected (how: alert / customer report / monitoring)
- HH:MM — Investigation started
- HH:MM — Root cause identified
- HH:MM — Fix deployed
- HH:MM — Monitoring confirmed resolution

## Root Cause
What specifically broke and why.

## Impact
Duration, users affected, data impact, compliance impact.

## Resolution
What was done to fix it.

## Prevention
What changes will prevent recurrence.
- [ ] Action item 1 (owner, deadline)
- [ ] Action item 2 (owner, deadline)
```
