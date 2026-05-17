# Authenticated Smoke Findings Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Review every authenticated smoke-suite failure with focused parallel agents, then produce a cross-reference map tying each finding to the responsible fix, test coverage, and rerun result.

**Architecture:** Use read-only explorer agents first, one per independent failure domain, then reconcile their findings in a coordinator-owned matrix before any code edits. If fixes are approved later, assign write ownership by file boundary so dashboard shell, auth/session, header menu, and verification changes do not collide.

**Tech Stack:** Next.js App Router, React, Playwright 1.59.1, Chromium/Firefox/WebKit browser projects, local admin API on FastAPI.

---

## Source Evidence

- Smoke report: `/tmp/regengine-authenticated-smoke-matrix/results.json`
- Smoke artifacts: `/tmp/regengine-authenticated-smoke-matrix/test-results`
- Worktree: `/Users/sellers/RegEngine/regengine-auth-scoped-session`
- Local smoke target used: frontend `http://127.0.0.1:3801`, backend `http://127.0.0.1:8800`

## Failure Groups To Review

| Finding ID | Failure | Affected Projects | Primary Suspects | Blocks |
| --- | --- | --- | --- | --- |
| AUTH-WEBKIT-001 | Login POST returns 200 but WebKit/iOS stays on `/login` | `safari-webkit-320`, `safari-webkit-375`, `safari-webkit-768`, `safari-webkit-1024`, `safari-webkit-1440`, `safari-webkit-1920`, `ios-safari-iphone-14` | `frontend/src/app/login/LoginClient.tsx`, `frontend/src/lib/auth-context.tsx`, `frontend/src/lib/api-client.ts`, `frontend/src/app/api/admin/[...path]/route.ts`, `frontend/src/app/api/session/route.ts`, `frontend/src/proxy.ts` | All Safari layout verification |
| DASH-MOBILE-001 | Dashboard quick nav creates horizontal scroll and offscreen links | `chrome-320`, `firefox-320`, `chrome-375`, `firefox-375`, `chrome-android-pixel-7` | `frontend/src/app/dashboard/layout.tsx` | No-horizontal-scroll, touch target checks |
| DASH-ONBOARD-001 | Getting Started card scrolls horizontally and has <44px targets | Chrome/Firefox all widths for overflow, mobile widths for target size | `frontend/src/components/dashboard/getting-started-card.tsx`, `frontend/src/app/dashboard/page.tsx` | No-horizontal-scroll, touch target checks |
| DASH-SIDEBAR-001 | Sidebar/list items overlap section buttons at tablet and desktop widths | `chrome-768`, `firefox-768`, `chrome-1024`, `firefox-1024`, `chrome-1440`, `firefox-1440`, `chrome-1920`, `firefox-1920` | `frontend/src/app/dashboard/layout.tsx` | No-overlap checks |
| MENU-FIREFOX-001 | Tools dropdown does not become visible in Firefox desktop widths | `firefox-1024`, `firefox-1440`, `firefox-1920` | `frontend/src/components/layout/header/NavDropdown.tsx`, `frontend/src/components/layout/header/DesktopNav.tsx`, `frontend/src/components/layout/header/MobileMenu.tsx` | Outside-click close verification |
| MATRIX-COVERAGE-001 | Edge and real iOS Safari were blocked by local environment | Edge latest, real iOS 17+ Safari | QA environment, browser availability | Complete requested matrix |

## Task 1: Create The Cross-Reference Review Ledger

**Files:**
- Create: `docs/qa/authenticated-smoke-fix-cross-reference.md`
- Read: `/tmp/regengine-authenticated-smoke-matrix/results.json`

- [ ] **Step 1: Generate the current failure summary**

Run:

```bash
cd /Users/sellers/RegEngine/regengine-auth-scoped-session/frontend
node - <<'NODE'
const fs = require('fs');
const r = JSON.parse(fs.readFileSync('/tmp/regengine-authenticated-smoke-matrix/results.json', 'utf8'));
const groups = new Map();
for (const suite of r.suites || []) for (const spec of suite.specs || []) for (const t of spec.tests || []) {
  for (const res of t.results || []) for (const e of res.errors || (res.error ? [res.error] : [])) {
    const msg = String(e.message || '').replace(/\u001b\[[0-9;]*m/g, '').trim();
    let label = null;
    if (msg.startsWith('TimeoutError: page.waitForURL')) label = 'AUTH-WEBKIT-001';
    else if (msg.startsWith('Error: horizontal scroll containers')) label = 'DASH-MOBILE-001 or DASH-ONBOARD-001';
    else if (msg.startsWith('Error: interactive elements extend beyond viewport')) label = 'DASH-MOBILE-001';
    else if (msg.startsWith('Error: mobile/touch targets smaller than 44x44')) label = 'DASH-MOBILE-001 or DASH-ONBOARD-001';
    else if (msg.startsWith('Error: interactive elements overlap')) label = 'DASH-SIDEBAR-001';
    else if (msg.startsWith('Error: expect(locator).toBeVisible() failed') && msg.includes('#tools-dropdown')) label = 'MENU-FIREFOX-001';
    if (label) {
      if (!groups.has(label)) groups.set(label, new Set());
      groups.get(label).add(t.projectName);
    }
  }
}
for (const [label, projects] of groups) console.log(`${label}: ${[...projects].join(', ')}`);
NODE
```

