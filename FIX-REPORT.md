# SEO fix report: regengine.co public snippets

Scope is the eight pages in section 4 of the Oct 8, 2026 audit, plus the sitewide JSON-LD price block and the two tool redirects that the sitemap was still listing. Visible pricing copy was left as it is. Other long titles outside these pages are listed under left open.

Before counts are the live strings from that audit. After counts are the strings now in the page source, and the same strings were returned by a local production server (see Tests).

## Before and after

| Page | Field | Before | After |
| --- | --- | --- | --- |
| Homepage | Title | 48. RegEngine, then an em dash, then FSMA 204 traceability evidence layer | 43. FSMA 204 Recordkeeping Software \| RegEngine |
| Homepage | Meta | 222. Long ingest and export sentence ending in Early-stage, Design-partner, Pre-revenue | 142. Pre-revenue FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. The FDA compliance date is July 20, 2028. Not legal advice. |
| Homepage | H1 | 37. FSMA 204 traceability evidence layer. | 54. FSMA 204 recordkeeping for the Food Traceability Rule. |
| Tools index | Title | 17. Tools \| RegEngine | 31. Free FSMA 204 Tools \| RegEngine |
| Tools index | Meta | 218 | 140. Free FTL List Checker, CTE Mapper, KDE checklist, and TLC format check. Self reported lists do not score readiness. FDA date: July 20, 2028. |
| Tools index | H1 | 45. Small tools for list checks and field checks. | 53. Free tools for FSMA 204 list checks and field checks. |
| FTL List Checker | Title | 28. FTL List Checker \| RegEngine | 41. FTL List Checker for FSMA 204 \| RegEngine |
| FTL List Checker | Meta | 193 | 152. Check foods against the FDA Food Traceability List. This free page does not decide who must keep records. Verify every grouping on the current FDA list. |
| FTL List Checker | H1 | 16. FTL List Checker | 16. FTL List Checker |
| CTE Mapper | Title | 66. CTE Mapper \| FSMA 204 Critical Tracking Events by Role \| RegEngine | 39. FSMA 204 CTE Mapper by Role \| RegEngine |
| CTE Mapper | Meta | 201 | 143. See which Critical Tracking Events usually apply to a role under 21 CFR Part 1 Subpart S. Educational only. Exemptions can change what applies. |
| CTE Mapper | H1 | Two H1s, both CTE Coverage Mapper | 10. One H1: CTE Mapper |
| KDE Field Checklist | Title | 63. KDE Checklist Builder \| FSMA 204 Starting Checklist \| RegEngine | 40. FSMA 204 KDE Field Checklist \| RegEngine |
| KDE Field Checklist | Meta | 187 | 144. A starting checklist of Key Data Elements for an FTL food and a Critical Tracking Event. Educational only. Check the rule before you rely on it. |
| KDE Field Checklist | H1 | KDE Checklist Builder | 19. KDE Field Checklist |
| TLC Format Check | Title | 70. TLC Validator \| Test Your GS1 Traceability Lot Code Format \| RegEngine | 41. TLC Format Check for FSMA 204 \| RegEngine |
| TLC Format Check | Meta | 159. Claimed a test against GS1 standards and FDA uniqueness requirements | 152. Check a traceability lot code for format and uniqueness assumptions. FDA does not set one TLC format. This free check is not a compliance determination. |
| TLC Format Check | H1 | TLC Validator | 16. TLC Format Check |
| Self Reported Checklist | Title | 35. Self-Reported Checklist \| RegEngine | 46. Self Reported Checklist \| FSMA 204 \| RegEngine |
| Self Reported Checklist | Meta | 142 | 146. You answer and the page echoes what you reported. It does not verify records, score readiness, or decide if you can meet the records request rule. |
| Self Reported Checklist | H1 | Two H1s: Self-Reported Checklist, and RegEngine bullet Self-Reported Checklist | 23. One H1: Self Reported Checklist |
| Records Request Checklist | Title | 37. Records-Request Checklist \| RegEngine | 46. FSMA 204 Records Request Checklist \| RegEngine |
| Records Request Checklist | Meta | 258 | 138. A self reported checklist for an FDA records request under 21 CFR 1.1455. Not a 24 hour test, not a readiness score, and not legal advice. |
| Records Request Checklist | H1 | Records-Request Checklist | 25. Records Request Checklist |

Every after title is 60 characters or under. Every after meta description is 155 or under. The root layout default title and description match the homepage strings, so a page that does not set its own snippet no longer inherits the old long default.

## Item 2: TLC claim

The title, meta description, Open Graph text, JSON-LD name and description, breadcrumb, H1, social card, tools index card, and the related-tool blurb on the KDE page no longer say the checker tests an FDA format or GS1 standards. They say FDA does not set one TLC format. The same sentence is on the traceability lot code blog call to action. The page body already said FDA does not specify a format. That body was left in place.

## Item 3: matching names

The tools index cards, the index JSON-LD names, each page title, and each H1 now use the same name: FTL List Checker, CTE Mapper, KDE Field Checklist, TLC Format Check, Self Reported Checklist, Records Request Checklist.

The CTE page and the self reported page no longer render a second H1 in the loading fallback. The self reported shell takes an optional heading so its H1 is Self Reported Checklist. Other free tools still use the existing "RegEngine" bullet plus title. That default was not changed, because an end to end test asserts it on Scan and Ingest.

