# UX QA — regengine/RegEngine (static walkthrough, read-only)

- **Date:** 2026-10-02
- **Branch:** main (via GitHub API)
- **Method:** heuristic evaluation by following `README.md` and linked docs exactly as a brand-new user/developer would. No execution, no browser, no signup — every step below was checked against fetched file content.
- **Docs followed:** `README.md` (401 lines, full), `docs/engineering/ROUTER_SURFACE.md` (excerpts), `.env.example`, `docker-compose.dev.yml` (existence), `frontend/README.md` (existence, not fully read), `docs/PRODUCT_DESCRIPTION.md` (existence).

## Walkthrough: new developer, local backend

**Step 1 — Prerequisites.** README says: Python 3.11 or 3.12 (`pyproject.toml` declares `>=3.11,<3.13` — verified in fetched file), Node/npm, Docker. Clear and correct.

**Step 2 — Backend setup.** The README gives an exact sequence: `python3 -m venv venv` → `pip install --require-hashes -r requirements.lock` → export `POSTGRES_PASSWORD` → `docker compose -f docker-compose.dev.yml up -d` → three `DATABASE_URL`-family exports → `./scripts/run-migrations.sh` → `./venv/bin/python scripts/create_test_api_key.py`. Then: "The raw key is printed once — pass it in the `X-RegEngine-API-Key` header. In development the backend validates DB-backed keys only when the server process runs with `ENABLE_DB_API_KEYS=true`." Coherent, ordered, copy-pasteable. **No friction found in this path** (static reading only; not executed).

**U-1 (Medium) — Passwordless login dead-ends without Resend.** README documents: "If `RESEND_API_KEY` is unset outside E2E mode, codes are not delivered at all — the challenge flow drops the code with only an error log." A new developer following the README to "exercise the full customer experience" via the frontend login will hit a login page that accepts their email, shows "If this address is eligible, a sign-in code is on its way," and never delivers a code — with the failure visible only in a server log. The `.env.example` leaves `RESEND_API_KEY` unset (it isn't even listed in the fetched `.env.example`). The copy is honest but the UX is a silent dead end; the login page has no way to surface "email delivery is not configured." Recommend: dev-mode banner on `/login` when `RESEND_API_KEY` is unset, or document the expected no-code behavior in the README's local-dev section.

**U-2 (Medium) — Supplier remediation is implemented but unreachable in production; the buyer dashboard exists.**
README capability table: "Supplier CSV manifest remediation (implemented; **excluded from the production router allowlist**)" and "Buyer remediation dashboard (requires the remediation API to be enabled...)". A buyer evaluating the product from the repo sees a complete remediation story (manifest intake → correction links → revalidation → release → evidence bundles) that cannot be turned on in production without editing `PRODUCTION_ENABLED_ROUTERS` in code — the exact-match production check (`server/router_policy.py:143-156`) rejects any `ENABLED_ROUTERS` value that isn't the 25-name approved set. For a compliance product whose pitch is supplier-data correction, the gap between "implemented" and "deployable" is the single most product-relevant thing a new technical evaluator will trip over. This is the same fact as backend finding B-1; surfacing it here as the UX consequence.

**U-3 (Low) — Metered billing reports nothing automatically.** README "Important Limitations" discloses: nothing periodically calls `report_tenant_usage_to_stripe`; usage accumulates in `billing.tenant_usage_counters` until an operator calls `POST /api/v1/billing/usage/report`. There is no frontend surface and no scheduler job ("documented, unbuilt follow-up"). A new operator reading the billing docs would reasonably assume metering flows to Stripe; it doesn't. Disclosure is present and honest, but the README's main billing row ("Subscription-gated access and persisted usage metering") reads as a working feature while the limitation is several screens below. Fine for engineers; risky for anyone quoting the feature to a customer.

**U-4 (Low) — Two auth code paths, acknowledged.** README "Known authentication caveat": passwordless cookie sessions and a legacy Supabase-session flow in `frontend/src/proxy.ts` coexist; "Treat auth behavior as code-and-test verified, not marketing-copy verified." Honest; a new developer debugging auth must determine which path a given route uses. The `frontend/src/lib/auth-context.tsx` is cookie-session-only, so the legacy path is proxy-only. Acceptable with the warning present.

**U-5 (Low) — CTE persistence mid-migration is well-documented but operationally sharp.** README discloses the dual-write retirement (legacy `fsma.cte_events` vs canonical `fsma.traceability_events`), consumer-specific cutover flags, and that "FDA CSV export v1 retains a legacy code default" with canonical reads behind `FDA_EXPORT_V1_READ_CANONICAL`. A developer asserting "exports come from the canonical chain" must check the flag per export path. The cutover runbook exists (`docs/persistence/dual-write-cutover.md` — verified present). Documented correctly; the UX risk is a future reader missing it and asserting the wrong read path in a customer conversation.

## Walkthrough: new user, public proof surface

**Step 1 — regengine.co/proof → /verify.** README links the public proof surface (synthetic CSV, EPCIS bundle, audit ZIP) and the `/verify` drop-a-bundle verifier backed by `POST /api/v1/proof/verify` (fetched: 5MB cap, 64-entry/25MB-decompressed zip-bomb guards, Merkle recompute, fail-closed on missing declared root, rate-limited 10/min/IP). The contract is coherent: verification is structural over caller-supplied bytes, "does not independently recompute the persisted database chain or authenticate the package issuer" — and the docstring says so explicitly. **No deception found; the honesty level here is high.**

**U-6 (Info) — Public unauthenticated endpoints are deliberately promoted.** `PRODUCTION_SURFACE.md` notes `proof_verify`/`proof_recall` "mount unconditionally in production" — the code gates them through `_router_enabled()` but they are in the production allowlist and are not experimental, so the practical effect matches. Rate limits (10/min and 5/min per IP) and the 5MB cap are the DoS controls. The promotion-rule sign-off is recorded as outstanding (#2838). A new security reviewer will ask for that sign-off; it's already flagged in the doc.

## Documentation accuracy (heuristic: does the map match the territory?)

- All 16 doc links in the README's Documentation Map were checked against the main-branch tree: **all resolve** (0 broken links).
- README's "This README describes behavior that is visible in checked-in code, configuration, tests, and runbooks" holds for every claim spot-checked (router policy, remediation exclusion, dual-write cutover, billing follow-ups, OTP/Resend behavior, E2E outbox gating).
- `ARCHITECTURE.md` carries a "Last verified: 2026-07-31" banner with honest scoping of what was re-checked — the right pattern; the dates are just aging.

## Heuristic summary (Nielsen-style, static)

| Heuristic | Verdict |
|---|---|
| Visibility of system status | Good in docs; mixed in product (silent OTP drop — U-1) |
| Match with real world | Strong (FSMA vocabulary, honest "Important Limitations") |
| Error prevention | Strong backend (fail-closed auth, envelope normalization); weaker frontend error copy on the preferred hook (F-3) |
| Consistency | Weakest area: copy contradictions (F-1), org-term inconsistency, `/fsma` vs `/fsma-204` |
| Help & documentation | Excellent README; doc-link integrity verified 16/16 |
| Honesty of marketing claims | Self-policed (copy plan, promise audit) but remediation items appear open (F-1) |

## What was NOT walked
- No browser: actual page rendering, navigation flows, form behavior, mobile, performance.
- No signup/login attempt; no API calls; no Docker/DB run.
