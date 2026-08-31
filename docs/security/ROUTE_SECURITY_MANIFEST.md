# Route Security Manifest

`route-security-manifest.json` is the sanitized, deterministic release
contract for the consolidated backend route table. It contains no credentials,
environment values, tenant identifiers, or deployment secrets.

Each production-enabled HTTP operation records:

- its owner router/group and exact method/path template;
- exactly one classification: `public`, `tenant-scoped`, `global-sysadmin`, or
  `workload-only`;
- its authentication method and required permission/scope (an empty list is
  an explicit `none`);
- its storage boundary; and
- the executable dependency/security adapter run for that operation.

The disabled inventory contains every source operation from every router
omitted by the production allowlist, including service-local compatibility
operations intentionally filtered from the broad development table because
they would shadow another optional service. Each entry records its inventory
source and the concrete safe probe selected for its route template. The
release gate checks method/path collisions before making requests, builds a
middleware-free app from the actual production `APIRoute` table, and requires
one request per unique omitted path to return exactly 404.

## Commands

Verify without changing files:

```bash
python scripts/generate_route_security_manifest.py --check
```

After intentionally changing route ownership or security policy, regenerate:

```bash
python scripts/generate_route_security_manifest.py --write
```

Generation fails until every new production operation has an explicit policy
and a working adapter. Review the JSON diff as a security-sensitive API change;
do not accept regeneration by itself as proof that a new route is safe.

For deployment-bound execution, build the external plan and run the fail-closed
staging harness described in `docs/security/STAGING_RELEASE_GATE.md`. The
harness requires one successful contract for every enabled operation and the
negative cases derived from every manifest adapter; it never stores credential
values in the plan or evidence.

## Scope and Remaining Proof

This gate proves route-table ownership, classification, dependency contracts,
production allowlist parity, and omission at the FastAPI router layer. It does
not replace the migrated-Postgres RLS suite, the two-tenant staging matrix,
authorization negative tests, Redis fail-closed tests, or deployment-bound
evidence. Those remain separate blocking release gates.
