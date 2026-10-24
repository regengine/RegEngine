# Visual regression + page monitoring (report-only)

Playwright suite that screenshots public pages and monitors them for errors,
broken copy rules, and layout drift. **Report-only**: every workflow runs with
`continue-on-error`, nothing blocks merges, nothing opens issues.

**Read-only**: production runs are GET page visits only — no sign-ins, no form
submits, no writes. The two exceptions are fenced behind env flags that no
workflow sets automatically (see below).

## Files

| File | Purpose |
|---|---|
| `routes.json` | Single replaceable route data file (`public`, `priority`, `skippedDynamic`, `expectRedirectOr404`, `authOnly`, `excludedReason`) |
| `ROUTE_CROSSCHECK.md` | Mismatches between `/tmp/re-all-routes.txt` and real `page.tsx` files |
| `helpers.ts` | `stabilize()` (fixed clock, settle page, freeze animations, lazy-image scroll, auto-mask dynamic text), `screenshotMasks()`, route-name helper |
| `pages.visual.spec.ts` | Full-page screenshots per public route (desktop+mobile), redirect/404 assertions, header/nav bbox drift |
| `priority-extras.visual.spec.ts` | Mobile nav-open, CTA focus ring, tablet home+pricing |
| `content.spec.ts` | Copy rules (all `expect.soft`): no em/en dashes, no lone `-`, banned demo words, EPCIS→Preview, Live-label and trust rules |
| `smoke.spec.ts` | Page/same-origin console errors, same-origin ≥400s, empty pages; third-party failures attached + annotated, never fail |
| `crawl.spec.ts` | Sitemap crawler: visits every live sitemap URL (rewritten to base origin), flags broken links / dead ends / page+console errors, checks routes.json coverage; writes `test-results-visual/crawl-report-<project>.json` |
| `preview-forms.spec.ts` | Blank-submit validation screenshots, login+signup (preview only) |
| `signed-in.spec.ts` | Read-only signed-in checks (manual only, `VISUAL_AUTH=1`) |
| `layout-boxes.json` | Expected header/nav boxes (empty: `_note` only — see below) |
| `../../playwright.visual.config.ts` | Suite config (chromium only, no webServer) |
| `.github/workflows/visual-*.yml` | Preview, production, and baseline-refresh workflows |

## Run it

There is no npm script (that needs a `package.json` edit — see Follow-ups).
Run from `frontend/`:

```bash
# Whole suite against production (read-only)
VISUAL_BASE_URL=https://regengine.co npx playwright test --config=playwright.visual.config.ts

# One project
VISUAL_BASE_URL=https://regengine.co npx playwright test --config=playwright.visual.config.ts --project=smoke

# Sitemap crawler at both widths
VISUAL_BASE_URL=https://regengine.co npx playwright test --config=playwright.visual.config.ts --project=crawl-desktop --project=crawl-mobile

# View the last HTML report
npx playwright show-report playwright-visual-report
```

## Environment (names only — never commit values)

| Name | Effect |
|---|---|
| `VISUAL_BASE_URL` | Base URL under test. Default `https://regengine.co` |
| `VISUAL_ALLOW_FORM_SUBMIT` | `1` enables the `preview-forms` project (blank submits). Set only by `visual-preview.yml` |
| `VISUAL_AUTH` | `1` enables the `signed-in` project. Set by hand for manual runs; no workflow sets it |
| `VISUAL_USER_EMAIL` | Expected session email for the signed-in project (asserted, not used to log in) |
| `VISUAL_SESSION_TOKEN` | Opaque session cookie value for the signed-in project, provisioned out-of-band |
| `VISUAL_UPDATE_BOXES` | `1` records header/nav boxes to `test-results-visual/layout-boxes.candidate.json` (JSONL) instead of asserting |
| `VERCEL_AUTOMATION_BYPASS_SECRET` | Optional: value sent as `x-vercel-protection-bypass` on every request. Name only — no workflow sets it; adding a secret is an optional follow-up (see "Vercel protection") |

## Projects

| Project | Spec | Viewport |
|---|---|---|
| `desktop` | pages | 1440×900 |
| `mobile` | pages | 390×844, touch |
| `priority-extras` | priority extras | mixed (set per test) |
| `content` | content rules | default |
| `smoke` | smoke | default |
| `crawl-desktop` | sitemap crawl | 1440×900 |
| `crawl-mobile` | sitemap crawl | 390×844, touch |
| `preview-forms` | blank submits | default, only if `VISUAL_ALLOW_FORM_SUBMIT=1` |
| `signed-in` | signed-in reads | default, only if `VISUAL_AUTH=1` |

Conditional projects are **omitted from the config** unless their flag is set,
so they never show as skipped.

## Routes

`routes.json` is the only route list the suite reads. Public vs auth was
derived from `src/proxy.ts` + `AUTHENTICATED_APP_ROUTE_PREFIXES`
(`src/lib/app-routes.ts`) + `GATED_DEV_ROUTES` (`/developer/portal`) +
`next.config.js` redirects. Notable calls:

- `/fsma/*` is **auth-gated**; `/fsma-204` is public (prefix match is exact-or-slash).
- `/tools/*` pages render signed-out (client-side `useAuth` only gates API calls); the three redirect sources (`recall-readiness`, `readiness-assessment`, `retailer-readiness`) are asserted as redirects.
- `/auth/sso/mock` is excluded from every spec (mock SSO fixture).

To re-derive after route changes, re-run the crosscheck in
`ROUTE_CROSSCHECK.md` and edit `routes.json` — no spec changes needed.

