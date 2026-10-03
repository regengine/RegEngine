# Backend QA — regengine/RegEngine (static, read-only)

- **Date:** 2026-10-02
- **Branch:** main (HEAD, via GitHub API `GET /repos/regengine/RegEngine/git/trees/main?recursive=1`)
- **Method:** static read-only review. No test execution, no app run, no secrets touched.
- **Scope:** API/route inventory vs docs, input validation (money/auth/boundary), authN/Z, secret handling, dependency hygiene, error-handling consistency.
- **Files inspected (fetched from API):** `server/main.py` (1088 lines), `server/router_policy.py`, `services/shared/middleware/tenant_context.py`, `services/shared/api_key_store.py`, `services/ingestion/app/authz.py`, `services/ingestion/app/webhook_models.py`, `services/ingestion/app/webhook_router_v2/{security,validation,routes}.py`, `services/ingestion/app/proof_verify_router.py`, `services/ingestion/app/proof_recall_router.py`, `services/ingestion/app/remediation/{router,supplier_router}.py`, `services/ingestion/app/stripe_billing/webhooks.py`, `services/shared/error_handling.py`, `services/shared/tenant_context.py` (canonical resolver), `services/admin/app/auth/challenges_router.py` (excerpt), `requirements.in`, `requirements.lock` (header), `pyproject.toml`, `.env.example`, `.gitleaks.toml`, `.gitignore`, `frontend/next.config.js` (redirect section).

## Method
Checklist-driven static review + OWASP API-lite (authN/Z, tenant isolation, input validation, rate limiting, secret handling). Every finding below is backed by a fetched file; line numbers are from the fetched copies. Where a claim could not be established from fetched files it is marked "not verified".

## Route inventory vs docs

**B-1 (Medium) — `remediation` router: boot-critical in code, excluded from production allowlist, docs pull both ways.**
- `server/router_policy.py:88-96`: `COMPLIANCE_ROUTERS = {canonical_records, rules, exceptions, remediation, fda_export, chain_verification}`. In non-production, naming any of these in `DISABLED_ROUTERS` raises `RuntimeError` unless `ALLOW_DISABLE_COMPLIANCE_ROUTERS=true` (`router_policy.py:158-164`).
- `server/router_policy.py:55-81`: `PRODUCTION_ENABLED_ROUTERS` (25 names) does **not** contain `remediation`. The production exact-match check (`router_policy.py:143-156`) would reject a deploy that adds it.
- `README.md` "What The Product Does" acknowledges: "Supplier CSV manifest remediation (implemented; **excluded from the production router allowlist**)".
- `PRODUCTION_SURFACE.md` instead lists remediation under "Boot-critical routers" alongside `canonical_records, rules, exceptions, fda_export, chain_verification` and says naming any in `DISABLED_ROUTERS` makes the app "raise RuntimeError at import and refuse to boot".
- Net: the token-scoped supplier-correction workflow (`services/ingestion/app/remediation/supplier_router.py` — link exchange, 30-min sessions, token-hash-only storage, attested append-only corrections) cannot run in production. README and code agree; PRODUCTION_SURFACE.md's "boot-critical" framing is stale/contradictory. If supplier remediation is part of the FSMA evidence story told to buyers, this is a product decision, not a code bug.

**B-2 (Medium) — `PRODUCTION_SURFACE.md` no longer matches `server/router_policy.py`.**
- Doc: "Router exposure is currently controlled by: `DISABLED_ROUTERS` / `ENABLE_EXPERIMENTAL_ROUTERS`"; "Naming any of these in `DISABLED_ROUTERS` makes the app raise RuntimeError at import".
- Code: in production (`RouterPolicy.from_environment(production=True)`), `DISABLED_ROUTERS` is **rejected outright** (`router_policy.py:120-124`: "Production router policy rejects DISABLED_ROUTERS; configure the exact release-approved ENABLED_ROUTERS allowlist instead"), `ENABLE_EXPERIMENTAL_ROUTERS` is rejected (`:125-129`), and `ENABLED_ROUTERS` must match `PRODUCTION_ENABLED_ROUTERS` exactly (`:131-156`). The DISABLED_ROUTERS escape hatch the doc describes is local/test-only. The doc's mental model ("import-time RuntimeError") also predates the current structure.
- Doc line refs drifted: `proof_verify` at `server/main.py:556` still lands on the mount (actual: `if _router_enabled("proof_verify"):` at line 553, mount at 556-558 — coincidentally correct), but `proof_recall` "server/main.py:654" is stale (actual mount at 658-661). The doc's "Neither has a recorded sign-off against the Promotion Rule below — that review is outstanding (#2838)" remains the most important live statement in that file.

**B-3 (Low) — `ARCHITECTURE.md` timestamp drift.** "Last verified: 2026-07-31" for router/middleware claims; partial re-verification 2026-08-26 covered only Alembic head. The architecture doc describes `TenantContextMiddleware` as "the authoritative defense" against `X-RegEngine-Tenant-ID` spoofing — matches code (`services/shared/middleware/tenant_context.py` rejects the header without valid `REGENGINE_INTERNAL_SECRET`, hmac.compare_digest). Stale dates on control docs erode trust in the parts that are actually correct.

