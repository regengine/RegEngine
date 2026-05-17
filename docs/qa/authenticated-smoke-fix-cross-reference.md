# Authenticated Smoke Fix Cross-Reference

Do not mark a finding fixed unless the row contains: root cause, exact changed files, targeted regression test, full matrix rerun result, and any cross-dependency updated after the rerun.

## Current Failure Summary

| Finding ID | Projects |
| --- | --- |
| AUTH-WEBKIT-001 | `safari-webkit-320`, `safari-webkit-375`, `safari-webkit-768`, `safari-webkit-1024`, `safari-webkit-1440`, `safari-webkit-1920`, `ios-safari-iphone-14` |
| DASH-MOBILE-001 | `chrome-320`, `firefox-320`, `chrome-375`, `firefox-375`, `chrome-android-pixel-7` |
| DASH-ONBOARD-001 | `chrome-320`, `firefox-320`, `chrome-375`, `firefox-375`, `chrome-768`, `firefox-768`, `chrome-1024`, `firefox-1024`, `chrome-1440`, `firefox-1440`, `chrome-1920`, `firefox-1920`, `chrome-android-pixel-7` |
| DASH-SIDEBAR-001 | `chrome-768`, `firefox-768`, `chrome-1024`, `firefox-1024`, `chrome-1440`, `firefox-1440`, `chrome-1920`, `firefox-1920` |
| MENU-FIREFOX-001 | `firefox-1024`, `firefox-1440`, `firefox-1920` |
| MATRIX-COVERAGE-001 | Edge latest, real iOS Safari 17+ |

## Ledger

| Finding ID | Evidence | Root Cause | Fix Owner | Fix Files | Regression Tests | Cross-Dependencies | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AUTH-WEBKIT-001 | WebKit/iOS login POST 200, no redirect | Local dev CSP blocked nonce-less WebKit scripts, and WebKit/Playwright `fill()` did not reliably propagate the controlled email state through React's `onChange` path at several layouts. | Auth/session | `frontend/src/lib/csp.ts`, `frontend/src/proxy.ts`, `frontend/src/lib/csp.test.ts`, `frontend/src/app/login/LoginClient.tsx`, `frontend/src/__tests__/auth/login.test.tsx` | `npm run test:run -- src/__tests__/auth/login.test.tsx src/lib/csp.test.ts src/__tests__/components/marketing-header-tools-menu.test.tsx`; programmatic WebKit login repro passed at 320/1024/1920 and iPhone 14 emulation using Playwright `fill()` | Blocks full Safari layout verification; real iOS Safari still requires device/cloud coverage | Fixed and verified locally |
| DASH-MOBILE-001 | Quick nav horizontal scroll, offscreen links, 36px targets | The mobile quick nav renders all five `TOP_ITEMS` in one hidden-scroll nowrap row with `min-h-[36px]`, so links overflow 320/375/Pixel widths and miss the 44px touch target. | Dashboard shell | `frontend/src/app/dashboard/layout.tsx`, `frontend/src/__tests__/pages/dashboard-navigation.test.tsx` | `npm run test:run -- src/__tests__/pages/dashboard-navigation.test.tsx`; after-fix smoke passed Firefox 320/375, Pixel 7, and Chrome 375 targeted rerun | Shares `frontend/src/app/dashboard/layout.tsx` with DASH-SIDEBAR-001; Chrome 320 had a page setup timeout in the full rerun, not a layout assertion | Fixed, targeted test passed, full matrix partially blocked |
| DASH-ONBOARD-001 | Getting Started overflow, 24px dismiss, 32px links | The card header dismiss button uses `p-1 -m-1`, creating a 24x24 target that protrudes from the flex row; checklist links are 32px tall and the walkthrough link has no minimum target size/wrap guard. | Dashboard content | `frontend/src/components/dashboard/getting-started-card.tsx`, `frontend/src/__tests__/components/getting-started-card.test.tsx` | `npm run test:run -- src/__tests__/components/getting-started-card.test.tsx src/__tests__/pages/dashboard.test.tsx`; Chrome 375 targeted smoke rerun passed after bumping link targets to 48px | Separate from quick-nav/sidebar; page wrapper changes did not need to change | Fixed and verified |
| DASH-SIDEBAR-001 | Sidebar links overlap section buttons | Collapsed sidebar sections keep submenu anchors mounted with real layout boxes while the wrapper is `maxHeight: 0; opacity: 0`, so hidden links overlap following section buttons in the smoke geometry audit. | Dashboard shell | `frontend/src/app/dashboard/layout.tsx`, `frontend/src/__tests__/pages/dashboard-navigation.test.tsx` | `npm run test:run -- src/__tests__/pages/dashboard-navigation.test.tsx`; after-fix smoke passed Chrome 768/1024/1440 and Firefox 768/1024/1440/1920 | Shares `frontend/src/app/dashboard/layout.tsx` with DASH-MOBILE-001; Chrome 1920 had a test timeout after dashboard render, not an overlap assertion | Fixed, targeted test passed, full matrix partially blocked |
| MENU-FIREFOX-001 | Firefox tools menu remains hidden after click | The Tools dropdown opens on hover and toggles on click; in Firefox, hover state can commit before click, so the click handler sees `toolsOpen=true` and immediately closes the menu. | Header/menu | `frontend/src/components/layout/header/NavDropdown.tsx`, `frontend/src/__tests__/components/marketing-header-tools-menu.test.tsx` | `npm run test:run -- src/__tests__/components/marketing-header-tools-menu.test.tsx`; covers hover-before-click, outside click close, and second-click close; after-fix smoke passed Firefox 1024/1440/1920 | Required before outside-click close can pass; separate from dashboard layout fixes | Fixed and verified |
| MATRIX-COVERAGE-001 | Edge not installed; real iOS 17+ Safari unavailable | Local environment lacks `/Applications/Microsoft Edge.app`; Playwright iPhone/WebKit is not a real iOS 17+ Safari device; Safari.app 26.5 exists but the automated run used Playwright WebKit 26.4. | QA environment | Environment setup, not app code | Manual/cloud/device coverage note | Separate from app code | Blocked by environment |

