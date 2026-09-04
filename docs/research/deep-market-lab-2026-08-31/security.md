# Security and evidence review — Deep Market Lab

Date: 2026-08-31. Role: `security_review`. Scope: the ingestion → persisted evidence → export boundary in checkout `41aa11c5`. This is a docs-only review, not a penetration test, certification, or legal assessment.

## Decision

The repository has useful tenant, authorization, and export-failure controls, but the tested implementation does not support an unrestricted claim that exported records have been independently verified against their original content or that every export can be reproduced later. Two offline reproductions at the inspected base demonstrated concrete gaps. The integration fixes package interoperability, rejects declared failed-chain and package-metadata disagreement cases, and repairs the historical verifier's privacy-mode/type mismatches. It does not independently recompute the persisted chain, establish current-content verification or immutable historical membership, or prove production enforcement. Treat those remaining limits as release gates for a pilot that depends on verified regulatory evidence; they do not prevent an internal demonstration using synthetic records.

No unauthenticated cross-tenant disclosure was demonstrated. No production environment, database grants, deployed migration state, secrets, or external services were inspected. Statements in source comments about what regulation requires were not treated as legal evidence.

## Controls supported by repository evidence

- **Authenticated tenant context:** `services/shared/tenant_context.py:93`, `resolve_tenant_context`, takes the authoritative tenant from accepted principal state, rejects missing tenant context, and checks competing request claims. Its database helper validates UUIDs and sets a transaction-local GUC with bound parameters (`:344`, `:421`). This supports tenant isolation when routes use it and the runtime role is subject to RLS; it does not prove every route does.
- **Shared master-key safeguards:** `services/shared/auth.py:317` requires a valid `X-Tenant-ID` for accepted preshared keys. The test bypass requires an explicit development/test environment (`:279`). Ingestion's separate `_is_dev_env` treats unset, staging, and unknown environments as requiring authentication (`services/ingestion/app/authz.py:56`). Master keys still confer broad authority and should remain server-side.
- **Cross-tenant wildcard defense:** `require_permission` rejects query/header tenant mismatches even for tenant keys with `*` scope (`services/ingestion/app/authz.py:419`). This is a useful distinction between permission breadth and tenant breadth. The older `tenant_validation.resolve_tenant` still treats wildcard principals differently (`:40`); migrating its callers requires route-level testing, not assuming the two resolvers are equivalent.
- **Evidence and billing outages:** ordinary FDA exports return HTTP 503 if the audit insert/commit fails (`services/ingestion/app/fda_export/router.py:317`). The subscription gate defaults to 402 for absent subscription state and 503 for Redis failures, with an explicit operator fail-open override (`services/ingestion/app/subscription_gate.py:10`, `:31`).
- **Persistence controls:** canonical writes establish tenant context and serialize per-tenant chain updates (`services/shared/canonical_persistence/writer.py:57`, `:85`, `:209`). SQL migrations force RLS on event, KDE, chain, and export-log tables (`alembic/sql/V002__fsma_cte_persistence.sql:217`). Presence in source does not establish successful deployment.
- **CSV handling:** the exporter sanitizes cells and defaults to redacting selected identifying fields; unredacted export requires a separate permission (`services/ingestion/app/fda_export_service.py:169`; `services/ingestion/app/fda_export/router.py:98`). Arbitrary free text is not proven free of personal data merely because named columns are redacted.

## Findings

### S1 — High: “verified chain” does not verify current event content

`CTEPersistence.verify_chain` reads stored chain hashes, previous hashes, sequence numbers, and matched event IDs (`services/shared/cte_persistence/core.py:1541`). It counts non-rejected events and checks for missing/orphan chain rows. Its cryptographic check recomputes a chain hash from the **stored** `event_hash` (`:1631`); it never loads and rehashes current quantity, timestamps, locations, or KDE values.

An offline probe used the real class and hashing functions with SQLAlchemy and an in-memory SQLite database. After inserting one matching event and chain row, it changed the event's quantity from 10 to 999 without changing stored hashes. Results:

```json
{"baseline_valid":true,"after_quantity_mutation_valid":true,"after_errors":[],"quantity_changes_recomputed_hash":true,"description_changes_recomputed_hash":false}
```

The quantity change would change a freshly computed event hash, but the verifier still approves the stored chain. Separately, `compute_event_hash` intentionally excludes `product_description`, three description KDE keys, and does not include `location_name` (`services/shared/cte_persistence/hashing.py:64`). An identity hash over selected fields must not be described as a digest of every exported field.

The impact reaches the normal export: the router calls this verifier (`services/ingestion/app/fda_export/router.py:294`) and emits `X-Chain-Integrity: VERIFIED` from its boolean result (`:432`). An internally consistent chain can therefore accompany changed event content without this verifier detecting the change.

