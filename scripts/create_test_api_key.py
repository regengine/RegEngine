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
        --scopes webhooks.ingest --expires-days 7

The raw key is never printed in full. It is written once to a file only
you can read (``--key-file``, default ``~/.regengine/test-api-key``, mode
0600) and the console shows only its key id and metadata. Only
its hash lands in the ``api_keys`` table. Remember: in development the backend validates DB-backed
keys only when ``ENABLE_DB_API_KEYS=true`` (shared.auth.get_key_store falls
back to the in-memory store otherwise).

Refuses to run when REGENGINE_ENV=production or when DATABASE_URL or
REDIS_URL points at a non-localhost host, unless --allow-production is
passed. Test keys do not belong in production. There, an authenticated
high-assurance sysadmin (WebAuthn or SSO session) creates keys through
POST /v1/admin/keys, or the "Create New API Key" card on the /admin page.
"""
from __future__ import annotations

import argparse
import asyncio
import errno
import os
import shlex
import stat
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "services")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
# Compose service names from .env.example (local dev stack only). These are
# the documented local hostnames, so the guard accepts them without forcing
# --allow-production on a standard compose run.
DEV_COMPOSE_HOSTS = {"postgres", "neo4j", "redis"}
LOCAL_HOSTS = LOOPBACK_HOSTS | DEV_COMPOSE_HOSTS


def _effective_db_hosts(database_url: str) -> list[str]:
    """Every host a Postgres driver may connect to for this URL.

    The authority host plus any libpq ``host`` / ``hostaddr`` query values,
    which SQLAlchemy passes through to psycopg/asyncpg and which override
    the authority host. A URL that looks like localhost but carries a
    remote query host is not local.
    """
    from urllib.parse import parse_qs, urlsplit

    hosts: list[str] = []
    try:
        parts = urlsplit(database_url)
    except ValueError:
        return [""]
    if parts.hostname:
        hosts.append(parts.hostname.lower())
    try:
        query = parse_qs(parts.query)
    except ValueError:
        return hosts or [""]
    for key in ("host", "hostaddr"):
        for value in query.get(key, []):
            # Multi-host values are comma-separated; each names a target.
            hosts.extend(h.strip().lower() for h in value.split(",") if h.strip())
    return hosts or [""]


def _is_local_url(database_url: str) -> bool:
    """True only when every effective host of the URL is local."""
    hosts = _effective_db_hosts(database_url)
    return bool(hosts) and all(h in LOCAL_HOSTS for h in hosts)

# Matches the AUTH_TEST_BYPASS default tenant and the legacy phase-2b seed
# tenant, so a key minted here composes with existing local fixtures.
TEST_TENANT_ID = "11111111-1111-1111-1111-111111111111"

DEFAULT_KEY_FILE = Path.home() / ".regengine" / "test-api-key"


def _write_key_file(raw_key: str, path: Path) -> None:
    """Write the raw key to ``path`` with owner-only (0600) permissions.

    Rejects a symlink as the final path component (``O_NOFOLLOW``). An
    existing parent must already be private (no group/other bits); a
    missing parent is created as ``0700``. Returns nothing so the raw key
    never taints the console summary path.
    """
    path = path.expanduser()
    parent = path.parent
    if parent.exists():
        parent_mode = stat.S_IMODE(parent.stat().st_mode)
        if parent_mode & 0o077:
            raise SystemExit(
                f"Refusing to write key file: parent {parent} is group/world "
                f"accessible (mode {oct(parent_mode)}). Use a private directory."
            )
    else:
        parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(parent, 0o700)

    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags, 0o600)
    except OSError as exc:
        # ELOOP: final component is a symlink.
        if getattr(exc, "errno", None) == errno.ELOOP:
            raise SystemExit(
                f"Refusing to write key file: {path} is a symlink"
            ) from exc
        raise
    try:
        # Tighten permissions even if the file already existed.
        os.fchmod(fd, 0o600)
        os.write(fd, (raw_key + "\n").encode("utf-8"))
    finally:
        os.close(fd)


@dataclass(frozen=True)
class _KeySummary:
    key_id: str
    tenant_id: str
    scopes: list
    billing_tier: str
    expires_at: object


def _format_summary(summary: _KeySummary, key_path: Path, billing_note: str) -> str:
    """Console summary. Never includes the raw key."""
    quoted_path = shlex.quote(str(key_path))
    return f"""
