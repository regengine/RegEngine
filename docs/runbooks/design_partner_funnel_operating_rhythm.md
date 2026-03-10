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
3. Re-check funnel progress for that tenant within 24 hours.
4. If the tenant stalls at one stage for 3+ days, assign direct follow-up owner.

## Escalation Rules
- If `payment_completed` count is flat for 7 days while top-of-funnel grows, escalate billing and closing workflow review.
- If any stage conversion drops by >= 20 percentage points week-over-week, run a focused incident-style retro within 24 hours.
- If stage data appears inconsistent, verify funnel event ingestion before acting on metrics.
