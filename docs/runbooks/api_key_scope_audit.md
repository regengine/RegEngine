# API Key Scope Audit Runbook

Operator runbook for [`scripts/audit_api_key_scopes.py`](../../scripts/audit_api_key_scopes.py) — the
read-only auditor that classifies every active RegEngine API key by privilege risk.

## When to run

- **Quarterly access review** — sweep all HIGH and MEDIUM keys, justify or rotate.
- **After a security incident** — leaked credential, suspicious traffic, terminated employee or
  partner. Filter to `--tier HIGH` first; those are blast-radius keys.
- **After a scope-schema change** — when `services/shared/permissions.py` adds, renames, or
  removes a scope token, re-audit so newly over-broad keys surface immediately.
- **Before annual SOC 2 / FSMA evidence collection** — the JSON output is auditor-friendly.
- **Ad hoc** — onboarding a partner with new credentials, deprecating a service, or any time
  someone asks "who still has admin?"

The script is read-only. It opens a single `SELECT` against `api_keys` and never mutates state,
so it is safe to run from any operator shell with `DATABASE_URL` set.

## Running it

```bash
# Default: human-readable table sorted HIGH first
DATABASE_URL=postgresql://... python scripts/audit_api_key_scopes.py

# Machine-readable, pipe to jq / store as evidence
DATABASE_URL=postgresql://... python scripts/audit_api_key_scopes.py --json > audit.json

# Focus on the worst tier only
DATABASE_URL=postgresql://... python scripts/audit_api_key_scopes.py --tier HIGH
```

The script accepts both `psycopg` and `psycopg2-binary`, and rewrites `postgresql+asyncpg://`
URLs to plain `postgresql://` automatically — paste the same `DATABASE_URL` you use for the
backend services.

## Interpreting the tiers

The `classify()` function in the script returns one of four tiers. They mirror the matching
rules in `services/shared/permissions.py`:

| Tier      | Meaning                                                                 | Action                                                                |
|-----------|-------------------------------------------------------------------------|-----------------------------------------------------------------------|
| **HIGH**  | Scope contains `*`, `admin.*`, or `super_admin` — effectively root.     | Justify in writing or rotate to a namespace-bounded scope. No exceptions. |
| **MEDIUM**| Namespace wildcard (`partner.*`, `fda.*`, etc.).                        | Acceptable for trusted partners; review every quarter. Confirm the partner still uses every endpoint the wildcard covers. |
| **LOW**   | Explicit, leaf-level scopes only (`clients.read`, `revenue.read`).      | Target shape. No action — these are the model new keys should follow. |
| **NONE**  | Empty scopes list. Likely legacy or misconfigured.                      | Either revoke or assign explicit scopes. Do not leave in this state. |

The summary line at the top of the table output (`HIGH=N  MEDIUM=N  LOW=N  NONE=N`) is the
headline number to track quarter over quarter — HIGH count should trend toward zero.

## Rotation playbook

The full rollback playbook lives in the script's module docstring at
[`scripts/audit_api_key_scopes.py`](../../scripts/audit_api_key_scopes.py) (lines 24-36). The
short version: identify the consuming service, generate a minimum-scope set, call
`DatabaseAPIKeyStore.change_scopes(key_id, new_scopes=[...], reason='audit-driven scope
narrowing', rotate=True)` from a management shell, distribute the new `raw_key`, and watch for
401s for ~5 minutes. **The old `raw_key` is destroyed at rotation — you cannot un-rotate.**

## Sample remediation checklist

For each HIGH key surfaced by the audit, walk through:

- [ ] **Identify** — match the `key_prefix` and `name` to the consuming service or partner.
      Grep for `require_permission(...)` calls in the consumer's handlers to derive the
      minimum scope set actually used.
- [ ] **Notify** — open a ticket and notify the owning team or partner contact at least 48
      hours before rotation. Include the proposed new scope set and the planned cutover time.
- [ ] **Rotate** — execute `change_scopes(..., rotate=True)` from a management shell. Capture
      the new `raw_key` securely (1Password, vault) and the `scope_change_from_key_id` from
      `extra_data`.
- [ ] **Verify** — distribute the new `raw_key`, then watch logs and Sentry for 5-10 minutes
      for 401/403 spikes from the consumer. If anything regresses, the audit log links the
      new key back to the old via `extra_data.scope_change_from_key_id`.
- [ ] **Close** — log the change in the security/access-control runbook with old `key_id`,
      new `key_id`, scope diff, ticket link, and justification. Re-run the audit and confirm
      the HIGH count decreased.