API key created. The raw key is NOT shown; it was written once to:

  {key_path}   (mode 0600, readable only by you)

  key_id:      {summary.key_id}
  tenant_id:   {summary.tenant_id}
  scopes:      {summary.scopes}
  tier:        {summary.billing_tier}
  expires_at:  {summary.expires_at or "never"}

Billing status for tenant: {billing_note}

Use it:

  export REGENGINE_TEST_API_KEY="$(cat {quoted_path})"
  curl -H "X-RegEngine-API-Key: $REGENGINE_TEST_API_KEY" http://localhost:8000/<endpoint>

Delete the file when you no longer need the key.

Reminder: with REGENGINE_ENV=development the backend only checks DB-backed
keys when ENABLE_DB_API_KEYS=true is set on the server process.
"""


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--name", default="Local Test Key")
    parser.add_argument(
        "--tenant-id",
        default=TEST_TENANT_ID,
        help=f"Tenant UUID the key is scoped to (default {TEST_TENANT_ID})",
    )
    parser.add_argument(
        "--tenant-name",
        default="Local Test Tenant",
        help="Name used if the tenant row needs to be created",
    )
    parser.add_argument(
        "--scopes",
        default="webhooks.ingest",
        help="Comma-separated scope list. Defaults to 'webhooks.ingest', the "
        "permission the webhook and CSV ingest routes require. "
        "Pass --scopes '*' explicitly only when a test needs a wildcard key.",
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
        "--key-file",
        type=Path,
        default=DEFAULT_KEY_FILE,
        help=f"Where to write the raw key (mode 0600). Default {DEFAULT_KEY_FILE}",
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
    if not _is_local_url(database_url):
        problems.append("DATABASE_URL is not a localhost URL")
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    if not _is_local_url(redis_url):
        problems.append("REDIS_URL is not a localhost URL")
    if problems and not args.allow_production:
        sys.exit(
            "Refusing to mint a test key: "
            + " and ".join(problems)
            + ". In real environments an authenticated high-assurance sysadmin "
            "creates keys via POST /v1/admin/keys or the /admin page. "
            "Pass --allow-production only if you are certain."
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
    from shared.tenant_context import set_tenant_guc
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
            await set_tenant_guc(conn, tenant_id)
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


def _seed_billing_status(tenant_id: str, allow_production: bool = False) -> str:
    """Mark the tenant's subscription 'trialing' so the subscription gate passes.

    Returns a human-readable outcome string; never raises (billing seed is
    best-effort: the key itself is still valid without it). Refuses to
    write to a non-localhost Redis without the production opt-in, so a
    shell pointed at shared Redis cannot open the paid-route gate there.
    """
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    if not _is_local_url(redis_url) and not allow_production:
        return (
            "SKIPPED (REDIS_URL is not a localhost URL; not writing billing "
            "state without --allow-production)."
        )
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
        billing_note = _seed_billing_status(args.tenant_id, args.allow_production)

    # Resolve the path before touching the raw key so the console summary
    # never receives a value tainted by the secret (CodeQL alert 81).
    key_path = args.key_file.expanduser()
    _write_key_file(key.raw_key, key_path)
    summary = _KeySummary(
        key_id=key.key_id,
        tenant_id=key.tenant_id,
        scopes=key.scopes,
        billing_tier=key.billing_tier,
        expires_at=key.expires_at,
    )
    print(_format_summary(summary, key_path, billing_note))

if __name__ == "__main__":
    asyncio.run(_main())
