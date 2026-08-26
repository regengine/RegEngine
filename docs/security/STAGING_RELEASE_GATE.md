# Staging Security Release Gate

`scripts/security/staging_release_gate.py` turns the checked-in route security
manifest into an explicit staging test obligation. It does not contain tenant
IDs, API keys, session cookies, CSRF tokens, metrics keys, or webhook secrets.
Those values are supplied at execution time through named environment
variables from the staging secret store.

The gate is deliberately split into two artifacts:

1. `docs/security/route-security-manifest.json` is the generated source route
   inventory.
2. An external staging plan binds disposable fixtures and requests to the
   manifest SHA-256 and one reviewed staging deployment.

Do not check a populated staging plan into the repository. The plan is
sanitized, but it still describes internal test fixtures and deployment
topology. Store it with the release evidence in the restricted release
workspace. Never put credential values in it.

## Required coverage

The plan must contain exactly one successful contract request for every enabled
manifest operation. Each entry repeats the manifest classification and
`test_adapter`; any missing, duplicate, stale, or mismatched operation fails
before network access.

The plan must also contain exactly one scenario for every adapter present in
the manifest. Required adapter probes are derived from the adapter and the
methods it protects:

| Adapter class | Required staging negatives |
|---|---|
| Public, no auth | None beyond the anonymous success contract |
| Public, optional checkout auth | Invalid tenant key, tenant assertion mismatch, workload key |
| Tenant-scoped | Unauthenticated; cross-tenant read when the adapter has reads; cross-tenant write with before/after observation when it has mutations |
| Cookie-backed tenant mutation | The tenant negatives plus missing CSRF |
| Identity-global self-erasure | Session actor; unauthenticated, missing CSRF, and a successful identity-isolation write observed through an independent `/auth/me` session |
| Global sysadmin | Unauthenticated, low assurance, non-sysadmin, and missing CSRF when the adapter has mutations |
| Metrics workload | Unauthenticated and tenant-key credential |
| Stripe webhook | Unsigned and invalid signature |
| Tenant provisioner workload | Unauthenticated, tenant key, wrong scope, expired key, and revoked key |

Contract probes must expect an exact 2xx response. Negative probes use
small, security-specific status sets. HTTP 404, 405, and 422 can never satisfy
the gate because they do not prove that the intended route and guard executed.

A cross-tenant read must name every unique marker seeded for the protected
tenant. The response body must contain none of those values. A cross-tenant
mutation must include an authenticated protected-tenant read and one or more
RFC 6901 JSON pointers; the selected values are compared immediately before
and after the denied mutation.

Self-erasure is intentionally different: a valid session from any selected
tenant is allowed to erase its own identity, so a denied cross-tenant write
would be vacuous evidence. Its `identity-isolation-write` probe must therefore
make five requests in order: A `/auth/me`, B `/auth/me`, A self-erasure, A
`/auth/me`, and B `/auth/me`. Both preflights must return exactly 200. Their
runtime `user_id` values must be distinct, both runtime `tenant_id` values must
equal the resolved protected-tenant fixture, and both `is_sysadmin` values must
be exactly false. The mutation must receive its one configured exact 2xx
status; A's same session must then receive exactly 401 from `/auth/me`, proving
the mutation was not a successful no-op. B's `/user_id`, `/email`,
`/tenant_id`, `/role`, and `/is_sysadmin` values are encoded deterministically
and must remain byte-identical across its two observations.

The `mutator_observe` object is deliberately actor-free: it always uses the
probe's actor A, so a plan cannot substitute another credential for the
post-erasure check. The ordinary `observe` object names independent actor B.
Both operations must be the enabled canonical `admin:GET:/auth/me` route.
Actor A must also differ from the operation contract actor because the
contract request has already erased that fixture.

```json
{
  "id": "erasure-a-cannot-change-b",
  "kind": "identity-isolation-write",
  "operation": "admin:POST:/v1/account/erasure",
  "actor": "erasure_actor_a",
  "protected_tenant": "a",
  "request": {"json": {"confirm": true}},
  "expect": {"status": [200]},
  "mutator_observe": {
    "operation": "admin:GET:/auth/me",
    "request": {},
    "expect": {"status": [200]},
    "post_expect": {"status": [401]}
  },
  "observe": {
    "operation": "admin:GET:/auth/me",
    "actor": "erasure_observer_b",
    "request": {},
    "expect": {"status": [200]},
    "json_pointers": ["/user_id", "/email", "/tenant_id", "/role", "/is_sysadmin"]
  }
}
```

## Plan shape

This abbreviated fragment shows references only. It is not a complete plan and
will fail coverage validation as intended.