Expected: output lists the six finding IDs above with the affected projects.

- [ ] **Step 2: Create the ledger**

Add `docs/qa/authenticated-smoke-fix-cross-reference.md` with this table shape:

```markdown
# Authenticated Smoke Fix Cross-Reference

| Finding ID | Evidence | Root Cause | Fix Owner | Fix Files | Regression Tests | Cross-Dependencies | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUTH-WEBKIT-001 | WebKit/iOS login POST 200, no redirect | Pending Agent A | Auth/session | Pending | Pending | Blocks Safari layout verification | Reviewing |
| DASH-MOBILE-001 | Quick nav horizontal scroll, offscreen links, 36px targets | Pending Agent B | Dashboard shell | Pending | Pending | Shares `dashboard/layout.tsx` with DASH-SIDEBAR-001 | Reviewing |
| DASH-ONBOARD-001 | Getting Started overflow, 24px dismiss, 32px links | Pending Agent C | Dashboard content | Pending | Pending | May affect mobile and desktop overflow | Reviewing |
| DASH-SIDEBAR-001 | Sidebar links overlap section buttons | Pending Agent D | Dashboard shell | Pending | Pending | Shares `dashboard/layout.tsx` with DASH-MOBILE-001 | Reviewing |
| MENU-FIREFOX-001 | Firefox tools menu remains hidden after click | Pending Agent E | Header/menu | Pending | Pending | Required before outside-click close can pass | Reviewing |
| MATRIX-COVERAGE-001 | Edge not installed; real iOS 17+ Safari unavailable | Pending Coordinator | QA environment | Pending | Pending | Separate from app code | Reviewing |
```

- [ ] **Step 3: Record the review rule**

Add this rule to the top of the ledger:

```markdown
Do not mark a finding fixed unless the row contains: root cause, exact changed files, targeted regression test, full matrix rerun result, and any cross-dependency updated after the rerun.
```

## Task 2: Dispatch Read-Only Review Agents

**Files:**
- Read: `docs/qa/authenticated-smoke-fix-cross-reference.md`
- Read: `/tmp/regengine-authenticated-smoke-matrix/results.json`
- Read: `/tmp/regengine-authenticated-smoke-matrix/test-results`

- [ ] **Step 1: Dispatch Agent A for AUTH-WEBKIT-001**

Prompt:

```markdown
You are Agent A, read-only reviewer for AUTH-WEBKIT-001.

Goal: explain why WebKit and iPhone Safari emulation receive a successful `/auth/login` response but remain on `/login` without redirecting.

Read these files:
- `frontend/src/app/login/LoginClient.tsx`
- `frontend/src/lib/auth-context.tsx`
- `frontend/src/lib/api-client.ts`
- `frontend/src/app/api/admin/[...path]/route.ts`
- `frontend/src/app/api/session/route.ts`
- `frontend/src/proxy.ts`
- `frontend/tests/e2e/login-dashboard.spec.ts`
- `frontend/tests/e2e/auth-diagnostic.spec.ts`

Use evidence from:
- `/tmp/regengine-authenticated-smoke-matrix/results.json`
- WebKit/iPhone traces and screenshots under `/tmp/regengine-authenticated-smoke-matrix/test-results`

Constraints:
- Do not edit files.
- Do not investigate dashboard layout or header dropdown bugs.
- Return exact file references, root cause hypothesis, confirmation steps, minimal fix proposal, and which smoke projects should clear.
```

- [ ] **Step 2: Dispatch Agent B for DASH-MOBILE-001**

Prompt:

```markdown
You are Agent B, read-only reviewer for DASH-MOBILE-001.

Goal: explain mobile quick-nav horizontal scroll, offscreen links, and 36px touch targets at 320, 375, and Pixel 7 widths.

Read these files:
- `frontend/src/app/dashboard/layout.tsx`
- `frontend/src/__tests__/pages/dashboard-navigation.test.tsx`
- `frontend/tests/e2e/login-dashboard.spec.ts`

Use evidence from:
- `/tmp/regengine-authenticated-smoke-matrix/results.json`
- `chrome-320`, `firefox-320`, `chrome-375`, `firefox-375`, and `chrome-android-pixel-7` artifacts

Constraints:
- Do not edit files.
- Stay focused on quick navigation and mobile target sizing.
- Note interactions with DASH-SIDEBAR-001 because both likely touch `frontend/src/app/dashboard/layout.tsx`.
- Return exact file references, root cause, minimal fix proposal, and regression test recommendation.
```

