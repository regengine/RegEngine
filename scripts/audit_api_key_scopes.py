#!/usr/bin/env python3
"""Audit RegEngine API keys for over-broad scopes.

Read-only — does NOT mutate any keys. Connects to ``DATABASE_URL`` and
classifies every enabled key by privilege risk so the operator can
decide which keys to rotate or narrow.

Risk tiers:
  HIGH    — scope contains ``*`` or ``admin.*`` (full or admin-tier
            access). Every HIGH key should be justified or rotated to a
            namespace-bounded scope.
  MEDIUM  — namespace wildcard like ``partner.*`` or ``fda.*``. Fine for
            trusted partners but worth reviewing periodically.
  LOW     — explicit, leaf-level scopes only (e.g. ``clients.read``,
            ``revenue.read``). These are the target shape for new keys.
  NONE    — empty scopes list. Likely a legacy or misconfigured key —
            either revoke or assign explicit scopes.

Usage:
  DATABASE_URL=postgresql://... python scripts/audit_api_key_scopes.py
  DATABASE_URL=postgresql://... python scripts/audit_api_key_scopes.py --json
  DATABASE_URL=postgresql://... python scripts/audit_api_key_scopes.py --tier HIGH

Rollback playbook (when rotating a HIGH key):
  1. Identify the consuming service from the key's name/description.
  2. Generate a replacement scope set that's the minimum the service
     actually uses (grep its handlers for require_permission(...) calls).
  3. Call ``DatabaseAPIKeyStore.change_scopes(key_id, new_scopes=[...],
     reason='audit-driven scope narrowing', rotate=True)`` from a
     management shell. This issues a NEW raw_key and revokes the old.
  4. Distribute the new raw_key to the consuming service. Watch for
     401s for ~5 minutes; if anything regresses, you have the
     ``scope_change_from_key_id`` field in the new key's extra_data to
     trace back, but the old raw_key is gone — you cannot un-rotate.
  5. Log the change in your security/access-control runbook with the
     old key_id, new key_id, scope diff, and ticket/justification.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Iterable

# Tier detection. These must mirror the matching rules in
# ``services/shared/permissions.py``: ``*`` and ``admin.*`` are root, and
# anything ending in ``.*`` is a namespace wildcard.
_HIGH_RISK_TOKENS = {"*", "admin.*", "super_admin"}


def classify(scopes: Iterable[str]) -> str:
    scope_list = [s for s in (scopes or []) if s]
    if not scope_list:
        return "NONE"
    normalized = [s.strip().lower().replace(":", ".") for s in scope_list]
    if any(s in _HIGH_RISK_TOKENS for s in normalized):
        return "HIGH"
    if any(s.endswith(".*") for s in normalized):
        return "MEDIUM"
    return "LOW"


def fetch_keys(database_url: str) -> list[dict]:
    """Read every enabled, non-expired key from PostgreSQL.

    We use psycopg (sync) directly here rather than the async store
    because this is a one-shot operator script and adding async event
    loop boilerplate buys nothing.
    """
    try:
        import psycopg  # type: ignore
    except ImportError:
        try:
            import psycopg2 as psycopg  # type: ignore
        except ImportError:
            sys.exit(
                "ERROR: install psycopg or psycopg2-binary to run this script."
            )

    # asyncpg-style URL won't work with psycopg — strip the +asyncpg.
    sync_url = database_url
    for pattern in ("postgresql+asyncpg://", "postgres+asyncpg://"):
        if sync_url.startswith(pattern):
            sync_url = "postgresql://" + sync_url[len(pattern):]

    rows: list[dict] = []
    with psycopg.connect(sync_url) as conn:  # type: ignore[arg-type]
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    key_id,
                    key_prefix,
                    name,
                    tenant_id,
                    billing_tier,
                    scopes,
                    enabled,
                    created_at,
                    last_used_at,
                    expires_at,
                    revoked_at
                FROM api_keys
                WHERE enabled = TRUE
                  AND revoked_at IS NULL
                  AND (expires_at IS NULL OR expires_at > NOW())
                ORDER BY created_at DESC
                """
            )
            cols = [c[0] for c in cur.description]  # type: ignore[union-attr]
            for r in cur.fetchall():
                rows.append(dict(zip(cols, r)))
    return rows


def render_table(records: list[dict]) -> str:
    """Plain-text table — no extra deps."""
    if not records:
        return "(no keys to report)"

    headers = [
        "tier",
        "key_prefix",
        "name",
        "tenant_id",
        "scopes",
        "last_used_at",
    ]
    rows = []
    for r in records:
        tenant = r.get("tenant_id") or "—"
        last = r.get("last_used_at") or "never"
        rows.append(
            [
                r["tier"],
                r["key_prefix"] or "?",
                (r.get("name") or "")[:30],
                str(tenant)[:36],
                ", ".join(r.get("scopes") or []) or "(empty)",
                str(last)[:19],
            ]
        )

    widths = [
        max(len(str(r[i])) for r in [headers] + rows) for i in range(len(headers))
    ]
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    out = [fmt.format(*headers), fmt.format(*("-" * w for w in widths))]
    out.extend(fmt.format(*r) for r in rows)
    return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tier",
        choices=["HIGH", "MEDIUM", "LOW", "NONE", "ALL"],
        default="ALL",
        help="Filter to one risk tier.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a table — suitable for piping.",
    )
    args = parser.parse_args()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL is not set.", file=sys.stderr)
        return 2

    keys = fetch_keys(database_url)
    enriched = []
    for k in keys:
        tier = classify(k.get("scopes") or [])
        if args.tier != "ALL" and tier != args.tier:
            continue
        enriched.append({**k, "tier": tier})

    # Stable sort: HIGH first so the operator can act on the worst cases.
    tier_order = {"HIGH": 0, "MEDIUM": 1, "NONE": 2, "LOW": 3}
    enriched.sort(key=lambda r: (tier_order.get(r["tier"], 9), str(r.get("created_at"))))

    if args.json:
        print(
            json.dumps(
                enriched,
                default=str,
                indent=2,
            )
        )
    else:
        # Summary first so the headline number is obvious.
        counts: dict[str, int] = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0}
        for r in enriched:
            counts[r["tier"]] = counts.get(r["tier"], 0) + 1
        print(
            f"Audited {len(enriched)} keys — "
            f"HIGH={counts['HIGH']}  MEDIUM={counts['MEDIUM']}  "
            f"LOW={counts['LOW']}  NONE={counts['NONE']}"
        )
        print()
        print(render_table(enriched))
        if counts["HIGH"]:
            print()
            print(
                "ACTION: Each HIGH-tier key grants effectively unrestricted "
                "access. Rotate via change_scopes(rotate=True) — see the "
                "rollback playbook in this script's docstring."
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
