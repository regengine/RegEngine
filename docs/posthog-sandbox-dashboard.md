# PostHog Dashboard Spec — Sandbox Conversion Funnel

## Overview

Tracks the full user journey from anonymous CSV paste to qualified lead.
All events prefixed with `SANDBOX_`.

---

## Dashboard Layout

### Row 1: Funnel Overview (4 metric cards)

| Metric | Event | Formula | Goal |
|--------|-------|---------|------|
| **Evaluations / week** | `SANDBOX_EVALUATE` | Count | Awareness — are people finding the tool? |
| **Grid Open Rate** | `SANDBOX_OPEN_GRID` / `SANDBOX_EVALUATE` | % where has_failures=true | Engagement — do they try to fix? |
| **Completion Rate** | `SANDBOX_ALL_CLEAR` / `SANDBOX_OPEN_GRID` | % | Value realization — did they succeed? |
| **Lead Capture Rate** | `SANDBOX_LEAD_CAPTURE` / (`SANDBOX_LEAD_CAPTURE` + `SANDBOX_LEAD_SKIP`) | % | Conversion — hand-raisers |

### Row 2: The Conversion Funnel (funnel chart)

Steps:
1. `SANDBOX_EVALUATE` — User pastes CSV and evaluates
2. `SANDBOX_OPEN_GRID` — User opens the spreadsheet editor
3. `SANDBOX_GRID_EDIT` — User makes their first edit
4. `SANDBOX_ALL_CLEAR` — All defects resolved
5. `SANDBOX_EXPORT_CSV` — User exports corrected data
6. `SANDBOX_CTA_CLICK` — User clicks a conversion CTA

**Breakdown by:** `cta_type` (book_call, automate, pricing, founding_cohort, recall_walkthrough)

### Row 3: Leakage Points (2 charts)

#### Chart A: "Frustration Gap" — Drop-off after grid open
- **Type:** Bar chart
- **X-axis:** Day
- **Series 1:** `SANDBOX_OPEN_GRID` count
- **Series 2:** `SANDBOX_EXPORT_CSV` count
- **Insight:** Gap = users who opened but never exported. High gap = too many red cells, need better recipes.

#### Chart B: "Gate Friction" — Lead gate conversion
- **Type:** Stacked bar
- **Series:** `SANDBOX_LEAD_CAPTURE` vs `SANDBOX_LEAD_SKIP`
- **Alert:** If skip rate > 80% for 7 consecutive days, revisit copy/value prop.

### Row 4: High-Intent Signals (table + trend)

#### Chart A: "Trace = Qualified" — Trace users vs total
- **Type:** Trend line
- **Series 1:** `SANDBOX_TRACE_RUN` unique users
- **Series 2:** `SANDBOX_EVALUATE` unique users
- **Insight:** Trace runners are 5x more likely to convert. Prioritize follow-up.

#### Chart B: "Hot Leads" — Recent lead captures
- **Type:** Table (persons)
- **Columns:** Email, defect_count, event_count, timestamp, cta_type
- **Filter:** `SANDBOX_LEAD_CAPTURE` in last 7 days
- **Sort:** Most recent first
- **Action:** Click email to open PostHog person profile → see full session replay

### Row 5: CTA Performance (pie + bar)

#### Chart A: CTA Click Distribution
- **Type:** Pie chart
- **Event:** `SANDBOX_CTA_CLICK`
- **Breakdown:** `cta_type`
- **Shows:** Which CTA resonates most (book_call vs automate vs pricing vs walkthrough)

#### Chart B: CTA by Mode
- **Type:** Grouped bar
- **Event:** `SANDBOX_CTA_CLICK`
- **Breakdown:** `mode` (failures, all_clear, trace_complete)
- **Insight:** Which emotional state drives the most action?

---

## Key Alerts (PostHog Actions)

| Alert | Trigger | Channel |
|-------|---------|---------|
| **New Lead** | `SANDBOX_LEAD_CAPTURE` fires | Slack #leads |
| **Hot Trace Lead** | `SANDBOX_TRACE_RUN` + `SANDBOX_CTA_CLICK` by same person within 10 min | Slack #leads + email to chris@ |
| **Funnel Regression** | Grid Open Rate drops below 30% for 3 consecutive days | Slack #product |
| **Gate Friction Spike** | Skip rate > 85% for 5 consecutive days | Slack #product |

---

## Cohort Definitions

| Cohort | Definition | Use |
|--------|-----------|-----|
| **Evaluators** | Performed `SANDBOX_EVALUATE` in last 30 days | Top of funnel |
| **Fixers** | Performed `SANDBOX_GRID_EDIT` in last 30 days | Engaged users |
| **Completers** | Performed `SANDBOX_ALL_CLEAR` in last 30 days | Value realized |
| **Tracers** | Performed `SANDBOX_TRACE_RUN` in last 30 days | High-intent |
| **Hand-Raisers** | Performed `SANDBOX_LEAD_CAPTURE` in last 30 days | SQLs |
| **CTA Clickers** | Performed `SANDBOX_CTA_CLICK` in last 30 days | MQLs |

---

## Calendly URL Parameters

The Calendly link includes context so Chris knows who he's talking to:

| Param | Value (failures / all_clear) | Value (trace_complete) | Example |
|-------|-------------------------------|------------------------|---------|
| `a1` | Mode that triggered the CTA | Mode that triggered the CTA | `failures`, `all_clear`, `trace_complete` |
| `a2` | Defect count at time of click | Lot count in the trace | `7` |
| `a3` | Event count in their CSV | Facility count in the trace | `12` |

These show up in Calendly's "Additional Info" section on the booking page.
In trace mode, `a2`/`a3` carry lot and facility counts instead of defect/event counts since those are not available.

---

## Implementation

All events are already firing as of PR #402. To build this dashboard:

1. Go to PostHog → Dashboards → New Dashboard → "Sandbox Conversion Funnel"
2. Add insights matching the specs above
3. Set up Actions for the alert triggers
4. Create Cohorts for the definitions above
5. Share dashboard link with the team

No additional code changes required.