## Shared File Conflict Map

| Shared File | Findings | Coordination Rule |
| --- | --- | --- |
| `frontend/src/app/dashboard/layout.tsx` | DASH-MOBILE-001, DASH-SIDEBAR-001 | Use one dashboard shell implementation owner so quick-nav and sidebar fixes land together. |
| `frontend/src/app/dashboard/page.tsx` | DASH-ONBOARD-001, DASH-SIDEBAR-001 | Confirm page-level spacing changes do not mask sidebar overlap. |
| `frontend/src/components/layout/header/NavDropdown.tsx` | MENU-FIREFOX-001 | Keep header/menu work separate from dashboard layout fixes. |
| `frontend/src/lib/auth-context.tsx` | AUTH-WEBKIT-001 | Keep auth/session work separate from visual fixes; rerun Safari layout only after login is fixed. |

## Future Implementation Ownership

| Implementation Owner | Write Scope | Findings |
| --- | --- | --- |
| Auth/session worker | `frontend/src/lib/csp.ts`, `frontend/src/proxy.ts`, auth/session tests | AUTH-WEBKIT-001 |
| Dashboard shell worker | `frontend/src/app/dashboard/layout.tsx`, `frontend/src/__tests__/pages/dashboard-navigation.test.tsx`, focused dashboard shell smoke tests | DASH-MOBILE-001, DASH-SIDEBAR-001 |
| Dashboard content worker | `frontend/src/components/dashboard/getting-started-card.tsx`, dashboard page/component tests | DASH-ONBOARD-001 |
| Header/menu worker | `frontend/src/components/layout/header/NavDropdown.tsx`, `frontend/src/components/layout/marketing-header.tsx`, header/menu tests | MENU-FIREFOX-001 |
| Verification worker | Playwright smoke spec/config and QA docs only | MATRIX-COVERAGE-001 plus full rerun |

## Acceptance Criteria

- AUTH-WEBKIT-001: WebKit desktop widths and iPhone WebKit emulation redirect to `/dashboard`, `/sysadmin`, or `/onboarding` after login, with auth cookies/session visible to middleware.
- DASH-MOBILE-001: At 320, 375, and Pixel 7 widths, dashboard quick nav has no document-level horizontal overflow, no offscreen interactive links, and all visible touch targets are at least 44x44px.
- DASH-ONBOARD-001: Getting Started card has no horizontal overflow at 320, 375, 768, 1024, 1440, or 1920 widths, and every visible interactive control is at least 44x44px on mobile.
- DASH-SIDEBAR-001: Sidebar navigation entries and section controls do not overlap at 768, 1024, 1440, or 1920 widths in Chrome or Firefox.
- MENU-FIREFOX-001: Firefox opens the Tools dropdown at 1024, 1440, and 1920 widths, then outside click hides it.
- MATRIX-COVERAGE-001: Report clearly separates automated local coverage from blocked real-browser/device coverage.

## Rerun Rule

A fix is accepted only after a targeted test passes and the full authenticated smoke matrix is rerun on all locally available projects. Edge and real iOS Safari remain blocked until the required browser/device is available.

## Verification Results

- Targeted Vitest run: `npm run test:run -- src/lib/csp.test.ts src/__tests__/pages/dashboard-navigation.test.tsx src/__tests__/components/getting-started-card.test.tsx src/__tests__/pages/dashboard.test.tsx src/__tests__/components/marketing-header-tools-menu.test.tsx` passed: 5 files, 24 passed, 2 skipped.
- Follow-up card test after 48px target bump: `npm run test:run -- src/__tests__/components/getting-started-card.test.tsx src/__tests__/pages/dashboard.test.tsx` passed: 2 files, 11 passed, 2 skipped.
- After-fix local authenticated smoke matrix, excluding Edge: 13 passed, 7 failed. Passed: Chrome 768/1024/1440, WebKit 375/768/1440, Firefox 320/375/768/1024/1440/1920, Pixel 7 Chrome. Failed: Chrome 320 page setup timeout, Chrome 1920 test timeout after dashboard render, WebKit 320/1024/1920 login timeouts, iPhone 14 WebKit login timeout.
- Targeted rerun after card target bump: `npx playwright test --config=playwright.authenticated-smoke-matrix.config.ts --project=chrome-375` passed.
- Follow-up WebKit auth repro after CSP and input-state fixes: WebKit 320, WebKit 1024, WebKit 1920, and iPhone 14 emulation all posted `/api/admin/auth/login`, set `/api/session`, and navigated to `/dashboard`.
