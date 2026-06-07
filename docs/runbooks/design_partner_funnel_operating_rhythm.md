# Design-Partner Funnel Operating Rhythm

This runbook defines a daily loop for demo -> feedback -> iterate using live funnel metrics.

## Objective
Move design partners through the stage sequence with minimal delay:
`signup_completed -> first_ingest -> first_scan -> first_nlp_query -> checkout_started -> payment_completed`

## Source of Truth
- Endpoint: `GET /v1/admin/funnel`
- Service: admin API
- Required access: authenticated user with `admin.funnel.read`

## Daily 20-Minute Routine (Mon-Fri)

### Step 1: Pull current funnel snapshot
```bash
curl -sS "$ADMIN_API_URL/v1/admin/funnel" \
  -H "Authorization: Bearer $ADMIN_ACCESS_TOKEN" \
  -H "Content-Type: application/json"
```

Optional pretty-print:
```bash
curl -sS "$ADMIN_API_URL/v1/admin/funnel" \
  -H "Authorization: Bearer $ADMIN_ACCESS_TOKEN" | jq
```

### Step 2: Record counts and conversion deltas
Track every stage count plus `conversion_from_previous_pct` in a daily log.

Recommended table columns:
- date
- stage
- count
- conversion_from_previous_pct
- delta_vs_yesterday
- owner
- action

### Step 3: Apply decision rules
Use these default triggers to decide what to fix first.

| Stage transition | Trigger | Immediate action |
|---|---|---|
| signup_completed -> first_ingest | conversion < 45% for 2 days | Tighten onboarding email and add "first ingest" concierge outreach for new signups. |
| first_ingest -> first_scan | conversion < 60% for 2 days | Improve scan onboarding and verify QR sample assets are easy to access. |
| first_scan -> first_nlp_query | conversion < 55% for 2 days | Add in-product prompt for "Ask traceability" after successful scan. |
| first_nlp_query -> checkout_started | conversion < 30% for 3 days | Update demo close script and pricing objection handling. |
| checkout_started -> payment_completed | conversion < 70% for 1 day | Audit Stripe flow, failed invoices, and payment method UX. |

### Step 4: Create one daily priority
Pick exactly one bottleneck transition and open one fix task with:
- expected funnel impact
- owner
- deadline (<= 48 hours)
- validation metric (which conversion should improve)

## 72-Hour Win Mode

Use this mode when RegEngine needs one visible improvement fast. It does not replace
the weekly OKR in `docs/decisions/2026-05-13-okr.md`; it is the short-cycle loop for
moving one funnel transition that should increase the chance of a pilot ingesting a
real CTE event this week.

### Entry criteria
- One target metric is named before work starts.
- The target metric maps to one funnel transition above or to the weekly pilot-ingest
  query in `scripts/okr_pilots_ingesting_weekly.sql`.
- The work uses the existing agent roles from `docs/engineering/AGENT_OPERATING_MODEL.md`:
  `planner`, `implementer`, and `security_review`. Do not create new agent role
  directories, autonomous chains, or scheduled agent jobs for this mode.
- The work has one accountable human owner for product judgment and prospect follow-up.

### Day 0: Pick the constraint
Within the first two hours:
1. Pull the latest `GET /v1/admin/funnel` snapshot.
2. Identify the single worst transition by conversion loss and business impact.
3. Write a one-sentence win statement:
   `By <date>, improve <transition> from <baseline> to <target> by shipping <smallest change>.`
4. Open one GitHub issue with:
   - baseline metric
   - target metric
   - affected route, screen, copy path, runbook, or outreach asset
   - owner
   - validation command or measurement source
   - explicit out-of-scope list

### Day 1: Ship the smallest useful fix
- `planner` verifies the current behavior from repo files, tests, and docs before
  implementation starts.
- `implementer` opens one scoped PR. Prefer a product, onboarding, funnel, or operator
  workflow fix over broad cleanup.
- Add or update tests when code changes behavior. Security-critical changes, including
  auth, tenant isolation, billing, permits, receipts, audit logs, compliance evidence,
  secrets, deployment, and tool execution, need negative-path tests.
- `security_review` reviews any security-critical change before merge.

### Day 2: Close the loop with prospects or pilots
- Contact the affected prospect, pilot, or user segment with the smallest possible ask:
  schedule, retry the blocked action, send one file, confirm one objection, or answer one
  pricing/procurement question.
- Record the response in the issue or the relevant outreach tracker.
- If the response shows the chosen constraint was wrong, stop expanding the fix and
  update the issue with the new constraint.

### Day 3: Decide continue, rollback, or redirect
- Re-read the funnel transition and, when relevant, run:
  `psql "$DATABASE_URL" -f scripts/okr_pilots_ingesting_weekly.sql`
- Close the loop in the issue with shipped change, metric result, and next action.
- Continue only if the metric or qualitative pilot evidence improved.
- Roll back or redirect if the change added complexity without moving the named metric.

### Non-goals
- Do not pursue more than one KPI in the same 72-hour cycle.
- Do not convert one prospect comment into a roadmap item unless it repeats across three
  pilots or blocks the current pilot-ingest OKR.
- Do not use this mode for speculative refactors, internal polish, or new agent framework
  work.

## Weekly 45-Minute Review (Friday)

### Agenda
1. Compare week-over-week conversion by stage.
2. List top three repeated blockers from scorecards.
3. Confirm which shipped changes moved conversion.
4. Decide next week's one growth experiment and one product fix.

### Weekly output artifact
A one-page summary containing:
- stage counts and conversions
- blocker themes
- wins/losses
- next week's actions

## Demo-to-Feedback Loop Integration
After every design-partner demo:
1. Update `sales/design_partner_outreach_tracker_template.csv` row.
2. Complete `sales/design_partner_feedback_scorecard.md`.
3. Start or update `sales/design_partner_evidence_packet_template.md` when real or production-like data was used.
4. Send `sales/procurement_trust_packet_template.md` only when a buyer asks for security/procurement review; keep SOC 2, pentest, FDA, and SLA caveats intact.
5. Re-check funnel progress for that tenant within 24 hours.
6. If the tenant stalls at one stage for 3+ days, assign direct follow-up owner.

## Escalation Rules
- If `payment_completed` count is flat for 7 days while top-of-funnel grows, escalate billing and closing workflow review.
- If any stage conversion drops by >= 20 percentage points week-over-week, run a focused incident-style retro within 24 hours.
- If stage data appears inconsistent, verify funnel event ingestion before acting on metrics.