- [ ] **Step 3: Dispatch Agent C for DASH-ONBOARD-001**

Prompt:

```markdown
You are Agent C, read-only reviewer for DASH-ONBOARD-001.

Goal: explain Getting Started card horizontal scroll and undersized interactive controls.

Read these files:
- `frontend/src/components/dashboard/getting-started-card.tsx`
- `frontend/src/app/dashboard/page.tsx`
- `frontend/src/hooks/use-onboarding.ts`
- `frontend/src/__tests__/pages/dashboard.test.tsx`

Use evidence from:
- `/tmp/regengine-authenticated-smoke-matrix/results.json`
- artifacts for Chrome/Firefox mobile, tablet, and desktop failures mentioning `Getting Started`

Constraints:
- Do not edit files.
- Do not investigate the dashboard sidebar or quick nav except to identify shared layout constraints.
- Return exact file references, root cause, minimal fix proposal, touch-target recommendations, and tests to update or add.
```

- [ ] **Step 4: Dispatch Agent D for DASH-SIDEBAR-001**

Prompt:

```markdown
You are Agent D, read-only reviewer for DASH-SIDEBAR-001.

Goal: explain why dashboard sidebar/list items overlap section buttons at 768px and wider.

Read these files:
- `frontend/src/app/dashboard/layout.tsx`
- `frontend/src/__tests__/pages/dashboard-navigation.test.tsx`
- `frontend/src/components/layout/page-container.tsx`

Use evidence from:
- `/tmp/regengine-authenticated-smoke-matrix/results.json`
- `chrome-768`, `firefox-768`, `chrome-1024`, `firefox-1024`, `chrome-1440`, `firefox-1440`, `chrome-1920`, and `firefox-1920` artifacts

Constraints:
- Do not edit files.
- Identify whether the overlap is caused by collapsed/expanded nav state, absolute positioning, animation timing, or fixed-height containers.
- Cross-reference any proposed change with Agent B because both involve `frontend/src/app/dashboard/layout.tsx`.
```

- [ ] **Step 5: Dispatch Agent E for MENU-FIREFOX-001**

Prompt:

```markdown
You are Agent E, read-only reviewer for MENU-FIREFOX-001.

Goal: explain why the Tools dropdown stays hidden after click in Firefox desktop widths, preventing outside-click close verification.

Read these files:
- `frontend/src/components/layout/header/NavDropdown.tsx`
- `frontend/src/components/layout/header/DesktopNav.tsx`
- `frontend/src/components/layout/header/MobileMenu.tsx`
- `frontend/src/components/ui/dropdown-menu.tsx`

Use evidence from:
- `/tmp/regengine-authenticated-smoke-matrix/results.json`
- Firefox artifacts for 1024, 1440, and 1920 widths

Constraints:
- Do not edit files.
- Distinguish "menu did not open" from "menu opened but outside click failed."
- Return exact file references, browser-specific root cause hypothesis, minimal fix proposal, and a focused Playwright test.
```

- [ ] **Step 6: Keep MATRIX-COVERAGE-001 with the coordinator**

Record these facts in the ledger:

```markdown
Edge latest is blocked locally because `/Applications/Microsoft Edge.app` is missing and Playwright's `msedge` project uses a system browser channel.
Real iOS Safari 17+ is blocked locally because Playwright WebKit/iPhone emulation is not a real iOS simulator or device.
Safari.app 26.5 exists locally, but the matrix used Playwright WebKit 26.4 because automated Safari.app support is not equivalent to Playwright WebKit.
```

## Task 3: Reconcile Agent Findings Before Any Fixes

**Files:**
- Modify: `docs/qa/authenticated-smoke-fix-cross-reference.md`

- [ ] **Step 1: Fill root causes**

For each finding row, replace `Pending Agent X` with the agent's root cause in one sentence and add exact file references.

- [ ] **Step 2: Cross-reference shared files**

Use this conflict map:

```markdown
| Shared File | Findings | Coordination Rule |
| --- | --- | --- |
| `frontend/src/app/dashboard/layout.tsx` | DASH-MOBILE-001, DASH-SIDEBAR-001 | One implementation owner for dashboard shell fixes; reviewers may remain separate. |
| `frontend/src/app/dashboard/page.tsx` | DASH-ONBOARD-001, DASH-SIDEBAR-001 | Confirm page-level spacing changes do not hide sidebar overlap. |
| `frontend/src/components/layout/header/NavDropdown.tsx` | MENU-FIREFOX-001 | Keep separate from dashboard layout fixes. |
| `frontend/src/lib/auth-context.tsx` | AUTH-WEBKIT-001 | Keep separate from visual fixes; rerun Safari layout only after login is fixed. |
```

