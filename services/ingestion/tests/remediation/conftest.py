"""Integration-test harness for the supplier remediation slice.

Runs against a real Postgres (DATABASE_URL_REMEDIATION_TEST or the local
scratch instance) that already has the migration chain applied. The app
connects as a NON-superuser role so FORCE RLS, the append-only trigger,
and the SECURITY DEFINER token lookup are genuinely enforced — not mocked.

Requires: a superuser DSN for seeding (tenants, grants, aliases) and the
v095 tables present. Skips cleanly if the database is unreachable.
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

service_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(service_dir))

SUPERUSER_DSN = os.environ.get(
    "REMEDIATION_TEST_SUPERUSER_DSN",
    "postgresql://regengine@localhost:55432/regengine",
)
APP_DSN = os.environ.get(
    "REMEDIATION_TEST_APP_DSN",
    "postgresql://remtest:remtest@localhost:55432/regengine",  # pragma: allowlist secret — throwaway scratch-DB role
)

DATA_DIR = Path(__file__).parent.parent / "data" / "supplier_sprint"


def _connectable(dsn: str) -> bool:
    from sqlalchemy import create_engine, text

    try:
        eng = create_engine(dsn, pool_pre_ping=True)
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        eng.dispose()
        return True
    except Exception:
        return False


_DB_AVAILABLE = _connectable(SUPERUSER_DSN)

# In CI the DB is provisioned by the workflow; an unreachable DB must FAIL
# the gate, never turn it green by skipping (#2530).
if not _DB_AVAILABLE and os.environ.get("REGENGINE_REQUIRE_DB") == "1":
    raise RuntimeError(
        f"REGENGINE_REQUIRE_DB=1 but the remediation Postgres is unreachable at {SUPERUSER_DSN!r} — refusing to skip."
    )

requires_db = pytest.mark.skipif(
    not _DB_AVAILABLE,
    reason="remediation scratch Postgres not available",
)


@pytest.fixture(scope="session")
def admin_engine():
    from sqlalchemy import create_engine

    if not _connectable(SUPERUSER_DSN):
        pytest.skip("remediation scratch Postgres not available")
    engine = create_engine(SUPERUSER_DSN)
    yield engine
    engine.dispose()


@pytest.fixture(scope="session")
def app_engine(admin_engine):
    """Non-superuser engine so RLS/triggers are actually enforced."""
    from sqlalchemy import create_engine, text

    with admin_engine.connect() as conn:
        conn = conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(
            text(
                """
                DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'remtest') THEN
                        CREATE ROLE remtest LOGIN PASSWORD 'remtest';  -- pragma: allowlist secret
                    END IF;
                END $$;
                """
            )
        )
        for stmt in (
            # Production connects as the `regengine` role, and the legacy fsma
            # policies are scoped TO regengine. Membership reproduces the
            # production identity; the new v095 tables use FORCE RLS with
            # PUBLIC policies, so they remain enforced even for this member.
            "GRANT regengine TO remtest",
            "GRANT USAGE ON SCHEMA fsma TO remtest",
            "GRANT USAGE ON SCHEMA public TO remtest",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA fsma TO remtest",
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO remtest",
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA fsma TO remtest",
            "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO remtest",
            "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA fsma TO remtest",
            "GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO remtest",
        ):
            conn.execute(text(stmt))
    engine = create_engine(APP_DSN)
    yield engine
    engine.dispose()


def _seed_tenant(admin_engine, name: str) -> str:
    from sqlalchemy import text

    tenant_id = str(uuid.uuid4())
    with admin_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO public.tenants (id, name, slug, status, settings, created_at)
                VALUES (CAST(:id AS uuid), :name, :slug, 'active', '{}'::jsonb, now())
                """
            ),
            {"id": tenant_id, "name": name, "slug": f"{name}-{tenant_id[:8]}"},
        )
    return tenant_id


@pytest.fixture()
def tenant_a(admin_engine):
    return _seed_tenant(admin_engine, "rem-buyer-a")


@pytest.fixture()
def tenant_b(admin_engine):
    return _seed_tenant(admin_engine, "rem-buyer-b")


@pytest.fixture()
def approved_alias(admin_engine, tenant_a):
    """Seed the previously-approved supplier product alias VF-ROM-23."""
    from sqlalchemy import text

    entity_id = str(uuid.uuid4())
    with admin_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO fsma.canonical_entities (entity_id, tenant_id, entity_type, canonical_name)
                VALUES (CAST(:entity_id AS uuid), CAST(:tenant_id AS uuid), 'product', 'Romaine Hearts 24ct')
                """
            ),
            {"entity_id": entity_id, "tenant_id": tenant_a},
        )
        conn.execute(
            text(
                """
                INSERT INTO fsma.entity_aliases (tenant_id, entity_id, alias_type, alias_value, source_system)
                VALUES (CAST(:tenant_id AS uuid), CAST(:entity_id AS uuid), 'internal_code', 'VF-ROM-23', 'test')
                """
            ),
            {"entity_id": entity_id, "tenant_id": tenant_a},
        )
    return entity_id


def _make_principal(tenant_id: str):
    from app.authz import IngestionPrincipal

    return IngestionPrincipal(
        key_id="rem-test-key",
        tenant_id=tenant_id,
        scopes=["remediation.read", "remediation.write", "remediation.export"],
        auth_mode="test",
    )


@pytest.fixture()
def client(app_engine, tenant_a, monkeypatch):
    """TestClient wired to the real scratch DB as the non-superuser role."""
    import app.authz as authz
    from app.authz import get_ingestion_principal
    from app.remediation import supplier_router as sup_mod
    from app.remediation.router import router as buyer_router
    from app.remediation.supplier_router import router as supplier_router
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from shared.database import get_db_session
    from sqlalchemy.orm import sessionmaker

    monkeypatch.setattr(authz, "consume_tenant_rate_limit", lambda **_kw: (True, 99))
    # Supplier endpoints share one limiter bucket per (test) client IP; stub
    # it here so unrelated tests can't trip each other's windows. The
    # rate-limit test re-installs the real function for itself.
    monkeypatch.setattr(sup_mod, "_consume_rate_limit", lambda **_kw: (True, 99))

    Session = sessionmaker(bind=app_engine)

    def _session_dep():
        db = Session()
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    test_app = FastAPI()
    test_app.include_router(buyer_router)
    test_app.include_router(supplier_router)
    test_app.dependency_overrides[get_ingestion_principal] = lambda: _make_principal(tenant_a)
    test_app.dependency_overrides[get_db_session] = _session_dep

    with TestClient(test_app) as tc:
        tc.tenant_a = tenant_a
        yield tc


def upload_fixture(client, name: str, supplier_org: str = "Valley Farms LLC"):
    csv_path = DATA_DIR / name
    with open(csv_path, "rb") as fh:
        response = client.post(
            "/api/v1/remediation/manifests",
            files={"file": (name, fh, "text/csv")},
            data={"supplier_org": supplier_org},
        )
    return response
