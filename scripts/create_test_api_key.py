#!/usr/bin/env python3
"""Mint a tenant-scoped RegEngine API key for local/dev testing.

One command produces a key that works end-to-end against a local stack:
it seeds the tenant row, creates the key through the production
``DatabaseAPIKeyStore`` path (peppered hash, RLS context, audit metadata),
and marks the tenant's subscription as ``trialing`` in Redis so the
subscription gate on paid ingest routes passes.

Prerequisites (see README "Local Development"):
    docker compose -f docker-compose.dev.yml up -d      # Postgres + Redis
    export DATABASE_URL=postgresql://regengine:${POSTGRES_PASSWORD}@localhost:5432/regengine
    bash scripts/run-migrations.sh

Usage:
    ./venv/bin/python scripts/create_test_api_key.py
    ./venv/bin/python scripts/create_test_api_key.py --name "EDI smoke key" \
        --scopes epcis.ingest,csv.ingest --expires-days 7

The raw key is printed ONCE and never stored — only its hash lands in the
``api_keys`` table. Remember: in development the backend validates DB-backed
keys only when ``ENABLE_DB_API_KEYS=true`` (shared.auth.get_key_store falls
back to the in-memory store otherwise).

Refuses to run when REGENGINE_ENV=production or when DATABASE_URL points at
a Supabase host, unless --allow-production is passed. Test keys do not
belong in production — use POST /v1/admin/keys with ADMIN_MASTER_KEY there.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "services")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Matches the AUTH_TEST_BYPASS default tenant and the legacy phase-2b seed
# tenant, so a key minted here composes with existing local fixtures.
DEFAULT_TENANT_ID = "11111111-1111-1111-1111-111111111111"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="Local Test Key")
    parser.add_argument(
        "--tenant-id",
        default=DEFAULT_TENANT_ID,
        help=f"Tenant UUID the key is scoped to (default {DEFAULT_TENANT_ID})",
    )
    parser.add_argument(
        "--tenant-name",
        default="Local Test Tenant",
        help="Name used if the tenant row needs to be created",
    )
    parser.add_argument(
        "--scopes",
        default="*",
        help="Comma-separated scope list. Defaults to '*' so the key passes "
        "require_permission() routes (permission matching is exact or "
        "namespace-wildcard — 'read,write' would 403 on e.g. 'fda.export'). "
        "Narrow it (e.g. epcis.ingest,fda.export) when testing scope enforcement.",
    )
    parser.add_argument(
        "--billing-tier",
        default="ENTERPRISE",
        choices=["DEVELOPER", "PROFESSIONAL", "ENTERPRISE"],
        help="Tier recorded on the key (default ENTERPRISE so entitlement checks don't get in the way locally)",
    )
    parser.add_argument(
        "--jurisdictions",
        default="US",
        help="Comma-separated allowed jurisdictions (default US)",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=1000,
        help="Rate limit per minute (default 1000; hourly/daily limits scale from it)",
    )
    parser.add_argument(
        "--expires-days",
        type=int,
        default=30,
        help="Key lifetime in days (default 30; 0 = never expires)",
    )
    parser.add_argument(
        "--no-seed-tenant",
        action="store_true",
        help="Skip creating the tenants row if it doesn't exist",
    )
    parser.add_argument(
        "--no-seed-billing",
        action="store_true",
        help="Skip marking the tenant's subscription 'trialing' in Redis "
        "(without it, subscription-gated routes return 402)",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Override the production guard. Almost never what you want.",
    )
    return parser.parse_args()


def _guard_against_production(args: argparse.Namespace, database_url: str) -> None:
    env = os.getenv("REGENGINE_ENV", "").strip().lower()
    problems = []
    if env == "production":
        problems.append("REGENGINE_ENV=production")
    if "supabase.co" in database_url or "supabase.com" in database_url:
        problems.append("DATABASE_URL points at a Supabase host")
    if problems and not args.allow_production:
        sys.exit(
            "Refusing to mint a test key: "
            + " and ".join(problems)
            + ". Use POST /v1/admin/keys (ADMIN_MASTER_KEY) for real environments, "
            "or pass --allow-production if you are certain."
        )


def _async_url(database_url: str) -> str:
    """Normalize a Postgres URL to the asyncpg dialect (same rules as the store)."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+asyncpg://", 1)
    return database_url


