"""Diagnose the local admin database with a throwaway test insert.

Defaults to the localhost dev database. Refuses hosted or non-localhost
targets (or REGENGINE_ENV=production) unless --allow-production is passed.
"""

import argparse
import os
import sys
import uuid

from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import sessionmaker

# The consolidated monolith keeps admin tables in the main 'regengine' DB
# (the legacy regengine_admin DB on 5433 is dead — see .env.example).
ADMIN_DATABASE_URL = os.environ.get("ADMIN_DATABASE_URL", "postgresql://regengine:regengine@localhost:5432/regengine")

PRODUCTION_DB_HINTS = (
    "supabase.co",
    "supabase.com",
    "neon.tech",
    "railway.app",
    "amazonaws.com",
    "ondigitalocean.com",
    "render.com",
)


def _database_host(database_url: str) -> str:
    try:
        return (make_url(database_url).host or "").lower()
    except Exception:  # noqa: BLE001 - unparseable URL, treat as non-local
        return ""


def ensure_local_database(database_url: str, allow_production: bool) -> None:
    """Refuse hosted or non-localhost databases without explicit opt-in."""
    lowered = database_url.lower()
    host = _database_host(database_url)
    env = os.getenv("REGENGINE_ENV", "").strip().lower()
    is_local = host in {"localhost", "127.0.0.1", "::1"}
    looks_hosted = any(hint in lowered for hint in PRODUCTION_DB_HINTS)
    if (not is_local or looks_hosted or env == "production") and not allow_production:
        raise SystemExit(
            "Refusing to run diagnostics against a non-localhost database. "
            "Use a localhost ADMIN_DATABASE_URL or pass --allow-production "
            "only if you are certain."
        )


def _engine_for(database_url: str):
    # psycopg (v3); psycopg2 is not installed.
    return create_engine(
        make_url(database_url).set(drivername="postgresql+psycopg")
        if database_url.startswith("postgres")
        else database_url
    )


def test_insert(database_url: str = ADMIN_DATABASE_URL):
    Session = sessionmaker(bind=_engine_for(database_url))
    db = Session()
    # SECURITY: set_admin_context(true) sets the session variable, but RLS bypass
    # only works if connected as the 'regengine_sysadmin' role. With the standard
    # 'regengine' role, this call is a no-op for bypass purposes.
    # For full sysadmin access, use ADMIN_DATABASE_URL with regengine_sysadmin credentials.
    db.execute(text("SELECT set_admin_context(true)"))
    user_id = str(uuid.uuid4())
    email = f"test-{user_id[:8]}@example.com"
    print(f"Inserting user {user_id} with email {email}")

    # Use raw SQL to avoid model dependency issues for this diagnostic
    db.execute(
        text(
            "INSERT INTO users (id, email, password_hash, status, is_sysadmin) VALUES (:id, :email, :pw, :status, :is_sysadmin)"
        ),
        {"id": user_id, "email": email, "pw": "hash", "status": "active", "is_sysadmin": True},
    )
    db.commit()
    db.close()
    print("Done")


def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a throwaway insert against the local admin database.")
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow a non-localhost ADMIN_DATABASE_URL. Almost never what you want.",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = _parse_args(argv)
    ensure_local_database(ADMIN_DATABASE_URL, args.allow_production)
    test_insert()


if __name__ == "__main__":
    main()