**Limits:** SQLite was deliberately used only to test verification logic, without PostgreSQL triggers. This is not proof that an external caller can modify production records. The checked-in append-only trigger is an additional defense. Its `fsma.allow_mutation` branch returns `OLD`, not `NEW` (`alembic/versions/20260505_5ac9e7b1d402_v078_orphan_migration_forward_ports.py:1338`). On a `BEFORE UPDATE` trigger this may retain the old values rather than apply the requested change; the GUC is not evidence of a working in-place correction path. Live role grants, actual deployed trigger behavior, and protection of KDE rows remain unverified.

**Gate/falsifier:** replay a persisted fixture, then independently alter each evidence-bearing field in an isolated database. Verification must flag changed content, missing records, added records, and sequence changes. Distinguish content verification from chain consistency in responses. Preserve a versioned canonical representation and an independently retained digest/checkpoint; no new ledger infrastructure is needed to establish this invariant. A mutation that continues to return “verified” falsifies the content-integrity claim.

### S2 — High: historical export regeneration remains incomplete

Three discrepancies were concrete at the inspected base `41aa11c5`:

1. The producer hashed `_generate_csv(events, include_pii=include_pii)` (`router.py:292`), while the baseline `verify_export_handler` called `_generate_csv(events)` with its default redaction mode. The baseline export-log query did not recover the original mode. With the real CSV generator, unchanged fixture data, and fake database reads, an export originally generated with `include_pii=True` returned `hashes_match=false` and `MISMATCH_DETECTED`.
2. Full-export generation stored `fda_export_all` or `fda_export_all_package` (`router.py:634`), while the baseline verifier recognized different no-TLC labels. Direct calls to the real handler with each producer type returned HTTP 409.
3. The verifier rereads current rows and transformation membership using the original date/TLC filters (`verification.py:59`). It does not select a stored list of event versions or an as-of ingestion boundary. Legitimate later arrivals can change a historical result. Recall product/location filters are explicitly acknowledged as incompletely persisted (`:95`), so some recall exports cannot be regenerated from their audit rows.

**Post-integration update:** the verifier now reads the nine-column audit tuple, uses the recorded `include_pii` value, recognizes both full-export producer labels, and shares the producer's full-export reconstruction helper. The [updated offline probe](export_verification_probe.py) verifies unchanged single-TLC and full-export fixtures in both privacy modes and confirms that audit rows without a recorded privacy mode and recall rows with incomplete filters fail closed with HTTP 409. Its [integrated output](export_verification_results_integrated.json) preserves the [baseline output](export_verification_results.json) separately.

The first two baseline defects caused false alarms or unavailable verification and are repaired locally. No data exfiltration was demonstrated. Current-row regeneration still cannot prove the exact historical member set after legitimate later arrivals. A retained package hash proves equality to a particular byte sequence only when that trusted hash and artifact are retained; the manifest alone does not authenticate its issuer.

**Gate/falsifier:** test producer → durable artifact/log → verifier for CSV and package, filtered and full exports, both PII modes, empty results, and late-arriving events. Persist immutable event/version membership, formatter version, relevant filters, redaction mode, and the actual artifact or sufficient reproduction inputs. Verification must distinguish artifact corruption from legitimate changes to current data. An unchanged artifact that is called corrupt, or an ordinary producer type that receives 409, falsifies the regeneration claim.

### S3 — Medium: artifact deduplication also deduplicates actor evidence

The export fingerprint includes tenant, export type, TLC/date filters, count, and content hash, but not `generated_by` or request identity (`services/shared/cte_persistence/core.py:1859`). `log_export` returns an existing row on that fingerprint conflict (`:1971`). Thus two different authorized actors exporting identical content can share one durable export row identifying only the first actor.

The router emits a structured audit line for each request (`router.py:352`), which could compensate if that stream is durably retained and attributable. Its delivery, retention, access controls, and reconciliation against database rows were not verified. Artifact deduplication is reasonable; equating it with an access audit trail is the risk.

**Gate/falsifier:** make identical exports as two distinct principals. A reviewer must recover both actors and attempts after worker restart without relying on transient memory. Keep artifact identity separate from append-only access/generation-attempt records, or demonstrate an existing durable audit stream satisfying this requirement.

## Runtime and database questions that remain open

Admin's missing-database fallback is explicitly restricted to local development/test-style environments without cloud markers (`services/admin/app/database.py:65`, `:111`). An explicitly configured SQLite URL takes a separate branch (`:88`), so deployment validation must establish PostgreSQL rather than relying on the fallback guard alone. Shared database helpers can return `None` when session construction fails (`services/shared/database.py:159`, `:172`); each consumer must refuse to report durable success without persistence.

The generic `AuditLogger` defaults to an in-memory backend (`services/shared/audit_logging/writer.py:42`), whose bounded buffer evicts records (`storage.py:88`), and its HMAC predecessor state is process-local (`integrity.py:37`, `:82`). This review did not establish that this generic logger is the production audit backend; multiple similarly named loggers exist. Do not infer durable, global audit completeness from this implementation alone.

Export history and verification create fresh sessions and query the RLS-protected export log before visibly setting the tenant GUC (`router.py:798`; `verification.py:37`). Tests mock those database reads. Exercise these exact routes as the intended non-superuser role on a clean pooled connection; the impact under deployed policies is **not verified**. Do not “fix” an empty result by granting BYPASSRLS.

