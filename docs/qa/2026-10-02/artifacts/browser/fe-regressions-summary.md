# FE-001 and FE-004 browser witnesses

Browser follow-up pass, 2026-10-03 02:09:55–02:10:03 UTC. Actual built UI at `http://127.0.0.1:3114`; Playwright 1.63.0 connects to the existing browser server at `ws://127.0.0.1:3950/`. No browser was launched by these tests.

**Final result: exit 0; 5 strict expected failures, 1 environment skip, 0 unexpected failures.** Playwright calls expected failures “passed”; the five cases still demonstrate product defects. Only the final defect assertion is marked `test.fail()`: setup, controls, native storage probes and evidence recording run before that marker. The WebKit skip is conditional on both a successful independent native string-storage control and the exact native Blob failure.

- [Authoritative final runner JSON](fe-regression-results-2026-10-03T02-09-55-607Z.json)
- [Exact command, output and timing](20261003T020955.397348Z-fe-regressions-final-all-engines.txt)

| Finding | Chromium | Firefox | WebKit |
| --- | --- | --- | --- |
| FE-001 | Confirmed in browser | Confirmed in browser | Confirmed in browser |
| FE-004 | Confirmed in browser | Confirmed in browser | Still unverified: native IndexedDB Blob storage fails before replay |

## FE-001

The real `/tools/scan` form parses `010950600013435210LOT-10-ABC\x1d17260930` and the `LOT-21-ABC` / `LOT-17260930` variants. Each actual Lot Code form field is `LOT-`. A simple GS1 `ALPHA` lot and a Digital Link `LOT-10-ABC` both pass before the defect assertion. The native input setter plus an input event preserve literal ASCII group separator bytes; Firefox's Playwright native fill method stripped that character in the first attempt. React's real input and Parse handlers execute; the parser is not replaced.

| Engine | Raw observations | Screenshot |
| --- | --- | --- |
| Chromium | [JSON](fe-001-chromium-2026-10-03T02-09-56-289Z.json) | [PNG](fe-001-chromium-2026-10-03T02-09-56-289Z.png) |
| Firefox | [JSON](fe-001-firefox-2026-10-03T02-09-59-769Z.json) | [PNG](fe-001-firefox-2026-10-03T02-09-59-769Z.png) |
| WebKit | [JSON](fe-001-webkit-2026-10-03T02-10-02-779Z.json) | [PNG](fe-001-webkit-2026-10-03T02-10-02-779Z.png) |

Boundary: actual built scanner UI and form result; no ingestion or database persistence.

## FE-004

The real `/fsma/field-capture` page first hydrates synthetic account A. While the browser is actually offline, the test seeds one generated JPEG with the existing ownerless `savePhoto` record shape into the browser's real `RegEngineMobileDB` IndexedDB database. It verifies an unsynced record and zero upload requests. A is unmounted while offline; the synthetic session cookie and stub session identity become B, then the browser reconnects and reloads the real page. No IndexedDB data is cleared during that transition.

The actual built `AuthProvider`, `useSync`, `getPendingUploads` and upload client issue one multipart request to `/api/ingestion/api/v1/ingest/csv`. In Chromium and Firefox, the request contains the **exact JPEG bytes queued under A**, `mobile_capture_pwa_offline`, and B's current session cookie. Synthetic HTTP 422 rejection leaves the photo unsynced with `syncAttempts=1`. No upload is accepted by a backend.

| Engine | Offline A fixture and screenshot | B request/body/cookie match and screenshot |
| --- | --- | --- |
| Chromium | [JSON](fe-004-account-a-chromium-2026-10-03T02-09-56-599Z.json), [PNG](fe-004-account-a-chromium-2026-10-03T02-09-56-599Z.png) | [JSON](fe-004-account-b-chromium-2026-10-03T02-09-58-261Z.json), [PNG](fe-004-account-b-chromium-2026-10-03T02-09-58-261Z.png) |
| Firefox | [JSON](fe-004-account-a-firefox-2026-10-03T02-10-00-177Z.json), [PNG](fe-004-account-a-firefox-2026-10-03T02-10-00-177Z.png) | [JSON](fe-004-account-b-firefox-2026-10-03T02-10-01-873Z.json), [PNG](fe-004-account-b-firefox-2026-10-03T02-10-01-873Z.png) |

WebKit rejects the fixture at the native IndexedDB boundary: `UnknownError: Error preparing Blob/File data to be stored in object store`. The [same-context native control](fe-004-webkit-environment-webkit-2026-10-03T02-10-03-254Z.json) stores a string successfully and reproduces the Blob error in a separate database without Dexie or application code. A [standalone browser page control](fe004-webkit-native-idb-control-1790993369038.json) also stores strings and ArrayBuffers successfully but rejects Blob storage. This is environment/browser capability evidence, not FE-004 defect proof in WebKit.

Boundary: actual IndexedDB and client replay, with synthetic session replacement and preseeded legacy evidence. Camera acquisition, the original photo-save action, real login/logout, server authorization and successful cross-tenant persistence are **not demonstrated**. All API traffic is intercepted; external browser requests are blocked, external preconnect/DNS hints removed, service workers blocked, and HTML receives a local-only CSP.

## Setup failures retained separately

- [Initial Chromium setup results](fe-regression-results.json): exact H1 text included `RegEngine •`; the first `__Host-` cookie fixture was rejected by the browser on the HTTP URL. Corrected the selector and used a deliberately invalid local JWT fixture accepted only by the frontend claims decoder; all backend boundaries remain synthetic.
- [Second Chromium attempt](20261003T020607.365599Z-fe-regressions-chromium.txt): FE-001 reproduced. Fake-camera UI photo-save did not populate IndexedDB under the isolation CSP; this was not counted as a product finding. The final FE-004 witness seeds the ownerless legacy queue directly.
- [First six-case attempt](20261003T020731.224584Z-fe-regressions-all-engines.txt): Firefox fill stripped the group separator; WebKit scanner interaction raced hydration; WebKit Blob setup failed. None was marked expected failure.
- [Cross-browser harness correction](20261003T020826.563458Z-fe-regressions-crossbrowser-rerun.txt): scanner witnesses pass as expected failures in Firefox/WebKit; Blob setup remains blocked in WebKit.
- [Exact WebKit native error](20261003T020907.339707Z-fe004-webkit-write-diagnostic.txt): request-level diagnostics identify the native Blob storage error before the final independent controls and conditional skip.

## Rerun

The isolated local server and externally managed browser server must already be running. From the repository root:

```sh
python3 docs/qa/2026-10-02/scripts/run_logged.py browser fe-regressions-rerun -- \
  env PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3950/ \
  node frontend/node_modules/playwright/cli.js test \
  --config frontend/tests/e2e/qa-2026-10-02/fe-regressions.config.ts
```

The dedicated config has no webServer/globalSetup and cannot start the real backend. It runs only these two regression specs against all three browser projects. `QA_BROWSER_BASE_URL` may point only at a loopback host. New JSON/screenshot artifacts use timestamps; prior evidence remains intact. Product files and dependency manifests were unchanged by this lane.