## Input validation (money / auth / boundary fields)

**B-4 (Low) — `kdes` dict and `traceability_lot_code` lack size caps.**
- `services/ingestion/app/webhook_models.py:184-186`: `kdes: Dict[str, Any]` — no `max_length` on the dict, no per-key/value length limits. `WebhookPayload.events` is capped at 500 (`:293-297`), and `product_description` is capped at 500 chars (`:178`), `traceability_lot_code` has `min_length=3` (`:177`) but no `max_length`.
- Practical bound is the HTTP body size (no explicit request-size limit was found in the files fetched); a 500-event batch with adversarially large `kdes` maps could bloat memory/parsing before persistence. Rate limiting is tenant-scoped (`routes.py:127`), which mitigates unauthenticated abuse. Low severity; worth an explicit request-body cap or per-field cap if threat model includes hostile tenants.

**B-5 (Positive — verified) — `IngestEvent` validation is otherwise solid.** Enum-locked `cte_type`, `quantity gt=0`, ISO-8601 timestamp validator rejecting >24h future, GLN 13-digit check-digit validation (strict by default, warn-only when `STRICT_GLN_VALIDATION=false`), unit-of-measure normalization, `require_location` model validator enforcing FSMA 204 §1.1325–§1.1350 location requirement. Batch dedup key (`routes.py:170-171`), replay window (90d/24h, `security.py`), required-KDE per-CTE checks all present.

## AuthN/Z gaps

**B-6 (Medium) — Webhook HMAC signature is opt-in; key-only auth forges events when unset.**
- `services/ingestion/app/webhook_router_v2/security.py:124-132`: `_verify_webhook_signature` returns (no-op) when `WEBHOOK_HMAC_SECRET` is unset, preserving the "migration ramp". The module's own comment (`:98-103`) admits the gap: "API-key auth alone makes any key leak (logs, proxies, .env) sufficient to forge a tenant's supply-chain events."
- Mitigations present: `webhook_hmac_configured()` feeds `/health` so ops can alarm ("F-5"), and `.env.example` does not set it (so it is off by default in every fresh deploy). This is a documented, intentional migration state — but the default posture for a new production deploy is API-key-only webhook ingest, and nothing in the boot path warns on stdout that the secret is unset. If any production tenant relies on webhook ingest, confirm `WEBHOOK_HMAC_SECRET` is set and the `/health` alarm is wired.

**B-7 (Low-Medium) — Obligation-check and compliance-alert writes fail silently on DB errors.**
- `services/ingestion/app/webhook_router_v2/validation.py:_check_obligations`: the rules SELECT is wrapped in a savepoint with rollback-and-`return []` on `SQLAlchemyError/ValueError/TypeError/RuntimeError` (`:245-249`); per-alert INSERTs use savepoints and roll back with a `logger.warning` (`:340-343`); the outer catch-all returns `[]` (`:348-350`).
- Consequence: if the obligation rules query fails (RLS denial, schema skew, UUID cast), ingest succeeds but compliance alerts are silently skipped — an operator sees a "valid" ingest with missing obligation alerts. The event itself persists (correct fail-open direction for availability), but there is no surfaced signal (no metric increment, no response field) that the obligation pass was skipped. Only debug/warning logs.

