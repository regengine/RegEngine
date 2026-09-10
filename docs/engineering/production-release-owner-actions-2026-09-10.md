# Production release owner actions — 2026-09-10

Status: **HELD**. This is a sanitized read-only evidence inventory and owner handoff, not approval to rotate credentials, migrate a hosted database, restore over data, or deploy. Roles below identify the required responsibility; no person is assigned by this document.

## Historical secret findings: assign disposition before suppression

Source: [main security run 34307820114](https://github.com/regengine/RegEngine/actions/runs/34307820114), Gitleaks job `102328070693`, source SHA `22fc9a6b07186f5bae544f9ce7fb383495a57295`. Its redacted log reports 2730 commits scanned and 322 findings. Metadata-only extraction gives:

| Rule | Findings |
| --- | ---: |
| curl-auth-header | 168 |
| generic-api-key | 130 |
| jwt | 12 |
| stripe-access-token | 10 |
| private-key | 2 |

Findings span 51 commit IDs. Counts are scanner occurrences, not unique working credentials. No finding values were extracted into this document.

[Issue #3080](https://github.com/regengine/RegEngine/issues/3080) remains open, has no assignee and no comments at this readback. Its older masked inspection suggests placeholders/fixtures but explicitly does not certify them. Its 317-fingerprint snapshot differs from the current run; do not use that number as the current inventory.

Security/credential owner actions:

1. Prioritize the three `generic-api-key` fingerprints in historical `.env.production` at commit `a130816b2c95f51e253b311dd73a9597eb2f88c4`, lines **15, 18, 37**, dated `2026-02-07T07:49:39Z`. A production filename is a triage priority, not proof the values were live. Record the provider, credential identifier, affected environments, and owner without reproducing the value.
2. Classify every exact fingerprint as a demonstrated synthetic fixture, a real credential requiring revocation, or unresolved. For fixture dispositions, record why the historical source is nonfunctional and who reviewed it. Test/docs paths alone do not establish this.
3. The two `private-key` occurrences identify `tests/shared/test_digital_signatures.py:175` in commits `a130816b2c95f51e253b311dd73a9597eb2f88c4` and `a6d476464bfe7afaf3ff830b65dc312a2be6d426`. The ten Stripe occurrences identify redaction-oriented test paths in those same commits: `test_exception_sanitization.py:153`, `test_secure_error_handling.py:471`, and `test_verbose_logging_control.py:216,219,546`, all under `tests/shared/`. Review each exact historical occurrence before accepting a synthetic disposition.
4. For any real credential, attach provider revocation event/identifier, operator and timestamp, replacement cutover deployment IDs, and old-credential denial evidence. Never attach raw credentials. History removal, scanner suppression, replacement creation, and code changes do not prove revocation.
5. Keep unresolved findings blocking; review any eventual narrowly scoped scanner disposition separately.

[Issue #2938](https://github.com/regengine/RegEngine/issues/2938) closed on `2026-09-02T20:03:05Z`. Its closing comment says PR #2995 stopped plaintext credential-file writes. It does **not** report provider rotation or revocation completion.

## Database migration identity: current provider readback

Read-only Supabase connector queries on project `magbeerafyxmyuqmbfgv` (`RegEngine`, PostgreSQL 17) returned:

| Role queried | Present | Superuser | BYPASSRLS | CREATEDB | CREATEROLE | LOGIN |
| --- | --- | --- | --- | --- | --- | --- |
| regengine | yes | false | false | false | false | true |
| regengine_sysadmin | yes | false | false | false | false | true |
| regengine_migrator | no result | — | — | — | — | — |
| regengine_migrator_ci | no result | — | — | — | — | — |

Query used only `pg_roles` flags for these four names. Absence of those two names does not exclude a differently named migration role. This proves the two runtime roles exist with restricted flags; it does **not** prove Railway connects as either role, that their grants are correct, or that every relevant table has enforced tenant policies.

A separate `SELECT version_num FROM public.alembic_version` returned **267d8053ced5**. Local `python3 scripts/check_alembic_revisions.py` reports **81 revisions, one head c6a120b4e901**, so this provider database is behind the source head. These queries do not establish which Railway environment currently points at this database.

Database/release owner actions:

1. Bind the intended staging target and production target explicitly; record each provider/database identifier and connection role name without URLs containing credentials.
2. Supply a dedicated migration identity with the intended ownership/grants and `NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`. Verify the identity through its actual connection; verify runtime/admin identity separately. Do not substitute the provider or runtime URL for deployed migration credentials.
3. Obtain the backup/restore acceptance below, then execute the supported migration runner under separately authorized release work and record convergence to the exact candidate head. `scripts/run-migrations.sh:48` deliberately refuses deployed migrations when `MIGRATIONS_DATABASE_URL` is missing.
4. Capture SQL evidence for role identity, flags, ownership, grants, tenant RLS policies, and migration revision from the exact target; local CI role tests cannot substitute for this.

## Latest failed deployments

Railway readback for project `4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51`, service `b5ba1aad-b19d-45a4-80e2-48f2b05f7730`, returned the following latest records. Both were created `2026-09-09T03:37:08.317Z` for source SHA `22fc9a6b07186f5bae544f9ce7fb383495a57295`.

| Environment | Deployment | Status | Evidence |
| --- | --- | --- | --- |
| production | 172152d1-6787-4ce9-9504-8470a0253134 | FAILED | Bounded runtime/build log reads returned no diagnostic lines; root cause not established. |
| staging | af902cd7-98ba-44b8-aa0c-576effc80047 | FAILED | Runtime repeats `MIGRATIONS_DATABASE_URL is required for deployed migrations`; build log reports healthcheck failure after retries. |

These are attempted-deployment records, not proof of the currently serving build. A new deployment requires provider readback plus exact serving SHA and authenticated production-spine acceptance.

## Backup and restore acceptance

No completed restore or approved backup-use record was located in the checked-in release evidence and runbooks inspected for this handoff. Current provider backup availability was **not refreshed** in this pass. [Issue #2937](https://github.com/regengine/RegEngine/issues/2937) closed `2026-08-27T19:19:21Z` with no comments; its format correction is source evidence, not a production restore record.

Database/data owner must provide:

- An approved backup identifier, capture timestamp, exact source database, retention/location, and approval record.
- A separate disposable restore target and completed restore record; never overwrite the source to test recovery.
- Validation of expected schema/revision, evidence counts/checksums and a representative independently verified export; capture measured recovery timing and any missing data.
- Release decision linking that restore result to the candidate and migration window.

`docs/runbooks/disaster-recovery.md:62` documents plain SQL gzip compatibility for the repository backup script. A provider-managed physical backup has different restore semantics; the existence of either format is not successful recovery evidence.

## Final release acceptance

After the external prerequisites are complete, bind the immutable serving candidate and execute restricted-role, authenticated two-tenant ingestion, cached same-key replay, fresh-key durable deduplication, negative tenant isolation, and export with independently verified chain integrity. Preserve the staging runner's proof boundary in `docs/security/STAGING_RELEASE_GATE.md:228`: it does not prove database role flags, cross-replica revocation, or cryptographic deployment identity. Collect these separately.

## Private simulator CI access

PR #3085's initial simulator job failed before test execution while checking out `regengine/inflow-lab`: repository not found under the default repository-scoped GITHUB_TOKEN. Read-only checks confirmed the repository is private and pinned commit `78050ae78c72a348a518b6d48bdeae7424d772da` exists. The pin was preserved.

Repository owner action: supply RegEngine Actions secret `INFLOW_LAB_READ_TOKEN` using a fine-grained token whose repository access is only `regengine/inflow-lab` with Contents read-only (implicit Metadata read). An equivalently restricted GitHub App token is also suitable if generated by the workflow. Do not copy a developer's broad CLI token. The workflow now fails explicitly when missing and does not persist checkout credentials. No token was provisioned by this task. Rerun the simulator contract job after configuration; neither a passing preflight nor a checkout proves the live contract tests pass.
