# FIX-REPORT: About page copy

Copy-only change in `frontend/src/app/about/page.tsx`. Two sentences were reworded. The published price was not changed.

## Before and after

1. Verification sentence (principle "Verifiable, not just claimed")

Before:
`Customers can independently verify export-bundle integrity using our published verify_chain.py script.`

After:
`You can independently verify export-bundle integrity using our published verify_chain.py script.`

The rest of that sentence is unchanged: "Compliance records are hash-linked once ingested, so any later change is detectable."

2. Faster iteration card

Before:
`Design-partner feedback is scoped to`

After:
`Early tester feedback is scoped to`

The rendered sentence now reads: "No committee approvals. Early tester feedback is scoped to ship within days, not quarters."

The following line was not changed: "Regulatory updates deploy without waiting for quarterly release trains."

Price left as it was:
`RegEngine starts at $425/mo (billed annually).`

## Diff

`git diff --stat` (tracked files only):

```
 frontend/src/app/about/page.tsx | 4 ++--
 1 file changed, 2 insertions(+), 2 deletions(-)
```

Two hunks from `git diff -- frontend/src/app/about/page.tsx`:

```
@@ -69,7 +69,7 @@ const PRINCIPLES = [
     Icon: Shield,
     title: "Verifiable, not just claimed",
     description:
-      "Compliance records are hash-linked once ingested, so any later change is detectable. Customers can independently verify export-bundle integrity using our published verify_chain.py script.",
+      "Compliance records are hash-linked once ingested, so any later change is detectable. You can independently verify export-bundle integrity using our published verify_chain.py script.",
   },
   {
     Icon: Lightbulb,
@@ -206,7 +206,7 @@ export default function AboutPage() {
                 Faster iteration
               </p>
               <p className="mt-1 text-ui text-re-text-secondary">
-                No committee approvals. Design-partner feedback is scoped to
+                No committee approvals. Early tester feedback is scoped to
                 ship within days, not quarters. Regulatory updates deploy
                 without waiting for quarterly release trains.
               </p>
```

Untracked test file, not included in `git diff --stat`:
`frontend/src/__tests__/pages/about-copy.test.tsx`

`frontend/next-env.d.ts` was rewritten by `next build` (dev type paths became production type paths). That file was put back to the committed text. It is not part of this change.

## Build, typecheck, and lint

Install, from `frontend/`, lockfile `package-lock.json`:

`~/metacode/fleet/heavy npm ci`

Result: exit 0. Added 793 packages in 27s. npm also printed 10 high severity audit findings in the existing tree. `npm audit fix` was not run.

Test before the page edit (source assertions only, 2 tests):

`~/metacode/fleet/heavy ./node_modules/.bin/vitest run src/__tests__/pages/about-copy.test.tsx`

Result: exit 1.

```
Test Files  1 failed (1)
     Tests  2 failed (2)
```

Both failed because the file still had "Customers can independently verify..." and "Design-partner feedback is scoped to", and did not contain the new phrases.

Test after the page edit, then again after a render assertion was added:

`~/metacode/fleet/heavy ./node_modules/.bin/vitest run src/__tests__/pages/about-copy.test.tsx`

Result: exit 0. Final run: 1 file passed, 3 tests passed.

Lint on the page and the test:

`~/metacode/fleet/heavy ./node_modules/.bin/eslint src/app/about/page.tsx src/__tests__/pages/about-copy.test.tsx`

Result: exit 0, no findings.

Typecheck of the final tree:

`~/metacode/fleet/heavy ./node_modules/.bin/tsc --noEmit --pretty false --incremental false`

Result: exit 0. An earlier `tsc` run, before the render assertion existed, also exited 0.

Production build, from `frontend/`:

`~/metacode/fleet/heavy npm run build`

Result: exit 0. Next.js 16.3.6 compiled successfully in 13.4s, finished TypeScript in 9.8s, and generated 172 static pages. `/about` is in the route list. Warnings were the usual ones: no build cache, anonymous telemetry notice, custom Cache-Control header, and Edge Runtime deprecation. No build error.

Ruff was not run. This change is TypeScript only.

Browser: the About page was not opened in a browser. The vitest render asserts the visible joined sentence, and `npm run build` compiled the route.

---

# Follow-up: pricing label and pre-revenue copy (2026-10-08)

RegEngine is pre-revenue with no customers or pilots. This follow-up removes public copy that implied otherwise, and renames the price label "for Founding Design Partners" to the Founding rate. Every published price ($425, $499, $649, $749, $849) is unchanged. Copy only; no logic changed.

## Before and after

`frontend/src/components/pricing/PricingPageClient.tsx` (regengine.co/pricing)
1. `Founding Design Partner discounts are documented in the executed order form or design-partner agreement.` -> `Founding rate discounts are documented in the executed order form or design-partner agreement.`
2. Tier badge `Founding design partner rate` -> `Founding rate`
3. `Post-pilot list price · billed annually` -> `Standard list price · billed annually`
4. `50% off post-pilot list pricing under your executed design-partner terms.` -> `50% off standard list pricing under your executed design-partner terms.`
5. `We are onboarding a limited number of partners ahead of the July 2028 FSMA 204 enforcement window. Your Founding Design Partner rate is controlled by your agreement,` -> `We are accepting a limited number of early testers ahead of the July 2028 FSMA 204 enforcement window. Your Founding rate is controlled by your agreement,`
6. `RegEngine starts at $425/mo (billed annually) for Founding Design Partners.` -> `RegEngine's Founding rate starts at $425/mo (billed annually).`
7. `RegEngine's current design-partner posture;` -> `RegEngine's current early access posture;`
8. `Founding Design Partners start at $425/mo, billed annually.` -> `The Founding rate starts at $425/mo, billed annually.`

