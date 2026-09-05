# GitHub issue review — 2026-09-04

Scope: all **11 open issues** in `regengine/RegEngine`, inspected with their
comments against `origin/main` at `b980a9b0`. Closed issues were not reopened.
The changes protect ingestion validation, retained evidence, exports, and the
truthfulness of the UI. Experimental features remain experimental.

## Issue disposition

“Implemented” means code and regression coverage are prepared on this branch;
it does not mean deployed or that the GitHub issue has been closed.

| Issue | Disposition | Change and evidence |
| --- | --- | --- |
| [#3048](https://github.com/regengine/RegEngine/issues/3048) | Implemented | Merkle verification recomputes canonical event content and chain linkage; missing/legacy-only evidence cannot pass the content claim. Verification-log and rejection-audit write failures surface failure, including HTTP 503 on ingestion. Health responses identify themselves as liveness; use `/readiness` for dependency checks. Tests: `test_merkle_content_integrity_3048.py`, chain/merkle/health and ingestion-enforcement suites. |
| [#3047](https://github.com/regengine/RegEngine/issues/3047) | Implemented | Holding is removed from automatic CTE mappings and its optional template is labeled storage guidance. New `first_land_based_receiver` firm type selects the existing FLR procedure. Generated plans require human review instead of certifying compliance. Tests: `tests/test_fsma_plan_builder.py`. |
| [#3046](https://github.com/regengine/RegEngine/issues/3046) | Implemented | FDA recall alerts never invent TLCs or GLNs; explicit GLNs must pass GS1 validation. Unknown facts stay absent. Confidence is labeled source-field completeness, not evidentiary trust. Batch publishing requires `REGENGINE_ENABLE_EXPERIMENTAL_RECALL_EVENTS=1`; records explicitly say they are not traceability evidence. Tests: scheduler `test_fda_transformer_integrity_3046.py`. |
| [#3045](https://github.com/regengine/RegEngine/issues/3045) | Implemented | Graph outages return 503 and empty graphs return null scores. No-drill SLA/readiness is unmeasured. Unavailable traces do not create facilities or lot counts. Tenant-scaled scenarios and historical scenario reads retain their illustrative disclaimer. Mock-audit grades are explicitly self-reported/unverified, with no verified pass; failed storage cannot acknowledge completion. Tenant checks protect drill status. Tests: graph recall/compliance, ingestion simulation/mock-audit suites. |
| [#3044](https://github.com/regengine/RegEngine/issues/3044) | Implemented | Recall API failure renders an error with retry. Document receipt no longer fabricates normalized text or facts. Alerts, heartbeat and identity require the experimental flag before mounting their hooks and are hidden from ordinary navigation. Export docs use the production FDA route. Orphan UI disposition is recorded below. Tests: frontend recall-report/evidence-integrity suites. |
| [#3043](https://github.com/regengine/RegEngine/issues/3043) | Implemented | Removed fabricated §204.2(g), corrected CTE and §1.1455 paragraph references, and removed the perishables retention exception. Source references below. |
| [#3041](https://github.com/regengine/RegEngine/issues/3041) | Coordinated contract v2 prepared | Main already contains GS1 and UOM enforcement from PR #3049. This branch requires an explicit initial-packing harvester phone, removes the unresolved entity-reference bypass, and updates CSV/synthetic fixtures. Matching Inflow changes, snapshot and commit pin must travel together; rollout order below. Tests: phone-contract negative cases plus existing rules integrity suite. |
| [#3035](https://github.com/regengine/RegEngine/issues/3035) | Implemented; data migration required | Corrected seeded citations and added v120 to update known active rule definitions with incremented versions and old/new audit values. Custom/latest and historical records are preserved. Existing evaluations are never rewritten. Tests: exact seed citation map and live PostgreSQL migration test. |
| [#2877](https://github.com/regengine/RegEngine/issues/2877) | Implemented | Only the graph CI matrix provisions Neo4j. Its test invocation uses `--run-integration` and `REGENGINE_REQUIRE_NEO4J=1`, making connection failure fail the job instead of skipping. The existing real-service tests passed against a disposable Neo4j 5.24 container. |
| [#2352](https://github.com/regengine/RegEngine/issues/2352) | Operator provisioning remains | Existing disclosures and SMTP runbook were reviewed. Supabase SMTP configuration, verified sender and delivery/reset-link evidence have not been verified live. Keep open until provisioning and verification are complete. |
| [#2351](https://github.com/regengine/RegEngine/issues/2351) | Operator provisioning remains | Existing disclosures, object-storage gate and six-variable R2 runbook were reviewed. Production buckets, credentials and retained test objects have not been verified live. Keep open until provisioning and verification are complete. |

## API and operational changes

- `INFLOW_CONTRACT_VERSION` advances from `1` to `2` in both repositories.
  Initial-packing KDEs must contain a non-empty string
  `harvester_business_phone`; a business/entity identifier is not a substitute.
  Existing synthetic examples use reserved fictional numbers. No customer phone
  numbers are inferred or backfilled.
- Experimental graph score/readiness fields can be `null`. SDK/frontend callers
  must render an unmeasured state. Graph dependency failure returns 503.
- Mock-audit `passed` is nullable and remains null for self-assessments.
  `assessment_basis=self_reported`, `verified=false`, and a disclaimer accompany
  grades/status. These are training scores, not compliance evidence.
- Missing rejection-audit storage changes the request response to 503. No event
  is accepted on that path. Retry after storage recovers; do not bypass the audit.
- `/health` is explicitly a process liveness probe. Its success does not verify
  PostgreSQL, Redis, object storage, or any other dependency. Deploy/traffic
  decisions must continue to use `/readiness`.
- v120 (`c6a120b4e901`, parent `8b866e4b4798`) is a **data migration** on the rule
  catalog/audit tables. It adds no tables, columns or permissions. It updates
  only the latest active definition when its old value matches the known seed;
  custom definitions require manual review. Downgrade only reverses untouched
  migration-owned values and records another audit/version transition.

## Evidence boundaries and decisions

Merkle verification now depends on canonical content recomputation, not a proof
created and checked against the same tree. The returned root is still computed
from the current database. `externally_anchored=false` is intentional: an attacker
able to rewrite both the event data and all stored hashes is outside the
protection supplied by this check. No external checkpoint/notarization was added.
Legacy-only rows cannot claim verified canonical content.

The FDA recall scraper is an external-alert source, not a supply-chain event
source. Its unused topic remains gated. Enabling the flag is an experimental
operator choice and is not authorization to consume its output as CTE evidence.
A consumer integration requires a separate design and tests.

`/remediation`, `/dashboard/recall-response`, `/controls`, and
`lib/mock-dashboard-data.ts` are retained as experimental/reference UI. They are
not promoted into navigation or relied on for the production ingestion-to-export
flow. Removing those modules is a separate cleanup, not a prerequisite for the
functional integrity fixes. The fixture module remains test-only.

Traceability-plan and SOP templates are drafts. An operation must verify its
actual CTEs, procedures, contacts and retention duties before adoption. Conditional
FLR SOP guidance is not implied merely by being an importer/distributor.
Operational lot-linkage, source-vessel, chronology and quantity checks are labeled
operational controls; they are not represented as statutory mandates.

## Regulatory sources

The citation map was checked against the official
[21 CFR Part 1 (GovInfo 2025 edition)](https://www.govinfo.gov/content/pkg/CFR-2025-title21-vol1/pdf/CFR-2025-title21-vol1.pdf)
and the FDA's
[CTE/KDE guidance](https://www.fda.gov/media/163132/download?attachment=),
[traceability-lot-code guidance](https://www.fda.gov/food/food-safety-modernization-act-fsma/traceability-lot-code),
and [FSMA food-traceability rule page](https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods).

| Recordkeeping activity | CFR section |
| --- | --- |
| Harvesting / cooling | §1.1325(a) / §1.1325(b) |
| Initial packing | §1.1330 |
| First land-based receiving | §1.1335 |
| Shipping / receiving | §1.1340(a) / §1.1345(a) |
| Transformation | §1.1350(a) |
| Records available within 24 hours | §1.1455(c)(1) |
| Electronic sortable spreadsheet when required | §1.1455(c)(3)(ii) |
| Two-year retention, unless otherwise specified | §1.1455(d) |

## Rollout and remaining production work

1. Merge the coordinated Inflow v2 changes and the matching RegEngine contract
   branch together. The workflow pin must resolve to the Inflow v2 commit; the
   simulator's contract snapshot must identify the exact RegEngine source commit.
   Run `.github/workflows/inflow-contract-ci.yml` before rollout.
2. Apply v120 using the normal Alembic process in staging, inspect rule versions
   and `fsma.rule_audit_log`, and exercise rejection/storage failure paths. Back up
   the rule catalog before production migration. Do not edit historical
   evaluations to make them appear evaluated under the corrected rules.
3. Deploy compatible producers, API and frontend as one coordinated release.
   Existing v1 producers need the phone KDE before the v2 API is enabled.
4. For #2351/#2352, follow
   [the existing provisioning runbook](../runbooks/OBJECT_STORAGE_AND_AUTH_SMTP_PROVISIONING.md).
   Publish/verify disclosures first. Production credentials and hosted settings
   were not changed by this review. Record bucket object evidence and auth-mail
   delivery/reset-link verification before closing those issues.
5. Close implementation issues only after merge and relevant deployment checks;
   this report is not itself evidence of a production fix.

## Validation

All database experiments used disposable local containers; no production data
was used. Python checks used the repository's Python 3.12 virtual environment.

| Check | Result |
| --- | --- |
| Shared rules, citation map, Merkle tamper tests, rejection audit, plan builder, scheduler integrity | 98 passed (97 initial cases plus the explicit entity-reference bypass regression) |
| Focused ingestion, enforcement, phone v2, mock-audit persistence, simulations, verification, health, SOP and Inflow workbench | 226 passed |
| Graph recall, real-result metrics, missing-data readiness and tenant-scoped compliance | 72 passed |
| Real Neo4j 5.24 integration (`--run-integration`, `REGENGINE_REQUIRE_NEO4J=1`) | 3 passed |
| PostgreSQL 17 v120 upgrade/repeat/downgrade/audit/history checks | 1 passed |
| Frontend recall-report and evidence-integrity regressions | 14 passed |
| TypeScript `npx tsc --noEmit` | Passed after regenerating stale Next route types from the previous checkout |
| Frontend `npm run lint` | Passed, no errors; existing warnings remain |
| All changed files through pre-commit, including secret detection | Passed |
| Repository `pytest -x --no-cov` | 10 passed, then baseline admin empty-tenant test failed |
| Ingestion suite `pytest services/ingestion/tests -x --no-cov` | 174 passed, 50 skipped, then baseline Stripe helper test failed |
| Full frontend `npm run test:run` | 857 passed, 18 failed, 2 skipped; all 18 failures reproduced on untouched `b980a9b0` |

The baseline Python failures also reproduced in an isolated checkout at
`b980a9b0`: `tests/admin/test_database.py` expects an empty tenant ID to succeed,
and `test_audit_fixes_stripe_dedup_release.py` patches a helper no longer exposed
by `app.stripe_billing.rate_limiting`. These files were not changed. The frontend
baseline failures are in auth-proxy validation, homepage copy, sitemap, and two
tools-grid label expectations. None of the failure sets is represented as green.

The PostgreSQL test exposed an existing test-harness defect: converting a
SQLAlchemy URL to `str` masks its password, breaking scratch-database creation.
`tests/migrations/scratch_db.py` now retains credentials when constructing the
derived local connection URL; it never prints them. The real migration test
verifies the fix. Its default guard requires an explicitly designated test DB.

Reproduction entry points include `tests/migrations/test_v120_rule_citations.py`,
`services/graph/tests/test_neo4j_integration_testcontainers.py`,
`services/ingestion/tests/test_harvester_phone_contract_3041.py`, and the other
issue-linked test files in the table. Use `REGENGINE_MIGRATION_TEST_DB` for a
scratch PostgreSQL server and `REGENGINE_REQUIRE_DB=1` to fail instead of skip.
Set `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` for a disposable graph only: the
integration fixture deletes its test graph. Do not point these tests at production.

Hosted CI, production migration, deployed producer compatibility, R2 objects,
and SMTP delivery/reset links remain unverified.

## Review decisions

CodeRabbit review was run after secret scanning. Valid findings about shell
continuation in the export example, unmeasured drill aggregation, same-form
source attribution, plan Markdown formatting, conditional FLR SOP guidance, and migration handling of retired rule versions
were addressed. Version allocation advances beyond retired definitions while the
audit preserves the actual previous active version.

Two suggestions were rejected after inspecting the implementation: Merkle
verification **does** call `CanonicalEventStore.verify_chain_canonical` before
returning, and that canonical verifier **already joins both stores** before
reporting an orphan. Removing its orphan verdict would hide real missing evidence.

Suggestions to relax operational TLC/source-vessel checks were not applied:
those are existing ingest-contract restrictions and are explicitly labeled
operational in this change. Changing their acceptance semantics would need a
separate coordinated producer/schema update; citation repair must not silently
weaken ingestion validation. They are not claimed to be independent FDA mandates.

The companion Inflow v2 suite passed in Linux: **771 passed, 1 skipped**. The
macOS run had **767 passed, 4 skipped, 1 failure** in the existing `/dev/full`
ENOSPC test (macOS returns EPERM for that path). The Linux run used Python 3.12,
curl and Node.js in a disposable container; no application dependencies changed.
The exact RegEngine contract snapshot source is commit
`71c0aebbc7af0826d6dd3e5a9424df13ee636290`.

Inflow contract provenance: **28 passed** with `REGENGINE_CHECKOUT` pointing at
this checkout, including the optional test skipped in the Linux full run. The
pinned Inflow commit is `368c606e54493fa39a775bf89afb119a77f4fd05`.
Companion Ruff checks passed. A pre-commit invocation was attempted there, but
that repository has no `.pre-commit-config.yaml`; no config was invented.

The candidate migration DAG check passed across 81 tracked migration files,
with one head (`c6a120b4e901`). The user's pre-existing untracked merge revision
`20260901_942f92c88738_merge_v111_runtime_role_grants_branch_.py` was preserved and
excluded from this change and from the candidate-DAG check. It would introduce
an unrelated local head if included in a checkout-wide migration invocation.
The original local `main` commit was preserved as well.

Final CodeRabbit CLI review against `b980a9b0`: **completed with zero findings**
after the fixes and a second migration regression pass. `actionlint` passed for
both changed workflows. The new live v120 regression is explicitly included in
the existing PostgreSQL RLS CI gate, so it cannot silently be omitted by the
per-service test selection.
