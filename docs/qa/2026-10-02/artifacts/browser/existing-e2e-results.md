# Browser follow-up pass — existing E2E suite

PR: opened by orchestrator

CI status: pending at time of writing

The unchanged existing suite was collected and exercised in genuine Chromium, Firefox, and WebKit against the isolated built frontend at `http://127.0.0.1:3114`. This is browser-only local coverage, not an authenticated full-stack pass. No database, production API, real account, deployment, or provider was contacted. All 90 original cases per engine were collected; the new FE reproduction directory was excluded from these counts.

| Engine | Version | Passed | Failed, including timeouts | Skipped | Discovered | Environment failures | Harness failures | Product failures |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Chromium | 153.0.8010.12 | 21 | 8 | 61 | 90 | 6 | 2 | 0 |
| Firefox | 155.0 | 20 | 9 | 61 | 90 | 6 | 3 | 0 |
| WebKit | 26.6 | 18 | 11 | 61 | 90 | 7 | 3 | 1 |
| Total | Playwright 1.63.0 | 59 | 28 | 183 | 270 | 19 | 8 | 1 |

Each engine has one timeout, already included in its failed count. No run was interrupted. Actual engine names, versions, and browser user agents were read from fresh server connections in [engine probe](existing-e2e-engine-probe.json).

## Attempts and evidence

1. **Stock local config:** [02:03:33 UTC log](20261003T020333.193469Z-existing-e2e-stock-local-attempt.txt), exit 1 before tests. The stock config has only a Chromium project and launches `start-e2e-backend.sh`, whose PostgreSQL/bootstrap work is prohibited in this browser-only pass. The safety wrapper refused that helper before execution. A green stock local full-stack run is not established.
2. **First browser-only fallback:** [02:03:38 log](20261003T020338.645294Z-existing-e2e-local-browser-suite.txt), [raw JSON](existing-e2e-local-browser.json), exit 1; 50 passed / 37 failed / 183 skipped. Two original tests per engine used their hardcoded localhost:3001 fallback rather than the config's localhost:3114 base URL. WebKit also rejected the QA interceptor's synthetic HTTP 307 fulfill. Both harness issues were corrected for the next run. All first-run evidence is retained.
3. **Authoritative corrected run:** [02:06:10 log](20261003T020610.930546Z-existing-e2e-final-local-browser-suite.txt), [raw JSON](existing-e2e-final-local-browser.json), [complete per-case classification and skip reasons](existing-e2e-final-local-browser-summary.json), exit 1; 138.49 seconds. It sets `PLAYWRIGHT_BASE_URL=http://127.0.0.1:3114` solely to align the original tests' absolute URLs with the local fixture; no external target was used. All three projects were explicit in the QA config. Protected-page redirects now follow only verified same-origin locations. Original test files were unchanged.

The safety envelope reused `node-isolation.cjs`, scrubbed environment through `run_logged.py`, blocked database/bootstrap helpers and OTP-fixture deletion, intercepted off-host browser requests, removed preconnect/DNS hints from document HTML, added same-origin CSP, and disabled service workers. Credentials were intentionally absent. The raw frontend's service URLs pointed to an unavailable loopback backend; API responses were not replaced with successful synthetic data by this lane. Page-specific mocks already present in the original suite still ran. CSP and network isolation limit conclusions about third-party integrations.

## All 28 failures classified

