# Pilot pricing — the answer for the first prospect call

**Date:** 2026-05-13
**Owner:** Christopher Sellers
**Status:** Draft default — refine after first 3 prospect calls produce signal

## Why this exists

The first prospect on a pilot call asks "what does this cost?" within the first 5 minutes. Without a pre-decided answer, the founder fumbles, the prospect smells indecision, and the relationship starts on weak footing. This doc is the answer to say out loud.

The structured pricing study (per [GTM memo](../research/fsma-204-go-to-market-2026-05.md) §pricing) hasn't run yet. This doc sets a defensible default until that study produces signal — typically 3-5 calls.

## The answer (memorize this)

> "Free during pilot — we're looking for 5-10 design partners who'll let us watch them use it for 60 days in exchange for free 12-month access and a public reference if you're satisfied. After the pilot period, pricing is volume-tiered around CTE event count; we'll know your tier once we've seen your data. For your scale, expect roughly $X-$Y per month — we'll firm that up in the second call."

Replace `$X-$Y` with the range from the table below once you've heard the prospect describe their volume.

## Three options I considered

### Option A (recommended) — Design partner free, volume-tiered post-pilot pricing
- **Pilot (60 days):** Free. Includes founder support, 30-min biweekly observation, no event volume cap.
- **Post-pilot:** Three usage tiers, billed monthly, anchored on CTE events ingested per month.
  - **Pilot Grandfather** (signed before 2026-08-01): 12 months free after pilot, then locked-in tier price.
  - **Starter:** ~$X/month, up to ~5K CTE events/month.
  - **Growth:** ~$Y/month, up to ~50K events/month.
  - **Scale / Enterprise:** Custom, includes EDI ingestion, custom export formats, and contract-defined support terms.

**Pros:** Removes pricing question for first pilots. Volume tiering aligns price with the natural unit of value (events). "Pilot grandfather" creates urgency without discounting post-pilot pricing.
**Cons:** Requires firming up `$X/$Y` before second-call follow-up.

### Option B — Free, no post-pilot pricing yet
- Free for everyone until first 10 paying customers.
- "We'll set post-pilot pricing based on what we learn from you."

**Pros:** Even less friction; emphasizes design-partner positioning.
**Cons:** Sophisticated prospects will assume you don't know what you're doing. Procurement teams won't sign without a future-cost number, even a rough one.

### Option C — Pay-as-you-go from day 1
- $0.X0 per CTE event ingested, capped at $Y/month.
- No free pilot.

**Pros:** Maximally honest unit economics.
**Cons:** Highest friction. Pre-revenue B2B SaaS rarely succeeds with this; you need usage proof first.

## Why A wins for this stage

- Solo founder pre-revenue with N=0 active pilots (verified 2026-05-13). Need usage, not revenue. Revenue follows usage; usage doesn't follow revenue at this stage.
- "Design partner" framing is well-understood in B2B SaaS and signals seriousness without committing pricing.
- The GTM memo already proposed "free 12-month advisor access" as a discovery-call thank-you — extending the same to pilots is consistent.
- Procurement teams accept "$X-$Y range, firmed up after volume assessment" as a placeholder when paired with a free pilot.

## Numbers to set this week (do not delegate)

Pick concrete numbers for `$X` (Starter) and `$Y` (Growth) before the next prospect call. Defensible defaults based on FoodLogiQ benchmarks from the GTM memo (FoodLogiQ "starts at $25K/year" per Capterra):

- **Starter:** $499/month ($6K/year). Roughly 1/4 of low-end FoodLogiQ.
- **Growth:** $1,499/month ($18K/year). Roughly 3/4 of low-end FoodLogiQ.

These are placeholders. Refine after first 3 prospect calls reveal what they actually budget for.

## What the prospect's procurement team will ask

Have a one-line answer ready:

- **"Is there an annual discount?"** Yes — 10% off Starter/Growth on annual prepay.
- **"Is there a setup fee?"** No for pilot. After pilot, the Scale tier includes one-time integration scoping; Starter/Growth are self-serve.
- **"What's your cancellation policy?"** Pilot can end at any time; post-pilot contracts are month-to-month unless on annual prepay.
- **"Where's your data residency?"** US (per /trust). Specifics in your DPA.
- **"Do you have third-party assurance?"** Not yet — see /trust for current security posture; an external assurance program is planned post-revenue.

## What this doc explicitly does NOT cover

- **Custom enterprise pricing.** Scale tier is "let's talk" — don't try to publish enterprise numbers.
- **Multi-tenant reseller / agency pricing.** Defer until a real partner asks.
- **Price-per-supplier or seat-based pricing.** CTE event count is the right unit for FSMA 204; don't fragment.

## Revisit this doc

After:
- 3 prospect calls in which the price came up
- First paid customer signs
- Any direct competitive intel that puts FoodLogiQ / Trustwell / ReposiTrak quotes in front of you

Update the table; archive this version in `docs/decisions/archive/`.