- [ ] **Step 3: Decide implementation ownership**

Assign future write ownership like this:

```markdown
| Implementation Owner | Write Scope | Findings |
| --- | --- | --- |
| Auth/session worker | `frontend/src/app/login/LoginClient.tsx`, `frontend/src/lib/auth-context.tsx`, `frontend/src/lib/api-client.ts`, auth/session tests | AUTH-WEBKIT-001 |
| Dashboard shell worker | `frontend/src/app/dashboard/layout.tsx`, dashboard navigation tests | DASH-MOBILE-001, DASH-SIDEBAR-001 |
| Dashboard content worker | `frontend/src/components/dashboard/getting-started-card.tsx`, `frontend/src/app/dashboard/page.tsx`, dashboard page tests | DASH-ONBOARD-001 |
| Header/menu worker | `frontend/src/components/layout/header/NavDropdown.tsx`, `frontend/src/components/layout/header/DesktopNav.tsx`, header/menu tests | MENU-FIREFOX-001 |
| Verification worker | Playwright smoke spec/config and QA docs only | MATRIX-COVERAGE-001 plus full rerun |
```

## Task 4: Define Fix Acceptance Criteria

**Files:**
- Modify: `docs/qa/authenticated-smoke-fix-cross-reference.md`

- [ ] **Step 1: Add per-finding acceptance criteria**

Add this section:

```markdown
## Acceptance Criteria

- AUTH-WEBKIT-001: WebKit desktop widths and iPhone WebKit emulation redirect to `/dashboard`, `/sysadmin`, or `/onboarding` after login, with auth cookies/session visible to middleware.
- DASH-MOBILE-001: At 320, 375, and Pixel 7 widths, dashboard quick nav has no document-level horizontal overflow, no offscreen interactive links, and all visible touch targets are at least 44x44px.
- DASH-ONBOARD-001: Getting Started card has no horizontal overflow at 320, 375, 768, 1024, 1440, or 1920 widths, and every visible interactive control is at least 44x44px on mobile.
- DASH-SIDEBAR-001: Sidebar navigation entries and section controls do not overlap at 768, 1024, 1440, or 1920 widths in Chrome or Firefox.
- MENU-FIREFOX-001: Firefox opens the Tools dropdown at 1024, 1440, and 1920 widths, then outside click hides it.
- MATRIX-COVERAGE-001: Report clearly separates automated local coverage from blocked real-browser/device coverage.
```

- [ ] **Step 2: Add rerun criteria**

Add this verification rule:

```markdown
A fix is accepted only after a targeted test passes and the full authenticated smoke matrix is rerun on all locally available projects. Edge and real iOS Safari remain "blocked" until the required browser/device is available.
```

## Task 5: Verification Plan After Fixes

**Files:**
- Create or modify only after review reconciliation: `frontend/tests/e2e/authenticated-app-smoke.spec.ts`
- Create or modify only after review reconciliation: `frontend/playwright.authenticated-smoke.config.ts`
- Modify: `docs/qa/authenticated-smoke-fix-cross-reference.md`

- [ ] **Step 1: Add or restore a permanent smoke spec**

The permanent spec should assert the same checks as the temporary matrix:

```markdown
- login redirects to `/dashboard`, `/sysadmin`, or `/onboarding`
- primary navigation is visible after login
- document width does not exceed viewport width by more than 1px
- no scroll container unintentionally creates horizontal overflow
- visible interactive elements do not extend beyond viewport
- visible interactive elements do not overlap
- mobile/coarse-pointer visible touch targets are at least 44x44px
- mobile drawer closes on outside tap
- desktop Tools dropdown opens and closes on outside click
```

- [ ] **Step 2: Rerun local matrix**

Run:

```bash
cd /Users/sellers/RegEngine/regengine-auth-scoped-session/frontend
npx playwright test --config=playwright.authenticated-smoke.config.ts
```

Expected: all locally available projects pass except explicitly blocked Edge/real-device coverage.

- [ ] **Step 3: Update the ledger**

For every row in `docs/qa/authenticated-smoke-fix-cross-reference.md`, set `Status` to one of:

```markdown
Fixed and verified
Fixed, targeted test passed, full matrix blocked
Needs follow-up
Blocked by environment
```

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-12-authenticated-smoke-findings-review.md`.

Two execution options:

1. **Subagent-Driven (recommended)**: dispatch Agents A-E for read-only review, reconcile the ledger, then assign implementation workers with disjoint write scopes.
2. **Inline Execution**: perform each review serially in this session, update the ledger after each finding, then pause before fixes.