**B-8 (Positive — verified) — Tenant isolation stack is defense-in-depth and fail-closed.**
- `TenantContextMiddleware.dispatch` (`services/shared/middleware/tenant_context.py:150-215`): RLS contextvar reset at request start (#2461), spoofed `X-RegEngine-Tenant-ID` rejected unless `hmac.compare_digest(X-RegEngine-Internal-Secret, REGENGINE_INTERNAL_SECRET)`; extraction failures on protected paths → 401, never fall-through. `get_current_tenant_id` raises 401 when no tenant (fail closed). Spoof attempts counted (`tenant_header_rejected_total`, deliberately unlabelled to avoid cardinality explosion — #2858) and logged with peer IP.
- `require_permission` (`services/ingestion/app/authz.py:331-404`) chains principal resolution + tenant cross-check + RBAC scope + per-permission RPM rate limiting. Ingest route additionally requires `X-RegEngine-API-Key` presence, HMAC signature, active subscription, and `Idempotency-Key` (`webhook_router_v2/routes.py:104-117`).
- README's `409 E_TENANT_MISMATCH` / `401 E_NO_PRINCIPAL` / `401 E_NO_TENANT` claim verified in `services/shared/tenant_context.py:110-183` (canonical resolver, not the middleware — a two-file design; both reviewed).

**B-9 (Positive — verified) — API key storage: peppered HMAC-SHA256 with legacy fallback.**
- `services/shared/api_key_store.py:71-106`: `REGENGINE_API_KEY_HASH_PEPPER`-based `hmac.new(pepper, key, sha256)`; unpeppered legacy SHA-256 accepted as fallback candidate (`api_key_hash_candidates`). Lookup hashes passed via session GUC (`set_config('regengine.api_key_lookup_hash_current', ...)`), so raw keys never reach SQL text.
- OTP challenges: `crypto_service.generate_secure_otp()` with only digests persisted (`services/admin/app/auth/challenges_router.py:229-235`), challenge TTL, attempt counting, rate-limited OTP generation (`:207`).

**B-10 (Positive — verified) — Stripe webhook handling order is correct.**
- `services/ingestion/app/stripe_billing/webhooks.py:698-760`: missing `STRIPE_WEBHOOK_SECRET` → 500 (fail closed); signature verified via `stripe.Webhook.construct_event` **before** any rate-limit budget consumption (#2929 — unverified floods can't burn the genuine-traffic bucket); verified events keyed from the envelope, not client headers. Idempotency: dedup claim taken before handler, released on handler failure (#2818) so a failed `checkout.session.completed` is retryable instead of permanently dropped as "duplicate".
- Tenant-exempt billing webhook paths (`/api/v1/billing/webhooks`, `/api/v1/billing/webhook/stripe`) in `_TENANT_EXEMPT_PATHS` are auth-correct only because of the signature verification above — verified present.

## Secret handling

**B-11 (Positive — verified) — No live secrets in the tree; scanning gates are real.**
- `.env.example`: all values placeholders/empty; dev-only defaults clearly marked (minio, `OBJECT_STORAGE_ENDPOINT_URL=http://minio:9000`, dev bucket names) with comments warning they "MUST be overridden in prod".
- Tree-wide scan (3,832 entries, 3,267 blobs): no committed `.env`, `*.pem`, `*.key`, `id_rsa*`, `credentials*`, or `secrets*` files other than the template/baseline/config files. `.gitignore` covers `.env`, `.env.*` with `!.env.example` carve-out (`:42-48`).
- `.gitleaks.toml`: extends upstream defaults (`useDefault = true`) — the config's own comment documents a past incident (#2809) where the config had only an allowlist and zero rules, so the "Secrets Scan (gitleaks)" gate could never fail. Fixed in-tree.
- `.github/workflows/security.yml`: tool-pinning gate rejects non-SHA-pinned action refs and unpinned semgrep/pip-audit installs across every workflow (verified the gate script header); secrets scanning + detect-secrets also run.
- `docs/operations/CREDENTIAL_ROTATION_RUNBOOK.md` (current HEAD, 52 lines): the 2026-08-02 copy plan's S1 claimed "~lines 61-73 appears to contain literal old secret values" — the file no longer contains any secret values or lines 61-73; it was rewritten to policy-only content. Remediation appears complete for HEAD; git-history scrub (BFG) was recommended in the plan — not verifiable statically from HEAD alone.

**B-12 (Low) — requirements.in references a poetry section that does not exist.**
- `requirements.in:2-3`: "Mirrors pyproject.toml [tool.poetry.dependencies]" — `pyproject.toml` contains only `[project]` metadata + tool configs; the real mechanism is pip-tools (`requirements.lock` compiled with `--generate-hashes`, verified pinned `==` + multi-hash entries). The authoritative path is confirmed (`pyproject.toml` itself says: "The single source of truth is requirements.in ... compiled to requirements.lock"). Stale comment only; dependency hygiene itself is good (floors in `.in`, exact pins + hashes in `.lock`, `--require-hashes` install).

## Error handling

**B-13 (Positive — verified) — Centralized, normalized, client-safe error envelope.**
- `services/shared/error_handling.py`: `install_exception_handlers` (wired at `server/main.py:378-380`); every client error gets `{type, message}` plus preserved original fields (`_normalized_dict_detail`, #2863 — documents the prior three-incompatible-shapes drift); 5xx details are sanitized to a generic message unless `ClientSafe`; Sentry `before_send` stamps tenant/correlation/request tags. Server-error leakage is explicitly defended.
- 401/403/409/429 semantics are consistent across `authz.py` (401 missing key, 403 insufficient scope, 409 tenant mismatch at the canonical resolver, 429 rate limit).

## Ghost-workflow verification
- `.github/workflows/` on main contains **24** files (listed in the consolidated report). No file is named `BuildFailed`; a case-insensitive search for "buildfailed" across all 3,832 tree entries returned zero matches. The orphaned workflow record (id 342065254, blank name, path literally "BuildFailed", state "deleted") cannot correspond to any file on current main. **Confirmed: no main-branch workflow file could match the orphan record.** (inflow-lab wf 370344878 is out of scope for this repo.)

## What was inspected vs not
- Inspected: router/authN/authZ/tenant/validation/error/secret/dependency surfaces listed above; docs-vs-code for router policy, README capability table, ARCHITECTURE, PRODUCTION_SURFACE, .env.example, security workflow gates.
- NOT inspected (static review only, no execution): Alembic migration SQL, scheduler jobs, NLP/graph services, most admin routes beyond session/challenge excerpts, email-ingest, EPCIS/EDI parsers, CSV ingest internals, all 3,000+ unopened files. Findings are limited to what the fetched files establish.
