"""Disposable native PostgreSQL/Redis operational acceptance. Never uses inherited URLs."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
PYTHON = sys.executable


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    processes = []
    evidence = {
        "scope": "disposable local acceptance; not staging or production",
        "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "source_hashes": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                ROOT / "services/shared/rules/evaluators/relational.py",
                ROOT / "services/shared/canonical_persistence/writer.py",
                ROOT / "services/shared/idempotency.py",
                ROOT / "server/main.py",
            ]
        },
    }
    with tempfile.TemporaryDirectory(prefix="regengine-operational-", dir="/tmp") as work:
        work = Path(work)
        work.chmod(0o700)
        env = {
            "LC_ALL": "C",
            "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
            "HOME": str(work),
            "PYTHONPATH": f"{ROOT}:{ROOT}/services",
            "REGENGINE_ENV": "test",
            "ENVIRONMENT": "test",
            "PYTHONDONTWRITEBYTECODE": "1",
            "LOG_LEVEL": "WARNING",
            "AWS_EC2_METADATA_DISABLED": "true",
            "DISABLE_TASK_WORKER": "true",
            "SCHEDULER_EMBEDDED": "0",
            "API_KEY_HASH_SECRET": secrets.token_hex(32),
        }
        for key in [
            "AUTH_SECRET_KEY",
            "JWT_SIGNING_KEY",
            "AUTH_OTP_HMAC_SECRET",
            "INTERNAL_SERVICE_SECRET",
            "AUDIT_INTEGRITY_KEY",
            "TOOL_ACCESS_SECRET",
            "METRICS_KEY",
            "CSRF_SECRET",
            "WEBHOOK_HMAC_SECRET",
        ]:
            env[key] = secrets.token_hex(32)
        pgport, redisport, httpport = free_port(), free_port(), free_port()
        data = work / "pg"
        pg_started = False
        try:
            subprocess.run(
                ["initdb", "-D", str(data), "-U", "probe_owner", "-A", "trust", "--no-locale", "-E", "UTF8"],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            subprocess.run(
                [
                    "pg_ctl",
                    "-D",
                    str(data),
                    "-l",
                    str(work / "postgres.log"),
                    "-o",
                    f"-k {work} -p {pgport} -h 127.0.0.1",
                    "-w",
                    "start",
                ],
                env=env,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            pg_started = True
            processes.append(
                subprocess.Popen(
                    [
                        "redis-server",
                        "--bind",
                        "127.0.0.1",
                        "--port",
                        str(redisport),
                        "--save",
                        "",
                        "--appendonly",
                        "no",
                        "--dir",
                        str(work),
                    ],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            )
            base_url = f"postgresql+psycopg://probe_owner@127.0.0.1:{pgport}/postgres"
            env.update(DATABASE_URL=base_url, ADMIN_DATABASE_URL=base_url, REDIS_URL=f"redis://127.0.0.1:{redisport}/0")
            os.environ.clear()
            os.environ.update(env)
            sys.path[:0] = [str(ROOT), str(ROOT / "services")]
            import httpx
            import redis
            from shared.api_key_store import DatabaseAPIKeyStore
            from sqlalchemy import create_engine, text

            from server.router_policy import PRODUCTION_ENABLED_ROUTERS
            from tests.migrations.test_seeded_mid_chain_upgrade import _provision_cluster

            admin = create_engine(base_url, isolation_level="AUTOCOMMIT")
            with admin.connect() as conn:
                for role in ["regengine", "regengine_sysadmin", "regengine_migrator_local"]:
                    conn.execute(
                        text(f"CREATE ROLE {role} LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION")
                    )
                conn.execute(text("CREATE DATABASE operational_local OWNER regengine_migrator_local"))

            def url(role):
                return f"postgresql+psycopg://{role}@127.0.0.1:{pgport}/operational_local"

            owner = create_engine(url("probe_owner"))
            migrator = create_engine(url("regengine_migrator_local"))
            _provision_cluster(migrator, owner)
            migration_env = env | {
                "DATABASE_URL": url("regengine"),
                "MIGRATIONS_DATABASE_URL": url("regengine_migrator_local"),
                "REGENGINE_MIGRATIONS_ROLE": "regengine_migrator_local",
            }
            migration = subprocess.run(
                [PYTHON, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT,
                env=migration_env,
                text=True,
                capture_output=True,
            )
            (work / "migration.log").write_text(migration.stdout + migration.stderr)
            if migration.returncode:
                print((migration.stdout + migration.stderr)[-6000:], flush=True)
                raise RuntimeError("dedicated migration-owner Alembic upgrade failed")
            with owner.connect() as conn:
                evidence["migration_head"] = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
                evidence["roles"] = [
                    dict(r._mapping)
                    for r in conn.execute(
                        text(
                            "SELECT rolname,rolsuper,rolbypassrls,rolcreaterole FROM pg_roles WHERE rolname IN ('regengine','regengine_sysadmin','regengine_migrator_local')"
                        )
                    )
                ]
            client_redis = redis.Redis.from_url(env["REDIS_URL"])
            fixtures = []

            async def seed():
                store = DatabaseAPIKeyStore(database_url=url("probe_owner"))
                for i in range(2):
                    tenant = str(uuid4())
                    with owner.begin() as conn:
                        conn.execute(
                            text("INSERT INTO tenants(id,name,slug,status) VALUES(:id,:name,:slug,'active')"),
                            {"id": tenant, "name": f"Local acceptance {i}", "slug": f"local-acceptance-{tenant}"},
                        )
                    key = await store.create_key(
                        "Local acceptance", tenant_id=tenant, scopes=["*"], billing_tier="ENTERPRISE"
                    )
                    client_redis.hset(f"billing:tenant:{tenant}", mapping={"status": "trialing"})
                    fixtures.append({"tenant": tenant, "key": key.raw_key})
                await store.close()

            asyncio.run(seed())
            service_env = env | {
                "REGENGINE_ENV": "production",
                "ENVIRONMENT": "production",
                "DATABASE_URL": url("regengine"),
                "ADMIN_DATABASE_URL": url("regengine_sysadmin"),
                "ENABLE_DB_API_KEYS": "true",  # pragma: allowlist secret -- boolean feature flag, no credential
                "RULES_ENGINE_ENFORCE": "cte_only",
                "REGENGINE_REQUIRE_RLS_ENFORCEMENT": "1",
                "ALLOW_INMEMORY_SESSION_STORE": "false",
                "SUBSCRIPTION_GATE_FAIL_OPEN": "false",
                "ENABLED_ROUTERS": ",".join(sorted(PRODUCTION_ENABLED_ROUTERS)),
            }
            log = (work / "server.log").open("w")
            processes.append(
                subprocess.Popen(
                    [
                        PYTHON,
                        "-m",
                        "uvicorn",
                        "server.main:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(httpport),
                        "--no-access-log",
                    ],
                    cwd=ROOT,
                    env=service_env,
                    stdout=log,
                    stderr=log,
                )
            )
            base = f"http://127.0.0.1:{httpport}"
            for _ in range(100):
                try:
                    if httpx.get(base + "/health", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if processes[-1].poll() is not None:
                    print((work / "server.log").read_text()[-6000:], flush=True)
                    raise RuntimeError("local service failed startup")
                time.sleep(0.2)
            else:
                raise RuntimeError("local service startup timed out")
            access = work / "access.json"
            access.write_text(
                json.dumps(
                    {
                        "base_url": base,
                        "fixtures": fixtures,
                        "hmac_secret": env["WEBHOOK_HMAC_SECRET"],
                        "runtime_url": url("regengine"),
                        "owner_url": url("probe_owner"),
                        "redis_url": env["REDIS_URL"],
                    }
                )
            )
            access.chmod(0o600)
            print(f"READY_ACCESS_FILE={access}", flush=True)
            evidence["service_started"] = True
            (OUT / "evidence.json").write_text(json.dumps(evidence, indent=2))
            # Additional acceptance requests run in a separate process. Parent
            # signals completion by creating stop; this lease bounds cleanup.
            deadline = time.monotonic() + 1800
            while not (work / "stop").exists() and time.monotonic() < deadline:
                time.sleep(0.5)
        except Exception as exc:
            evidence["failure"] = str(exc)
            if (work / "postgres.log").exists():
                print((work / "postgres.log").read_text()[-3000:], flush=True)
            print(type(exc).__name__ + ": " + str(exc), flush=True)
        finally:
            for proc in reversed(processes):
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
            if pg_started:
                subprocess.run(
                    ["pg_ctl", "-D", str(data), "-m", "fast", "-w", "stop"],
                    env=env,
                    stdout=subprocess.DEVNULL,
                    check=True,
                )
            evidence["owned_processes_stopped"] = True
            (OUT / "evidence.json").write_text(json.dumps(evidence, indent=2))
    evidence["owned_storage_removed"] = True
    (OUT / "evidence.json").write_text(json.dumps(evidence, indent=2))

    if "failure" in evidence:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
