# First-Pilot Session Playbook

What happens between "warm contact agrees to look at it" and "their tenant_id is in the OKR count." 30 minutes, observed, no mid-call fixes.

This doc connects:
- [first-pilot-onboarding outreach list](../research/fsma-204-go-to-market-2026-05.md) — 200+ named companies
- [Inflow Workbench Design Partner Demo](inflow_workbench_design_partner_demo.md) — the 3-4 minute talk track for the live walkthrough
- [Design-Partner Funnel Operating Rhythm](design_partner_funnel_operating_rhythm.md) — the daily metrics loop after a pilot lands
- [OKR decision doc](../decisions/2026-05-13-okr.md) — the single metric this serves

## Pre-call (T-24h)

1. Verify the prospect has a real ingestion path today. If they only have spreadsheets and no API/EPCIS/EDI capability, the smoke test will fail in ways that aren't about RegEngine. Use the demo flow (synthetic CSV via Inflow Lab) instead of a live pilot.
2. Provision their tenant:
   - Create the tenant in production via the admin flow.
   - Mint an API key (`rge_live_*` prefix per docs/authentication).
   - Send the prospect the API key + the [quickstart link](https://regengine.co/docs/quickstart) **before** the call. Ask them to try one curl request to `/api/v1/webhooks/ingest` ahead of the session. If they hit issues, those go on the call agenda.
3. Skim recent commits to anything they'd touch. If something obviously broke in the last 48h, reschedule or scope around it.

## On the call (30 min total)

### Minute 0-5: Frame
"I'm going to watch you try to use this. I'll answer direct blockers but I won't fix anything mid-call. If something is confusing, that's the data I want."

### Minute 5-25: Observation

They drive. You observe.
- They sign in (Supabase Auth — note any session weirdness).
- They drop their API key into a curl or Postman call.
- They post one real CTE event to `/api/v1/webhooks/ingest`.
- They open the dashboard and find their event.

**Do NOT:**
- Pre-fill anything for them.
- Skip ahead "to save time."
- Apologize for rough edges. If they hit one, note it; move on.

**Capture in a scratch doc as it happens** — not from memory afterward:
- Every "wait, where do I…" question.
- Every error message they see.
- Every place they pause for more than 10 seconds without scrolling.
- The exact moment they say something that sounds like "oh, I get it."

### Minute 25-30: Wrap

- Thank them. Ask: "If we did one thing this week to make this stick, what is it?"
- Schedule the next observation in 2 weeks (per the [OKR doc](../decisions/2026-05-13-okr.md)).
- Do NOT promise specific fixes. Promise to read the notes and route them.

## Within 1 hour after the call

1. Run the OKR query:
   ```bash
   psql "$DATABASE_URL" -f scripts/okr_pilots_ingesting_weekly.sql
   ```
   The pilot's tenant should appear in the per-pilot breakdown. If it doesn't, the ingest didn't actually persist — that's a P0, not a UX note.
2. Write a 5-bullet observation note. File at `docs/pilots/<tenant-slug>-<YYYY-MM-DD>.md`:
   - Top 3 friction points (verbatim, no interpretation)
   - One thing they said that surprised you
   - The "if we did one thing this week" answer
3. **Pick exactly ONE** friction point to fix this week. Open a GitHub issue with label `pilot-feedback`. The fix routes through the [OKR doc](../decisions/2026-05-13-okr.md) routing rule.

## Anti-patterns

- **Multi-pilot stacking.** Run one pilot session per week, max. Multiple in parallel before iterating wastes the signal — you'll fix things one pilot complained about that the other was fine with.
- **Pre-cleaning the experience.** Don't fix the friction the prospect surfaced before the next session. The friction IS the signal. Fix it after observation, not preemptively.
- **Adding feature requests to the backlog.** A request from a single pilot is noise. A request from three pilots is signal. Track requests in the pilot notes, not as issues, until pattern emerges.
- **Calling it a "demo."** This is observation, not sales theater. The Inflow Workbench demo doc covers the sales motion; this doc is what happens after they want to try it themselves.

## Success conditions

- Pilot's tenant appears in `scripts/okr_pilots_ingesting_weekly.sql` output within 1 hour of the call.
- Pilot accepts a second observation session 2 weeks out.
- You leave the call with at least 3 friction points captured verbatim.
- You do NOT leave the call with a list of new features to build.