| Failure group | Chromium | Firefox | WebKit | Reason and evidence |
| --- | ---: | ---: | ---: | --- |
| Database/OTP setup prohibited | 5 | 5 | 5 | Both `auth-flow.spec.ts` tests and three `security-release-gate.spec.ts` tests invoke DB seed/OTP cleanup helpers without self-skipping. The QA guard intentionally refuses them. No auth product conclusion. |
| Sandbox sample evaluation unavailable | 1 | 1 | 1 | `sandbox-front-door.spec.ts:80` requires a working backend evaluator; the local frontend shows the recoverable service-unavailable state. Its availability helper treats every non-404 response, including unavailable responses, as mounted. No evaluation result was invented. |
| Stale Password control expectation | 1 | 1 | 1 | `rbac-gates.spec.ts:45` first passes the login redirect and email assertion, then waits for the removed Password control through `support/ui-auth.ts:4`. Current UI is OTP/passkey. This is test drift. |
| Error-page regex false positive | 1 | 1 | 1 | `security-audit-fixes.spec.ts:749` scans `body.textContent`, which includes Next inline serialized script text. The substring `config` matches public marketing prose “where configured data supports the request”. Visible `innerText` has no matching term; [browser witness](existing-e2e-error-page-triage.json). No exposed secret was found. |
| Chromium-specific aborted-fetch wording | 0 | 1 | 1 | `login-dashboard.spec.ts:113` expects “Failed to fetch”. Firefox shows “NetworkError when attempting to fetch resource.”; WebKit shows “Load failed”. Both are visible recoverable alerts. The assertion is engine-specific. |
| WebKit/macOS keyboard setting | 0 | 0 | 1 | `login-dashboard.spec.ts:71` assumes Tab moves email to Continue. An independent plain HTML input/button control reproduces input→BODY on Tab and input→button on Alt+Tab, while Chrome/Firefox Tab reaches the button; [control evidence](existing-e2e-keyboard-platform-control.json). This is environment behavior, not a product-specific inaccessible button. |
| **UX-008, Low — clipped tour card** | 0 | 0 | 1 | `inflow-lab-tour.spec.ts:105` reproduces a WebKit-only lower edge overflow at the first dashboard preview tour step. See below. |

## All 183 skips classified

Each engine has the same 61 skipped cases: 8 require primary signed-in credentials; 24 require the passwordless local backend/OTP outbox; 23 require admin credentials; 4 require a dedicated sysadmin; 1 requires a scoped demo API key; and 1 is the opposite branch of the sandbox availability test. Thus 180 skips are auth/backend/key prerequisites and 3 are conditional sandbox branches. The sandbox annotation says “router is mounted” because its helper accepts any non-404 status; this is not proof that a working evaluator exists. Every case title and original annotation is retained in the summary JSON. Missing credentials were not read or requested.

## UX-008 browser witness

In WebKit at 1440×900, navigate to `/tools/inflow-lab-dashboard-preview`, open “Learn to operate it step by step”, and remain on Step 1 of 7. The card's bottom stays at **918.15625 CSS pixels**, 18.15625 below the viewport. The Next button's bottom is **901.15625**, partially clipped by about 1.16 pixels. The same geometry remains after 0.9, 2.9, and 7.9 seconds, so this is not merely a screenshot during animation. Two full-suite runs also failed at 917.4375 and 917.796875 pixels. Chromium/Firefox controls remained within the viewport in the settling probe.

Evidence: [settling samples](existing-e2e-tour-settling.json), [WebKit screenshot](existing-e2e-tour-webkit-settled.png), [Chromium control](existing-e2e-tour-chromium-settled.png), [Firefox control](existing-e2e-tour-firefox-settled.png), [probe log](20261003T020801.222484Z-existing-e2e-tour-settling.txt). The reusable witness is `scripts/existing-e2e-tour-probe.cjs`. No real backend is required.

Likely cause, **inference rather than a validated fix**: `frontend/src/components/ui/tutorial.tsx:94` measures `getBoundingClientRect()` while the card animates scale from 0.9 to 1 at line 289, then the clamp at line 228 uses that cached height. Measure untransformed size or recompute after the animation. No product source or original test assertion was changed.

The no-secret/public-surface pass does not establish authenticated tenant isolation, OTP delivery, WebAuthn lifecycle, saved ingestion evidence, or backend persistence. The original suite is not green; the table above explains every failure and skip.

## Browser follow-up pass — authoritative per-hop proxy rerun