`frontend/src/app/pricing/page.tsx`
9. Meta and Open Graph description: `Transparent design-partner pricing with onboarding terms controlled by your agreement.` -> `Transparent Founding rate pricing with onboarding terms controlled by your agreement.`
10. FAQ: `What do Founding Design Partners get?` / `Founding Design Partner discounts are documented...` -> `What does the Founding rate include?` / `Founding rate discounts are documented...`
11. FAQ: `Does my partner pricing ever change?` / `Partner pricing is controlled by...` -> `Does my Founding rate ever change?` / `Your Founding rate is controlled by...`

`frontend/src/app/why-regengine/page.tsx`
12. `Plans from $425/mo (billed annually) for Founding Design Partners. Pricing is published — no "contact sales" required.` -> `Founding rate plans start at $425/mo (billed annually). Pricing is published, so you do not need to "contact sales."`
13. Three plan cards: `Founding design partner rate, billed annually (...)` -> `Founding rate, billed annually (...)`
14. `Founding Design Partners get preferred pricing for the life of their account.` -> `The Founding rate is preferred pricing for the life of your account.`
15. `Founding Design Partner rates from $425/mo (billed annually) get you live.` -> `Founding rates from $425/mo (billed annually) get you live.`

`frontend/src/app/compare/{foodlogiq,tracegains,repositrak}/page.tsx`
16. `(Founding Design Partner rates from $425/mo, billed annually)` -> `(Founding rates from $425/mo, billed annually)` (all three pages)
17. FoodLogiQ: `with Founding Design Partner rates from $425/mo (billed annually) — no multi-year commitment required. FoodLogiQ pricing is custom-quoted — request both...` -> `with Founding rates from $425/mo (billed annually) and no multi-year commitment required. FoodLogiQ pricing is custom-quoted, so request both...`

`frontend/src/app/supplier-compliance/page.tsx`
18. `plans start at $425/mo (billed annually) for Founding Design Partners.` -> `plans start at $425/mo (billed annually) at the Founding rate.`

`frontend/src/app/tools/roi-calculator/components/ROICalculatorClient.tsx` (two places)
19. `We don't have verified customer ROI data yet — early-design partner pricing reflects that.` -> `We don't have verified customer ROI data yet, and the Founding rate reflects that.`

`frontend/src/app/case-studies/page.tsx`
20. `RegEngine is in production with founding design partners; self-serve access is in staged rollout.` -> `RegEngine is pre-revenue; self-serve access is in staged rollout.`

`frontend/src/app/developers/page.tsx`
21. `Already a customer? Sign in` -> `Have a RegEngine workspace? Sign in` ("Already have an account" is blocked by the existing developers-front-door test, so it was not used.)

`frontend/src/app/status/page.tsx`
22. Meta description: `Live RegEngine system status — backend service health, last checked timestamp, and pilot support channel.` -> `Live RegEngine system status: backend service health, last checked timestamp, and support channel.`
23. Open Graph: `Live RegEngine system status and pilot support contact.` -> `Live RegEngine system status and support contact.`
24. Heading `Pilot support` -> `Support`
25. `We aim to respond within one business day during pilot programs.` -> `We aim to respond within one business day during early access.`

## Left alone on purpose

- Program name and its calls to action (`Founding Design Partner Program`, `Apply as founding design partner`, `Become a founding design partner` on /pricing, /walkthrough, /tools/label-scanner). These invite applications rather than claim existing partners, and `frontend/COPY_REMEDIATION_PLAN.md` D7 keeps "Founding Design Partner" as the program name. Renaming the program is a decision for C.Lee.
- `design-partner agreement` / `design-partner terms` as the name of the contract document (pricing FAQ, pricing card).
- /pricing comparison table cells `Design-partner workflow`, `Design-partner terms`, `Indicative design-partner ranges; agreement controls`: describe the offer, not existing customers.
- /why-regengine `Founding Design Partner rate never increases` and `Simple design-partner agreements — no multi-year lock-in` (three places): pricing commitments with an absolute claim and existing dashes; rewording a pricing promise needs C.Lee.
- /case-studies `Guided onboarding speed for an approved design-partner workspace using synthetic sample data`: scoped to synthetic data.
- /trust and /integrations status taxonomy (`Pilot`, `Design Partner` labels from `frontend/src/lib/customer-readiness.ts`), /docs inflow-lab `Pilot connector`, /contact `pilot onboarding`: capability status labels or offers tied to code identifiers.
- Homepage `Design-partner. Pre-revenue.`: already honest.
- "customer" where it means the reader's customers or a future contract party (blog posts, FSMA guides, trust, trust/support, trust/architecture, tools, lead gate), the in-app /remediation metric, and legal pages (/privacy, /terms, /dpa, /legal).

## Tests and build

New test `frontend/src/__tests__/pages/pre-revenue-copy.test.ts` asserts the retired phrases are gone from the 11 edited files, and that the $425/mo Founding rate wording is present.

- `vitest run src/__tests__/pages src/__tests__/public-site-fixes.test.tsx src/lib/csp.test.ts`: 44 files passed, 284 tests passed, 2 skipped.
- `eslint` on every changed file plus the new test: exit 0.
- `tsc --noEmit`: exit 0.
- `npm run build`: exit 0, 172 static pages generated. `next-env.d.ts` was rewritten by the build and put back; it is not part of this change.