async def _seed_tenant(database_url: str, tenant_id: str, tenant_name: str) -> bool:
    """Ensure the tenants row exists. Returns True if a row was inserted."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(
        _async_url(database_url),
        connect_args={"statement_cache_size": 0, "prepared_statement_cache_size": 0},
    )
    try:
        async with engine.begin() as conn:
            # tenants has forced RLS; set the tenant GUC so the write passes
            # the policy for non-superuser roles too.
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": tenant_id},
            )
            result = await conn.execute(
                text(
                    """
                    INSERT INTO tenants (id, name, slug, status, settings, created_at)
                    VALUES (:id, :name, :slug, 'active', '{}', :now)
                    ON CONFLICT DO NOTHING
                    """
                ),
                {
                    "id": tenant_id,
                    "name": tenant_name,
                    "slug": f"local-test-{tenant_id[:8]}",
                    "now": datetime.now(timezone.utc),
                },
            )
            return bool(result.rowcount)
    finally:
        await engine.dispose()


def _seed_billing_status(tenant_id: str) -> str:
    """Mark the tenant's subscription 'trialing' so the subscription gate passes.

    Returns a human-readable outcome string; never raises (billing seed is
    best-effort — the key itself is still valid without it).
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    try:
        import redis as redis_lib

        client = redis_lib.from_url(redis_url, socket_connect_timeout=2)
        existing = client.hget(f"billing:tenant:{tenant_id}", "status")
        if existing:
            return f"already '{existing.decode() if isinstance(existing, bytes) else existing}' (left as-is)"
        client.hset(f"billing:tenant:{tenant_id}", mapping={"status": "trialing"})
        return "set to 'trialing'"
    except Exception as exc:  # noqa: BLE001 — advisory step, report and move on
        return (
            f"SKIPPED ({type(exc).__name__}: {exc}). Subscription-gated routes will "
            f"return 402/503 until you run: redis-cli HSET billing:tenant:{tenant_id} status trialing"
        )


async def _main() -> None:
    args = _parse_args()

    database_url = os.getenv("DATABASE_URL", "")
    if not database_url:
        sys.exit("DATABASE_URL must be set (see README 'Local Development').")

    _guard_against_production(args, database_url)

    try:
        uuid.UUID(args.tenant_id)
    except ValueError:
        sys.exit(f"--tenant-id must be a valid UUID, got: {args.tenant_id!r}")

    scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
    jurisdictions = [j.strip() for j in args.jurisdictions.split(",") if j.strip()]
    expires_at = datetime.now(timezone.utc) + timedelta(days=args.expires_days) if args.expires_days > 0 else None

    if not args.no_seed_tenant:
        inserted = await _seed_tenant(database_url, args.tenant_id, args.tenant_name)
        print(f"Tenant {args.tenant_id}: {'created' if inserted else 'already exists'}")

    from shared.api_key_store import DatabaseAPIKeyStore

    store = DatabaseAPIKeyStore(database_url=database_url)
    try:
        key = await store.create_key(
            name=args.name,
            description="Test key minted by scripts/create_test_api_key.py",
            tenant_id=args.tenant_id,
            billing_tier=args.billing_tier,
            allowed_jurisdictions=jurisdictions,
            scopes=scopes,
            rate_limit_per_minute=args.rpm,
            rate_limit_per_hour=args.rpm * 60,
            rate_limit_per_day=args.rpm * 60 * 24,
            expires_at=expires_at,
            created_by="scripts/create_test_api_key.py",
            metadata={"purpose": "local-testing"},
        )
    finally:
        await store.close()

    if args.no_seed_billing:
        billing_note = (
            "skipped (--no-seed-billing). Subscription-gated routes will return 402 "
            f"until you run: redis-cli HSET billing:tenant:{args.tenant_id} status trialing"
        )
    else:
        billing_note = _seed_billing_status(args.tenant_id)

    print(
        f"""
API key created — the raw key is shown ONCE and cannot be recovered:

  key_id:      {key.key_id}
  tenant_id:   {key.tenant_id}
  scopes:      {key.scopes}
  tier:        {key.billing_tier}
  expires_at:  {key.expires_at or "never"}
  raw key:     {key.raw_key}

Billing status for tenant: {billing_note}

Use it:

  export REGENGINE_TEST_API_KEY='{key.raw_key}'
  curl -H "X-RegEngine-API-Key: $REGENGINE_TEST_API_KEY" http://localhost:8000/<endpoint>

Reminder: with REGENGINE_ENV=development the backend only checks DB-backed
keys when ENABLE_DB_API_KEYS=true is set on the server process.
"""
    )


if __name__ == "__main__":
    asyncio.run(_main())
