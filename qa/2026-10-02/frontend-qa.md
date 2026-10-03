# Frontend QA — regengine/RegEngine (static, read-only)

- **Date:** 2026-10-02
- **Branch:** main (via GitHub API)
- **Method:** static read-only review of the Next.js App Router app in `frontend/` (886 files; 810 in `src/`). No `npm install`, no build, no test run, no browser.
- **Files inspected (fetched from API):** `frontend/AGENTS.md`, `frontend/README.md`, `frontend/PAGE_AUDIT.md` (2026-07-13), `frontend/package.json`, `frontend/next.config.js` (redirects), `frontend/src/proxy.ts` (626 lines), `frontend/src/lib/api-client.ts` (981 lines, excerpts), `frontend/src/hooks/use-api-query.ts`, `frontend/src/components/ui/{empty-state,spinner,button}.tsx`, `frontend/src/app/login/PasswordlessEntryClient.tsx` (272 lines), `frontend/docs/accessibility_audit.md` (2026-01-27), `frontend/COPY_REMEDIATION_PLAN.md` (2026-08-02).
- **Not inspected:** the remaining ~870 frontend files (all 163 pages, 500 `src/app` routes, 128 `__tests__`, e2e). Findings are limited to what fetched files establish; page-level claims below cite the repo's own audit docs.

## Component structure

- Design system primitives exist in `frontend/src/components/ui/` (27 files: button, input, dialog, alert, callout, empty-state, spinner, skeleton, toast, data-table, etc.). `EmptyState` is spec-driven (`SPEC §4`) with an explicit heading-level prop (`titleAs`) that preserves document outline — accessibility was designed in, not bolted on.
- Auth architecture: HTTP-only cookies; client hooks (`use-api-query.ts`) call same-origin proxy routes; the proxy injects credentials server-side. `authFetch` centralizes 401-gating of queries (`enabled: isAuthenticated`). Two fetch layers coexist with different error semantics (see F-3).

## F-1 (Medium) — Copy contradictions across the marketing/app surface (self-documented, status unknown)

`frontend/COPY_REMEDIATION_PLAN.md` (2026-08-02) is the repo's own audit of the frontend copy against backend code, the FDA, and the Federal Register. Verified facts it records that still matter:

| Item | Contradiction recorded |
|---|---|
| Pricing | `why-regengine` shows $425/$549/$639; `pricing` shows GA $999/$1299/$1499 with struck partner rates; `compare/*` says "$425–$749/mo" |
| Legal entity | Terms: "RegEngine Inc. / Los Angeles, CA"; DPA: "RegEngine, Inc. / Wilmington, Delaware"; LICENSE/footer/READMEs: "RegEngine Inc."; `pyproject.toml` author email used `admin@regengine.io` (wrong domain — still present at HEAD in the file fetched 2026-10-02) |
| Support promise | Status page "first response within 24 hours"; LeadGate "within 24 hours"; retailer assessment "< 24hr turnaround"; trust pages promise nothing |
| Maturity | "Pre-production" (case-studies) vs production plans (pricing) |
| Org term | workspace / organization / tenant / account used interchangeably in UI (plan default: "workspace" user-facing, "tenant" never) |
| Developer funnel | Docs: "free developer account in minutes"; `/developers`: request-gated preview |
| Fabricated-evidence language | `/ingest` demo flow renders "Integrity Status: VERIFIED" and "100% unbreakable provenance linking" over sample output; `why-regengine` cites "customer interviews"; FTL checker "retailers are already requiring traceability NOW"; about-page customer track record; `/fsma/market` "75+ companies" over 48 entries with named real companies in the user-facing app |
| Compliance-verdict language | `dashboard/compliance` "FSMA 204 Compliant — meets current FDA requirements"; audit-log "Compliant with 21 CFR Part 11 … SOX" + "Tamper-proof" badge; recall-report "ready to respond to a 24-hour FDA records request" |
| Hardcoded audit actor | `exceptions`/`requests` resolution paths write hardcoded `'dashboard_user'` instead of the session user's identity (plan PR-5) |
| Synthetic audit rows | client-side code injects synthetic rows into the audit log and shows a decorative "Chain Verified" stat not bound to the verification endpoint (plan PR-5) |
| CFR citation | `NormalizedDocumentViewer.tsx` cites `§ 1.1330` for receiving — should be `§ 1.1345` (plan PR-1) |
| Non-CTE event types in samples | `transport`/`quality_check`/`CREATION` used where real CTE names belong (plan PR-4) |