## Item 4: JSON-LD prices

The root layout no longer emits Product or AggregateOffer. It emits SoftwareApplication with no offers and no prices. The old block listed monthly prices and a highPrice of 1499. Tool pages that emitted an Offer with price 0 had that offer object removed. Visible prices on the pricing page were not edited.

## Item 5: readiness redirect, sitemap lastmod, and the 500

`/tools/readiness-assessment` still 308 redirects to `/tools/self-reported-checklist` in next.config.js. The page file now also redirects, sets the canonical URL to the checklist, and asks crawlers not to index the old URL. The old assessment is not rendered.

`/tools/recall-readiness` is the same kind of mismatch. It 308 redirects to `/tools/records-request-checklist`, and the page file now redirects there too. Cards and the compliance checklist blog post that still linked to the old URL, and called it a readiness score or a 24 hour recall test, now link to the records checklist and use that name.

Both old URLs are gone from the sitemap. A sitemap URL has to answer 200. The test also fails if any next.config.js redirect source is listed.

Blog lastmod stays the publication date as YYYY-MM-DD. `stableLastModified` returns that string only when it is a real calendar date. A bad value is omitted. Next prints a string as-is. An invalid Date would throw inside toISOString and can make `/sitemap.xml` return HTTP 500. That is the local explanation for the intermittent 500. It was not reproduced here.

Local check, after `npm run build`, on http://127.0.0.1:4188 (not production):

- `/sitemap.xml` returned 200 eight times. 64 URLs. 9 lastmod values, all YYYY-MM-DD. No readiness-assessment or recall-readiness URL.
- `/tools/readiness-assessment` returned 308 to `/tools/self-reported-checklist` eight times.
- `/tools/recall-readiness` returned 308 to `/tools/records-request-checklist` eight times.
- The eight audited pages returned 200 with the titles, metas, and single H1s in the table. Homepage HTML had no AggregateOffer, priceCurrency, or highPrice.

`next start` without CSRF_SECRET refuses to boot. That is the existing production startup check. It is not the sitemap 500. A throwaway local value was used only for this process and was not written to a file. The server was stopped.

## Tests and build

New test: `frontend/src/__tests__/seo/public-snippets.test.ts`.

Before the production edits, that file was run against the old tree:

`~/metacode/fleet/heavy ./node_modules/.bin/vitest run src/__tests__/seo/public-snippets.test.ts`

Result: 9 failed, 1 passed (10). The pass was lastmod stability on the old date strings. The failures were the old titles and descriptions, the old tool names, the TLC FDA uniqueness sentence, Offer and AggregateOffer fields, and the sitemap still listing the two redirect URLs. Log: session terminal `call-1d6dd8e1-b3b6-480d-8d2f-4d83ed47b7aa-108.log`.

One assertion was added after that run: an invalid date is dropped instead of being serialized. The old sitemap module did not export `stableLastModified`, so that import would fail on the old tree. It was not re-run against the old tree, because restoring files is not allowed in this checkout.

After the fix, from `frontend/`:

`~/metacode/fleet/heavy ./node_modules/.bin/vitest run src/__tests__/seo/public-snippets.test.ts src/__tests__/pages/homepage.test.tsx src/__tests__/seo/crawl-surface.test.ts`

Result: 3 files passed, 26 tests passed. Run twice, both exit 0. The second run was after the self reported lead-gate label was aligned to Self Reported Checklist.

`~/metacode/fleet/heavy npm run lint`

Result: exit 0. eslint reported 0 errors and 41 warnings. The warnings are in eslint config, scripts, e2e tests, and older pages this change did not introduce. design-lint: clean (644 files).

`~/metacode/fleet/heavy npm run build`

Result: exit 0. Next.js 16.3.6. Compiled in 6.9s. TypeScript finished in 8.7s. 172 pages generated. `/sitemap.xml` is static. There is no separate typecheck script. The build is the typecheck. That build finished before the last two visible labels on the self reported page were changed from Self-Reported Checklist to Self Reported Checklist. Those are string literals only. The test file was run again after that change and passed. The build was not run a second time.

`next build` also rewrote `frontend/next-env.d.ts` to point at `.next/types` instead of `.next/dev/types`. That file was put back. It is not part of the SEO fix.

## Left open

- Titles and metas outside these eight pages are still long. Examples: blog, docs, developers, the FSMA 204 guide, login, and the retailer readiness layout. They were not in the eight page set.
- Homepage HTML still has no og:site_name. The root layout sets siteName, and the homepage openGraph block does not. The rendered tag was absent. The audit called this smaller than the five main gaps.
- `/retailer-readiness` still redirects to `/buyer-programs`. A few pages still say Readiness Assessment and point there, or point at `/fsma/assessment`. Those are not `/tools/readiness-assessment`.
- `ReadinessAssessmentClient.tsx` and `RecallReadinessClient.tsx` are still in the tree. The routes no longer render them. `FSMA204Assessment` is still used by the self reported checklist and by `/fsma/assessment`.
- The intermittent production sitemap 500 was not reproduced. Production was not called.
- The homepage eyebrow still says design-partner. Pricing page prices were not changed.