Auth startup validation suppresses fatal configuration errors when `CI` or `GITHUB_ACTIONS` is truthy (`services/shared/auth.py:60`). Production-like boot tests must therefore include cases without those flags. The passing CI-oriented tests are not proof that deployment configuration is correct.

## Executed verification

System `python3 -m pytest ... -q --no-cov` initially failed with `No module named pytest`. The existing repository `.venv/bin/python3` was usable; nothing was installed. Commands below ran from the repository root. `-o addopts=''` was used for an explicit result summary.

```bash
.venv/bin/python3 -m pytest services/shared/tests/test_auth_fail_closed.py services/shared/tests/test_auth_preshared_tenant_required_1068.py services/shared/tests/test_tenant_context.py services/shared/tests/test_tenant_context_set_guc.py -q --no-cov -o addopts=''
# 40 passed in 2.60s

.venv/bin/python3 -m pytest services/ingestion/tests/test_authz_1342.py services/ingestion/tests/test_fda_export_router_1342.py services/ingestion/tests/test_fda_export_verification_1342.py services/ingestion/tests/test_subscription_gate_fail_closed.py -q --no-cov -o addopts=''
# 171 passed in 2.43s

.venv/bin/python3 -m pytest tests/shared/test_cte_persistence_verify_chain_1314.py services/shared/cte_persistence/tests/test_append_only_1334_1335.py services/shared/tests/test_cte_persistence_log_export_1655.py tests/shared/test_canonical_persistence_tenant_context.py -q --no-cov -o addopts=''
# 37 passed, 9 failed in 0.39s
```

Five failures reference a missing old migration filename, `20260420_v073_cte_events_append_only_trigger_1334.py`. The replacement trigger exists in the forward-port migration cited above, so these failures do not prove triggers are absent. Four failures expect literal `SET LOCAL app.tenant_id`; current code calls `set_config(..., true)`. These are stale-test assertions, not demonstrated tenant leaks. They should be repaired without weakening behavioral coverage.

The two original inline Python probes used `env -i`, test-only settings, the existing virtual environment, real production functions, and either SQLite memory tables or patched database reads. They contacted no database server. Their observed outputs are recorded under S1 and S2; the original S2 output remains in [the baseline JSON](export_verification_results.json). The updated `export_verification_probe.py` keeps the same environment clearing, network denial, and synthetic patched reads while checking the integrated contract:

```bash
.venv/bin/python3 docs/research/deep-market-lab-2026-08-31/export_verification_probe.py
# Exit 0: single-TLC and both full-export labels verify in both privacy modes;
# missing legacy privacy metadata and incomplete recall filters return HTTP 409.
```

Here exit zero confirms only the scoped repaired behaviors and intentional fail-closed cases. It is not a product acceptance result. No production code was changed by the original research run; the later integration changed the package and historical-verifier contracts with regression coverage.

The post-integration package-verifier selection also ran locally:

```bash
.venv/bin/python3 -m pytest services/ingestion/tests/test_proof_verify_router.py -q --no-cov -o addopts=''
# 21 passed
```

The selection covers API/SDK acceptance of declared `VERIFIED` and `PARTIAL` packages and rejection of byte tampering, a self-consistent `UNVERIFIED` chain, manifest/hashed-chain disagreement, and undeclared or duplicate ZIP members. It does not supply an independently trusted hash, authenticate the issuer, or independently recompute the persisted chain.

## Pilot acceptance and reporting

Before relying on the product for a customer evidence workflow, require the S1–S3 falsifiers to pass, then test two tenants through actual HTTP routes and PostgreSQL using the intended application role. Cover hostile query/header/body/path tenant claims, missing credentials, expired/revoked keys, permission denial, pooled-session reuse, database/Redis loss, audit write failure, and restart recovery. Run fresh and upgraded-schema tests; inspecting SQL text cannot substitute for them. Verify separate retention of the downloaded artifact, hash, and all export actors.

- **Files changed:** this report, `export_verification_probe.py`, and its post-integration result in the research directory.
- **What changed:** preserved the bounded baseline findings and added the integrated historical-verifier result without broadening its assurance claim.
- **Tests run / what passed:** the original run recorded 248 passed and 9 stale-assertion failures across three explicit selections; the chain probe confirmed its gap, the updated export probe passed the repaired mode/type contract and two fail-closed controls, and 20 package-verifier tests passed positive and negative API/SDK cases.
- **Not tested:** live PostgreSQL RLS/triggers/grants, external authentication, production secret configuration, deployed logging/retention, full HTTP exploit paths, deployment, load, recovery, or all services.
- **Remaining risks:** event-content verification, exact historical membership after later arrivals, audit-attempt completeness, and unverified deployment enforcement.
- **Recommended next step:** keep the producer-to-verifier regression, add late-arrival/retained-membership and payload-mutation cases, then run the two-tenant PostgreSQL acceptance suite before making stronger claims or accepting a verified-evidence pilot.
