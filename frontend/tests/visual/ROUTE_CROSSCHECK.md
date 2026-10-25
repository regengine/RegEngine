# Route crosscheck: /tmp/re-all-routes.txt vs app router pages

Generated 2026-10-23. Source list: `/tmp/re-all-routes.txt` (task brief says 156
routes; the file actually contains **155 non-empty lines** — line 1 is blank).
Actual pages: `frontend/src/app/**/page.{tsx,jsx}` → **157 page files**.

Method: each `page.tsx(x)` directory mapped to its route
(`./about/page.tsx` → `/about`, `./page.tsx` → `/`), then set-diffed against
the source list.

## Routes in the list with no page (1)

| Route | Verdict |
|---|---|
| `/settings/users` | No `page.tsx`. Redirect source: `next.config.js` 308s it to `/dashboard/settings/users` (which exists). Classified under `expectRedirectOr404` in `routes.json`; the redirect assertion covers it. |

## Pages not in the list (3)

| Page | Verdict |
|---|---|
| `/` (`src/app/page.tsx`) | The home page — missing from the source list. Added to `public` and `priority` in `routes.json` (priority requires it). |
| `/dashboard/settings/users` (`src/app/dashboard/settings/users/page.tsx`) | Auth-gated (`/dashboard` prefix). Not in the source list, so not in `routes.json` (which covers exactly the source list + `/`). Covered indirectly: the signed-in spec visits nearby settings surface. Add to `authOnly` if the list is ever extended. |
| `/onboarding/supplier-flow` (`src/app/onboarding/supplier-flow/page.jsx`) | Auth-gated (`/onboarding` prefix; note `.jsx`, the only JSX page). Same as above: not in the source list, not in `routes.json`. |

## Coverage statement

`routes.json` covers all 155 source-list routes plus `/`, minus `/sandbox/results/[id]` (deleted in #3557):

- `public`: 78 (designer crawl minus the 3 deliberate exclusions; was 82 before reconciliation — see below)
- `authOnly`: 58
- `skippedDynamic`: 4 (`/fsma-204/[cte]`, `/ingest/results/[id]`, `/portal/[portalId]`, `/requests/[id]`; `/sandbox/results/[id]` was removed when #3557 deleted it)
- `expectRedirectOr404`: 14 (was 10 before reconciliation)
- excluded entirely: `/auth/sso/mock` (mock SSO fixture; reason in `excludedReason`, visited by no spec)

Per-route reasons for every non-public route live in the `excludedReason` map
in `routes.json`.

## Designer package reconciliation

Source: the RegEngine Visual Designer's package at
`~/regengine-qa-spec/qa-spec/visual-regression/` — `routes.json` (81
routes that returned **200 with no redirect** on production
`https://regengine.co`, crawl of 151 routes, Oct 23 2026), `baseline/`
(162 PNGs), `playwright.config.ts`, `visual.spec.ts`.

The 151 crawled = the 155 source-list routes + `/` − the 5 dynamic
params, so every non-dynamic route was crawled exactly once, including
`/design-system`.

### In the designer list, not in our `public` (3) — kept out deliberately

| Route | Designer evidence | Verdict |
|---|---|---|
| `/auth/sso/mock` | Crawled 200 | Excluded entirely (unchanged): mock SSO fixture page (`CHROMELESS_EXACT_ROUTES`). Never screenshotted or visited by monitoring, regardless of status. |
| `/demo` | Removed by #3543 | Stays in `expectRedirectOr404` (unchanged). /demo is removed by #3543: the page is deleted, so the assertion now passes. |
| `/sandbox` | Crawled 200 (before #3557) | Stays in `expectRedirectOr404`. The route was deleted in #3557 (no `src/app/sandbox/`), so it is now expected to 404 and the assertion should pass. |

### In our `public`, not in the designer list (4) — adopted, moved to `expectRedirectOr404`

Our earlier proxy/static analysis had these as public 200s; the crawl
showed otherwise, and the page sources confirm the crawl in all four
cases (page-level `redirect()` / `notFound()` that static route analysis
missed):

| Route | Designer evidence | Page source (read-only) | Verdict |
|---|---|---|---|
| `/trust-center` | Redirecting (target already covered) | `src/app/trust-center/page.tsx` calls `redirect('/trust')`; `/trust` is in `public` | Moved to `expectRedirectOr404` |
| `/verticals/food-safety` | Redirecting (target already covered) | `src/app/verticals/food-safety/page.tsx` calls `redirect('/fsma-204')`; `/fsma-204` is in `public` | Moved to `expectRedirectOr404` |
| `/tools/anomaly-simulator` | Redirecting (target already covered) | `src/app/tools/anomaly-simulator/page.tsx` calls `permanentRedirect('/tools/drill-simulator')`; `/tools/drill-simulator` is in `public` | Moved to `expectRedirectOr404` |
| `/design-system` | Not 200 (in neither the 200 set nor the redirect list) | `src/app/design-system/page.tsx` calls `notFound()` when `NODE_ENV=production` ("Internal · development only") → 404 on production | Moved to `expectRedirectOr404` |

Net: `public` 82 → **78** (= designer 81 − the 3 deliberate exclusions
above); `expectRedirectOr404` 10 → **14**. Per-route reasons are in the
`excludedReason` map in `routes.json`.

### Snapshot naming

The designer names baselines `{route with / → __, / = home}-{project}.png`
(`home-desktop.png`, `blog__<slug>-mobile.png`, …). Our
`screenshotName()` already produced the same stems; the config's
`snapshotPathTemplate` is now
`{testDir}/__screenshots__/{arg}-{projectName}{ext}` so regenerated
baselines land on identical filenames for 1:1 review. The designer's PNGs
themselves are NOT copied (captured without freezes or masks — see README
"Baselines").