Designer reconciliation (2026-10-23): the Visual Designer's production
crawl (81 routes returning 200 with no redirect) is adopted as the public
set minus `/auth/sso/mock`, `/demo`, `/sandbox`, which stay out of
baselines (mock fixture / demo surfaces — see `ROUTE_CROSSCHECK.md`).
Snapshot stems (`home`, `about`, `blog__<slug>`, …) match the designer's
`baseline/` PNG names 1:1 for review; the PNGs themselves are NOT copied
(see Baselines).

## Expected findings (known on day one)

- `/demo` and `/sandbox` are classified `expectRedirectOr404`, but both
  currently return 200 (`src/app/demo/page.tsx` renders the synthetic demo;
  `/sandbox` renders UI or a disabled notice depending on
  `isSandboxEnabled()`). Those assertions flag until the routes are retired
  or reclassified to `public`. `/alpha` genuinely redirects to `/contact`.
- The content word bans (`demo`, `sandbox`, `sample`, …) will flag current
  production copy (e.g. sandbox CTAs, "interactive demo" links). That is the
  point: the report inventories every occurrence for the copy cleanup.

## Baselines

Screenshots compare against `__screenshots__/<name>-<project>.png`
(`<name>` is the route with `/` → `__`, `/` itself is `home`), captured on
Linux. The stem scheme matches the Visual Designer's package 1:1
(`~/regengine-qa-spec/qa-spec/visual-regression/baseline/`), but **do NOT
copy those PNGs into the repo**: they were captured without the animation
freeze, fixed clock, or masks, so they would mismatch CI comparisons from
day one. They are a look-reference only.

Until baselines exist, every screenshot test reports a missing-snapshot
result — expected, and the reason the check stays report-only.

1. Dispatch **Visual Update Baselines** (`visual-update-baselines.yml`) with the URL to capture. It runs `--update-snapshots` once on `ubuntu-latest` with the freezes + masks in `helpers.ts` and uploads the PNGs as the `visual-baselines-linux` artifact.
2. Download the artifact, review the PNGs.
3. Commit them under `tests/visual/__screenshots__/` **only after the
   RegEngine Visual Designer's approval comment** on the run or PR.
4. Never commit baselines captured on macOS/Windows — font rendering differs
   and Linux CI comparisons will fail.

To make the check required later (all three):

1. Baselines committed per the above, suite green for a few weeks.
2. Remove `continue-on-error: true` from the `visual-report` job in the workflow being enforced (keep production monitoring non-required — it pages nobody by design).
3. Add the job as a branch-protection required status check on `main`, matching the job's `name:` (`visual-report (non-required)` — rename it first, e.g. to `visual-report`, so the required check has a sane name).

Comparison tolerances live in the config: `maxDiffPixelRatio: 0.001`,
`threshold: 0.2`, `scale: 'css'`, `deviceScaleFactor: 1`, animations
disabled, light scheme, reduced motion, `locale: en-US`,
`timezoneId: America/Los_Angeles`.

`maxDiffPixelRatio: 0.001` is intentionally strict for the first baseline
run. It can be relaxed (e.g. to `0.005`–`0.01`) after that run if the only
diffs are noise-level (subpixel antialiasing, font hinting).

## Layout boxes

`layout-boxes.json` holds expected header/nav bounding boxes keyed
`<project>:<route>`. It ships with a `_note` only (no invented numbers):
missing entries are attached to the report and never fail.

To capture real values:

```bash
rm -f test-results-visual/layout-boxes.candidate.json
VISUAL_BASE_URL=https://regengine.co VISUAL_UPDATE_BOXES=1 \
  npx playwright test --config=playwright.visual.config.ts --project=desktop --project=mobile
jq -s 'add' test-results-visual/layout-boxes.candidate.json > /tmp/boxes.json
# Review /tmp/boxes.json, then merge approved entries into layout-boxes.json
```

Drift tolerance is 2px per dimension (`BOX_TOLERANCE_PX` in `helpers.ts`).

## Signed-in runs (manual)

```bash
VISUAL_BASE_URL=<preview-url> VISUAL_AUTH=1 VISUAL_USER_EMAIL=<name-only> \
  VISUAL_SESSION_TOKEN=<provisioned-at-runtime> \
  npx playwright test --config=playwright.visual.config.ts --project=signed-in
```

Checks: session hydrates for that email; non-admin is blocked from `/admin`
and `/sysadmin`; Products, Compliance, Integrations, and Billing (lives at
`/dashboard/settings` — no standalone billing page exists) load with no page
errors. Key/token-like values are masked before screenshotting. Signed-in
screenshots are for local comparison — do not commit them (tenant data).
Failing request URL+status is attached per test.

## Vercel protection

If preview deploys sit behind Vercel Deployment Protection, the suite
screenshots the auth wall. The config already supports the bypass: when the
`VERCEL_AUTOMATION_BYPASS_SECRET` env var is set, every request carries it
as an `x-vercel-protection-bypass` header (name only — never commit the
value). No workflow sets that variable and no workflow references any
secret. Adding one later is an optional follow-up for Christopher to
approve: store the bypass value as an encrypted Actions secret and pass it
as that env var to the preview workflow's test step. Nothing else changes.

## Follow-ups (need edits to existing files — not done here)

1. **`data-visual-mask` / `data-vr-mask` attributes on components.**
   `helpers.ts` masks both (either opts out; `data-vr-mask` is the
   designer's alias). Authors should add one of them to timestamps,
   counters, and live widgets so masks are exact instead of selector-based.
2. **`npm run test:visual` script.** Needs a `package.json` edit:
   `playwright test --config=playwright.visual.config.ts`. Until then use the
   `npx` commands above.
3. **Required check later.** When baselines are committed and the suite is
   green for a few weeks, flip `continue-on-error` off (or add the job as a
   required status check) for previews. Keep production monitoring
   non-required — it pages nobody by design.
