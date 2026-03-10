# Design-Partner Demo Script (15 Minutes)

## Goal
Run a tight live demo that drives one immediate next step: signup, pilot start, or integration review.

## Audience
Food safety, compliance, and supplier ops leads preparing for FSMA 204.

## Success Criteria
- Prospect sees scan -> query -> export flow end to end.
- Prospect states one blocker and one must-have requirement.
- Prospect commits to a dated next action.

## Demo Operator Checklist

### Day-before prep
- [ ] Confirm environment has live data for one traceability lot.
- [ ] Prepare one GS1 barcode/QR sample (AI 01/10/17/21 or Digital Link).
- [ ] Verify `POST /api/v1/qr/decode` responds successfully in target env.
- [ ] Verify `POST /api/v1/query/traceability` returns non-empty results.
- [ ] Verify FDA export endpoint returns package for sample lot.

### Five minutes before call
- [ ] Start on `/product` page.
- [ ] Open tabs: `/fsma/field-capture`, `/tools/knowledge-graph`, `/tools/recall-readiness`.
- [ ] Have one fallback barcode image ready if camera permissions fail.
- [ ] Ensure billing/pricing page is open for close.

## 15-Minute Talk Track

### 0:00-1:30 - Problem framing
"FSMA 204 is an operational response-time problem. Most teams can find data, but not fast enough or complete enough under recall pressure."

### 1:30-3:00 - Product tour
- Open `/product`.
- Walk the three pillars: scan, ask, export.
- Set expectation: "I will run one lot through all three live."

### 3:00-7:00 - Scan -> ingest
- Open `/fsma/field-capture`.
- Scan GS1 code live.
- Call out auto-filled fields (GTIN, lot, date, serial).
- Submit ingest and confirm success state.

### 7:00-10:00 - Ask -> answer
- Open `/tools/knowledge-graph`.
- Ask a real query, for example:
  - "Show lettuce events from Supplier X in the last 30 days"
  - "Where did lot ABC-2025-001 come from?"
- Highlight answer block, evidence, warnings, and confidence.

### 10:00-12:30 - Export -> comply
- Open `/tools/recall-readiness` (or FDA export flow).
- Trigger export package.
- Show CSV + manifest + verification artifact and explain chain verification briefly.

### 12:30-15:00 - Close and qualify
Ask exactly these questions:
1. "What would stop you from using this today?"
2. "What is missing vs your current process?"
3. "If we solve that gap, who approves rollout and when?"

Then propose one next step with a date:
- Pilot activation
- Integration workshop
- Security/procurement review

## Post-Demo Capture Checklist (Same Day)
- [ ] Log blocker and requested feature in scorecard.
- [ ] Update outreach tracker status and next action.
- [ ] Check funnel progression (`signup_completed` -> downstream stages) within 24 hours.
- [ ] Create one prioritized product task if blocker is repeated across two or more demos.
