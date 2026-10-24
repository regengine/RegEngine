# Frontend Page Audit

> Last verified: 2026-07-13 (WS-10)
> Prior verification 2026-04-17 (#1188). Changes this pass: removed the
> deleted `/owner/*`, `/forgot-password`, and `/reset-password` routes from
> the inventory, refreshed the quick stats against the current tree
> (163 pages / 38 handlers), and fixed the middleware reference — Next 16
> renamed `src/middleware.ts` to `src/proxy.ts`.

## What's live and linked

### Marketing nav ([marketing-nav.ts](src/components/layout/marketing-nav.ts))
Surfaces the public routes a prospect or visitor lands on. Check this file
when deciding whether a page is reachable from production chrome.

Top-level entries link to:
- `/walkthrough` (Product)
- `/pricing`
- `/security`, `/trust`
- `/about`
- `/tools`, `/fsma-204` (Resources)
- `/case-studies`, `/compare/*`

### Core design-partner journey (keep and maintain)
Authenticated app — reached after `/login` or `/alpha`. Each has active
product owners and regular UI work.
1. `/` — Landing page
2. `/alpha`, `/login`, `/signup` — sign-in is passwordless (email OTP /
   passkey via `/login`); the old `/forgot-password` and `/reset-password`
   pages no longer exist
3. `/onboarding` + `/onboarding/bulk-upload` + `/onboarding/setup/*`
4. `/dashboard` and `/dashboard/*` (20 sub-pages; canonical user surface)
5. `/fsma` and `/fsma/*` — authenticated FSMA dashboard (not the same
   route tree as the public `/fsma-204` marketing page)
6. `/sysadmin` — gated, sysadmin-only (middleware check)

### Free tools (SEO + lead gen)
`/tools/*` — 20 public tool pages (FTL checker, ROI calculator, etc.).
Kept for SEO even when usage is low. Don't delete without checking
search console first.

### Docs / trust / legal
- `/docs`, `/docs/*` (public API docs)
- `/developer/portal/*` (gated sections require API-key auth)
- `/trust/*`, `/security`, `/privacy`, `/terms`, `/dpa`

## Ambiguity / drift found in this audit

### `/fsma` vs `/fsma-204`
Two distinct route trees with confusingly similar names:
- `/fsma` — **authenticated app**, uses `useAuth` + FSMA hooks, mounted
  under the dashboard-style layout. Linked from `/dashboard` and the
  logged-in header.
- `/fsma-204` — **public marketing page**, static metadata, linked from
  blog posts, the FTL checker, and `/supplier-compliance`.

Not duplicates. Keep both. A rename would help (`/fsma-app/*` or
`/compliance-app/*` for the authenticated tree) but that's a bigger
refactor with redirect implications.

### `/compliance/*` root-level pages
Still shadowed by the `/compliance/:path*` → `/dashboard/compliance`
permanent redirect in `next.config.js` (tracked in #1183 — pending
founder decision: keep the pages and narrow the redirect, or delete the
pages entirely).

### Pages flagged as "disabled" in the prior audit that are actually live
- `/about` — linked from marketing-nav ("Company"), sitemap, JSON-LD
  breadcrumb in `layout.tsx`.
- `/walkthrough` — linked from marketing-nav ("Product"),
  SandboxResultsCTA, sitemap.
- `/mobile/*` — moved to `/dashboard/scan` per in-file comments.

If any of these genuinely aren't wanted, delete the nav entries first so
the link graph goes quiet before the pages are removed.

## Candidates for future archival
Still reachable but low-usage. Keep for now, revisit if we prune:
- `/portal/[portalId]` — supplier portal entry point

Resolved since the last audit: `/owner/*` (the unwired billing/contracts
suite) has been deleted, and its prefix removed from
`src/lib/app-routes.ts`. `/sandbox` and `/sandbox/results/[id]` were deleted
in #3557; CSV upload lives at `/ingest`.

## Route map quick stats
- Total page routes: 163 (including dynamic `[param]` variants)
- API route handlers: 38
- Auth-gated route prefixes: 19 (`AUTHENTICATED_APP_ROUTE_PREFIXES` in
  `src/lib/app-routes.ts`, consumed by `src/proxy.ts` — Next 16 renamed
  middleware to proxy)

Regenerate the counts with:
`find src/app -name page.tsx | wc -l` and `find src/app -name route.ts | wc -l`.