None of the above was re-verified against today's pages in this static pass (pages were not fetched). The plan is dated 2026-08-02 and is written as a to-do list, so the default assumption is these are **open** unless Christopher confirms the PR batches landed. This is the single largest frontend finding: the marketing/app copy contains regulatory and evidentiary claims that the repo's own engineering audit flags as false or misleading.

## F-2 (Low) — `PAGE_AUDIT.md` vs `next.config.js`: `/compliance/*` redirect state disagrees

- `frontend/PAGE_AUDIT.md` (2026-07-13): `/compliance/*` root-level pages "still shadowed by the `/compliance/:path*` → `/dashboard/compliance` permanent redirect in `next.config.js` (tracked in #1183 — pending founder decision)".
- `frontend/next.config.js` (fetched at HEAD): the catch-all is gone; only the **bare** `/compliance` path redirects, with an inline comment explaining the previous catch-all "301-ed every click to the bare /dashboard/compliance, losing the sub-route and breaking navigation (#1183)" and that only the bare path is redirected now.
- Either the audit is stale (fix landed after 2026-07-13) or the config regressed. The config reads like the fix. Low severity; the audit doc should be updated or closed against #1183.
- Separately, the audit's `/fsma` (authenticated app) vs `/fsma-204` (public marketing page) naming confusion is acknowledged as intentional-but-confusing, kept for redirect-cost reasons. Acceptable; noted.

## F-3 (Low) — Two fetch layers with different error-envelope semantics

- `frontend/src/hooks/use-api-query.ts` (`authFetch`): on `!res.ok` throws a generic `Error("API error: ${res.status} ${res.statusText}")` — raw HTTP status text propagates toward UI. Loading/error states depend on each page's React Query `error` rendering.
- `frontend/src/lib/api-client.ts:488-499` handles mixed backend envelopes carefully (CSV-parsing `detail` object vs validation `detail` array vs `{message, errors}`), with comments about a past `.map` crash (`:711`).
- So the *preferred* hook (`use-api-query.ts`, "the PREFERRED pattern for all new code") has the weaker error UX, while the older client has the hardened one. A page using the preferred hook shows users "API error: 422 Unprocessable Entity" style text unless it maps statuses itself. Not a security issue; a UX-consistency one.

## F-4 (Low) — `Spinner` has no accessible loading announcement

- `frontend/src/components/ui/spinner.tsx`: the spinner is a bare `<div className="animate-spin …">` with no `role="status"`, no `aria-label`, no visually-hidden "Loading" text. Screen-reader users get no announcement when async content is loading.
- The repo's own `frontend/docs/accessibility_audit.md` (2026-01-27, WCAG 2.1 AA) claims ARIA-label and keyboard fixes landed. The login page (`PasswordlessEntryClient.tsx`) does use `role="status"`/`role="alert"` on `Callout`s (`:145-172`) — so the pattern exists in-app; the shared `Spinner` just doesn't use it. One-line fix when someone is in the file.

## F-5 (Positive — verified in fetched files)

- **Login page** (`frontend/src/app/login/PasswordlessEntryClient.tsx`): open-redirect protection (`resolveSafeNextPath` rejects `//` and `/login` prefixes); generic OTP message ("If this address is eligible, a sign-in code is on its way") — no user enumeration; double-submit guard; 429-specific copy; error/status regions with `role="alert"`/`role="status"`; in-flight redirect-loop guard keyed on cookie-backed auth (not localStorage user).
- **proxy.ts**: 19 auth-gated route prefixes (`AUTHENTICATED_APP_ROUTE_PREFIXES`), sysadmin gating, redirect discipline.
- **Error boundaries**: `frontend/src/app/error.tsx` and `frontend/src/app/login/error.tsx` exist (login one fetched as a path; content not reviewed).
- **Copy honesty infrastructure**: `frontend/scripts/design-lint.mjs`, `promise-audit.mjs`, `production-readiness.mjs`, `security-release-gate-audit.mjs`, `verify-public-ssr.mjs` exist as scripts; `PROMISE_AUDIT.md` maintained.
- Backend envelope normalization (`services/shared/error_handling.py`) gives the frontend a stable `{type, message}` shape to rely on — the frontend's defensive envelope parsing in `api-client.ts` is now belt-and-suspenders.

## What was NOT reviewed (frontend)
- The 163 pages themselves (content, forms, empty/loading states per page), the 38 API route handlers in `src/app/api`, e2e tests, visual design, actual rendered accessibility (needs a browser), bundle size, or the public `/verify` page UX.