```json
{
  "schema_version": 1,
  "manifest_sha256": "<sha256-of-route-security-manifest.json>",
  "target": {
    "environment": "staging",
    "base_url_env": "REGENGINE_STAGING_BASE_URL",
    "expected_origin": "https://reviewed-staging-api.example.com",
    "deployment_id": "reviewed-staging-deployment-id"
  },
  "variables": {
    "TENANT_A_ID": "REGENGINE_STAGING_TENANT_A_ID",
    "TENANT_A_MARKER": "REGENGINE_STAGING_TENANT_A_MARKER",
    "TENANT_B_ID": "REGENGINE_STAGING_TENANT_B_ID",
    "TENANT_B_MARKER": "REGENGINE_STAGING_TENANT_B_MARKER"
  },
  "tenant_fixtures": {
    "a": {
      "id_variable": "TENANT_A_ID",
      "marker_variables": ["TENANT_A_MARKER"]
    },
    "b": {
      "id_variable": "TENANT_B_ID",
      "marker_variables": ["TENANT_B_MARKER"]
    }
  },
  "actors": {
    "anonymous": {"kind": "anonymous"},
    "tenant_a": {
      "kind": "tenant-api-key",
      "credential_env": "REGENGINE_STAGING_TENANT_A_KEY",
      "tenant": "a"
    },
    "tenant_b": {
      "kind": "tenant-api-key",
      "credential_env": "REGENGINE_STAGING_TENANT_B_KEY",
      "tenant": "b"
    }
  },
  "operations": [
    {
      "operation": "owner:GET:/v1/example/{tenant_id}",
      "classification": "tenant-scoped",
      "test_adapter": "tenant_api_key_postgres_rls",
      "contract": {
        "actor": "tenant_a",
        "request": {
          "path_params": {"tenant_id": "{{TENANT_A_ID}}"}
        },
        "expect": {"status": [200]}
      }
    }
  ],
  "adapter_scenarios": []
}
```

Supported actors are `anonymous`, `tenant-api-key`, `workload-api-key`,
`session`, `metrics-key`, and `stripe-signature`. Non-anonymous actors use a
`credential_env` name. Session actors also use a `csrf_env` name and declare
`assurance`, `is_sysadmin`, and their credential-bound disposable tenant.
Stripe actors reference the staging webhook secret; the runner computes the
timestamped signature over the exact request bytes without recording it.
Every actor must use a distinct credential environment name and value so a
single credential cannot be relabeled as multiple assurance or privilege
states in the plan.

Request paths come only from the manifest. A plan supplies values for every
path parameter, plus optional query values, non-credential headers, JSON, or a
synthetic body fixture below the plan directory. `Authorization`, cookies,
RegEngine keys, metrics keys, Stripe signatures, CSRF values, proxy-attestation
headers, and `Host` cannot be placed in request headers; the selected actor
injects them at runtime.

## Commands

First verify the source manifest, then calculate its digest for the external
plan:

```bash
python3 scripts/generate_route_security_manifest.py --check
shasum -a 256 docs/security/route-security-manifest.json
```

Validate the completed plan offline. This reads no credential values and makes
no network requests:

```bash
python3 scripts/security/staging_release_gate.py \
  --plan /restricted/release/staging-plan.json \
  --validate-only
```

After loading the named variables from the staging secret store, execute only
against the exact reviewed deployment. Both confirmation and evidence output
are mandatory:

```bash
bash scripts/security/tenant_isolation_test.sh --staging \
  --plan /restricted/release/staging-plan.json \
  --confirm-staging-deployment reviewed-staging-deployment-id \
  --evidence-out artifacts/tenant-isolation/staging-release-gate.json
```

The runner accepts only a credential-free HTTPS origin, rejects localhost,
internal hostnames, and IP literals, disables redirects, limits response bodies
and request bodies to 16 MiB, renders every request before the first network call, and runs
sequentially. Missing environment variables, fixtures, operation contracts,
adapter probes, or assertions are failures, never skips.

Adapter probes are paced 13 seconds apart by default so the
shared five-failures-per-60-seconds throttle cannot mask a route guard with an
HTTP 429. Release execution rejects a configured interval below 13 seconds,
and 429 is not an accepted auth result. Rate-limit threshold behavior itself is
a separate staging check.

Evidence contains environment-variable names, manifest and plan hashes,
deployment metadata, operation templates, adapter/probe IDs, exact statuses,
durations, and the pass/fail result. It never records concrete tenant IDs,
markers, request or response bodies, cookies, keys, signatures, or CSRF values.
For a successful identity-isolation probe, the sanitized result also records
the four `/auth/me` statuses (`200`, `200`, `401`, `200`) without recording
either identity. Its five network calls are included in `coverage.request_count`.

## Proof boundary

This runner proves that every enabled operation has a successful staging
contract and that every shared manifest adapter has the required dynamic
negative cases. The manifest generator separately proves that each operation
is bound to that adapter in source.

It does not provision fixtures or generally introspect whether supplied
credentials were created with their declared attributes. The identity-isolation
probe is the narrow exception: canonical `/auth/me` responses verify A and B's
live identity, tenant, and non-sysadmin posture. The runner still does not
verify database roles through SQL, test revocation across replicas, measure
enumeration timing, exercise the SSRF canary, or verify disabled routes on the
deployed build. Those remain separate blocking release checks. The deployment
ID is operator-confirmed and bound into the plan/evidence; an authenticated
deployment-identity endpoint would be required for cryptographic runtime
attestation.