The 02:15:32 UTC run below supersedes the earlier run's isolation claim. Gate review correctly identified that Playwright invokes a route handler only for the first URL in a redirect chain. The previous same-origin `route.continue()` branch did not prove that later hops or the final redirected HTML were re-intercepted. Earlier results and artifacts remain retained; the claim above that redirected document targets were necessarily intercepted is withdrawn.

The corrected QA path is browser → `127.0.0.1:3115` proxy → guarded Next server at `127.0.0.1:3114`. The proxy makes one fixed-loopback `HTTPConnection` request per incoming request and never follows redirects itself. It validates every outgoing Location against the exact upstream scheme, host, and port; rejects credentials and off-origin destinations; rewrites allowed redirects back to port 3115; strips preconnect/DNS hints and adds restrictive CSP to every final HTML response, including documents reached after redirects. Browser routing separately rejects initial requests outside the proxy origin. The transport deliberately changes upstream Host, removes compression/Link/Refresh headers, and replaces CSP; it is not byte-transparent and does not establish production-header compatibility.

The [adversarial local HTTP probe](existing-e2e-proxy-safety-check.json) passes using an upstream transport spy: a local first hop redirects to another local hop whose protocol-relative `//offhost.invalid` Location is blocked with 502; a safe chain remains on port 3115; final HTML loses off-host hints and receives CSP. The spy confirms every upstream call is fixed to `127.0.0.1:3114`; no external network was contacted by this probe. HTTPS, a different port, hostname alias, and credentialed redirect cases are also rejected. Independent gate review found no blocker in the corrected proxy or probe.

The unchanged 270-case suite was rerun through this proxy: [02:15:32 UTC command log](20261003T021532.827337Z-existing-e2e-proxy-local-browser-suite.txt), [raw report](existing-e2e-proxy-local-browser.json), and [authoritative per-case classifications](existing-e2e-proxy-local-browser-summary.json). Exit 1, **139.40 seconds**. Counts and classification are unchanged:

| Project | Passed | Failed | Skipped | Environment failures | Harness failures | Product failures |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Chromium | 21 | 8 | 61 | 6 | 2 | 0 |
| Firefox | 20 | 9 | 61 | 6 | 3 | 0 |
| WebKit | 18 | 11 | 61 | 7 | 3 | 1 |
| Total | 59 | 28 | 183 | 19 | 8 | 1 |

All original 90 cases per engine were collected. Each engine's one stale-password timeout is included in its failed count. All 28 failure identities and all 183 skip reasons match the previous detailed tables. There were no new Origin/Host mismatch failures. This remains a local browser-only run without database/authenticated-backend proof.

UX-008 also reproduces with the corrected isolation: the full-suite WebKit tooltip bottom is **918.15625** at a viewport height of 900. In the separate [proxy settling probe](existing-e2e-tour-proxy-settling.json), its bottom remains **915.96875** after 0.9, 2.9, and 7.9 seconds. The Next button bottom in this particular settling run is **898.96875**, fully inside the viewport; clipping the card is repeatable, while clipping the button is not invariant. Chromium and Firefox card bottoms are 892. See [WebKit screenshot](existing-e2e-tour-proxy-webkit-settled.png), [Chromium control](existing-e2e-tour-proxy-chromium-settled.png), [Firefox control](existing-e2e-tour-proxy-firefox-settled.png), and [02:15:38 probe log](20261003T021538.799768Z-existing-e2e-proxy-tour-settling.txt). The previously proposed measurement cause remains an inference; no product fix was applied.

The owned port-3115 proxy stopped cooperatively and its logger exited 0: [server lifecycle](20261003T021531.650153Z-existing-e2e-per-hop-proxy-server.txt). A separate [listener readback](existing-e2e-proxy-cleanup.json) returned connection refused at 02:18:22 UTC. The root-owned Next server and orchestrator browser service were left for their owners.
