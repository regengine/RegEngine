# Browser follow-up pass — UX lane

PR: opened by orchestrator

CI status: pending at time of writing

42 initial route/viewport/browser combinations returned HTTP 200 with no uncaught page errors or whole-document horizontal overflow. Browser versions: Chromium 153.0.8010.12, Firefox 155.0, WebKit 26.6; Playwright 1.63.0; @axe-core/playwright and axe 4.13.0. True top-level desktop 1440×900 and mobile 390×844 contexts replace the earlier iframe-only evidence.

All contexts block service workers and external requests; document HTML removes speculative preconnect/dns links and adds same-origin resource/connect CSP. All APIs are synthetic. External Google Fonts are intentionally blocked, so screenshots use fallback fonts. This pass establishes local browser rendering and interaction only.

## Accessibility results

| Route | Desktop (all three engines) | Mobile Chromium / Firefox / WebKit |
| --- | --- | --- |
| `/` | 0 | 0 / 0 / 0 |
| `/login` | 0 | 0 / 0 / 0 |
| `/verify` | 0 | scrollable-region-focusable: 5 / 5 / 6 nodes |
| `/tools/scan` | heading-order: 1 node | heading-order: 1 / 1 / 1 node |
| `/contact` | 0 | 0 / 0 / 0 |
| `/demo` | 0 | 0 / 0 / 0 |
| `/tools/ftl-checker` | 0 | 0 / 0 / 0 |

Counts are violated-rule nodes, not separate findings. UX-003 repeats at the actual 390px viewport. UX-006 is a new Low best-practice heading-order issue, not a claimed WCAG conformance failure: `frontend/src/app/tools/scan/page.tsx:114` renders Camera Scanner as h3 after the shell h1. Initial and parsed-result states flag the same one h3. Parsed Fields is also an h3 but is not another reported axe node. Zero violations do not establish complete accessibility.

## Keyboard evidence

- UX-001 confirmed across all engines: Tab to the mobile menu opener, Enter, wait for the visible drawer, Tab to Close menu, Escape, Shift+Tab. The drawer remains open after Escape and focus leaves its modal to the background opener. Source: `frontend/src/components/layout/header/MobileMenu.tsx:32`.
- UX-002 confirmed across all engines: Tab through desktop `/verify` to `verify-bundle-file`; its focus is clipped to 1×1px and the visible label has no outline/shadow. Source: `frontend/src/app/verify/page.tsx:233`.
- UX-007 (new Medium) confirmed across all engines: first Tab on `/` focuses Skip to content, but after250ms it remains 1×1px with `clip: rect(0px,0px,0px,0px)` and no visible indicator. Enter changes URL to #main-content and the next Tab reaches Verify a sample export, so bypass navigation works while focus visibility fails. Source: `frontend/src/app/layout.tsx:140` and the unlayered `.sr-only` at `frontend/src/app/globals.css:914`, which overrides focused utility styles.
- Keyboard-only manual scan succeeds across all engines: reach the input with Tab, type synthetic `010950600013435210BATCH-ABC`, Enter, observe BATCH-ABC, then continue ten Tabs out of the parser. Focus/tab order recorded in JSON; no trap in this sampled parser flow.
- WebKit uses native Option/Alt+Tab because the server macOS preference excludes links/buttons from ordinary Tab. The initial normal-Tab timeout is preserved as an environment limitation.

## Synthetic states, screenshots and console/network

Eight final Chromium state captures cover desktop/mobile login503, contact503 (retained fields and recovery message), verifier503 (selected synthetic bundle and recovery), and FTL zero-match search (UX-005, still no explanation). Demo initial screenshots retain the unconditional sample-data/backend-unavailable wording (UX-004). No actual sign-in, email, contact delivery or backend upload occurred.

Every initial route has a viewport PNG, full-page PNG, exact viewport metadata, raw axe results (including incomplete/manual-review cases), console errors, failed requests and HTTP errors. The three browser keyboard retries include focused scanner-result screenshots after selecting Essential cookie consent and scrolling the rendered lot into view. Earlier post-tab screenshots show the document position after traversal; those are retained.

All captured initial console errors are intentional same-origin CSP rejections for Google Fonts or synthetic API401 responses. There are zero uncaught page errors, zero unexpected local failed requests and zero nonstub local HTTP errors in the42 initial combinations. Synthetic error-state503 responses are expected and recorded separately. [Per-route classified evidence](browser-ux-summary.json).

## Durable reports

- [audit report](browser-ux-2026-10-03T02-04-48-007Z/report.json)
- [keyboard report](browser-ux-2026-10-03T02-07-59-985Z/report.json)
- [states report](browser-ux-2026-10-03T02-07-59-986Z/report.json)

The summary JSON includes an explicit list of screenshots inspected visually. Initial failed setup/selector/platform attempts remain in their original artifacts and BROWSER-SESSION-LOG; the final harness fixes are retained in `scripts/browser-ux-followup.cjs`. Run modes are default `audit`, `keyboard`, and `states`; only connect() is used. The final script returns nonzero if a harness error occurs.

Lighthouse remains not covered. Physical mobile devices, screen-reader speech, authenticated real-backend flows, database persistence, real message delivery and production performance remain outside scope.
