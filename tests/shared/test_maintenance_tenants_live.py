"""Bounded discovery and evidence-preserving retention on the migrated schema."""

import os
from unittest.mock import patch
from uuid import uuid4

import pytest
from shared.db_url import sync_postgres_url
from shared.maintenance_tenants import list_maintenance_tenant_ids
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from tests.migrations.rls_db import guarded_live_database_url


@pytest.fixture
def database_roles():
    provider_url = guarded_live_database_url()
    if not provider_url:
        pytest.skip("no designated migrated scratch database")
    admin_url = os.getenv("ADMIN_DATABASE_URL", "")
    if not admin_url:
        pytest.fail("a direct admin test credential is required")
    provider, admin = make_url(provider_url), make_url(admin_url)
    assert (provider.host, provider.port, provider.database) == (admin.host, admin.port, admin.database)
    engine = create_engine(sync_postgres_url(provider_url))
    try:
        yield engine, provider_url, admin_url
    finally:
        engine.dispose()


def test_discovery_limit_is_applied_by_postgres(database_roles):
    engine, _, admin_url = database_roles
    tenants = [str(uuid4()), str(uuid4())]
    try:
        with engine.begin() as conn:
            for tenant in tenants:
                conn.execute(
                    text("INSERT INTO public.tenants(id,name,slug) VALUES (:id,'bounded discovery',:slug)"),
                    {"id": tenant, "slug": tenant},
                )
        values = list_maintenance_tenant_ids(admin_url, limit=1)
        assert len(values) == 1
        assert values == list_maintenance_tenant_ids(admin_url)[:1]
    finally:
        with engine.begin() as conn:
            for tenant in tenants:
                conn.execute(text("DELETE FROM public.tenants WHERE id=:id"), {"id": tenant})


def test_discovery_refuses_provider_identity_and_invalid_limit(database_roles):
    _, provider_url, _ = database_roles
    with pytest.raises(RuntimeError, match="exact.*regengine_sysadmin"):
        list_maintenance_tenant_ids(provider_url, limit=1)
    with pytest.raises(ValueError, match="positive integer"):
        list_maintenance_tenant_ids(provider_url, limit=0)


def test_task_purge_retains_recall_and_unknown_evidence(database_roles):
    from services.scheduler.service import SchedulerService

    engine, _, admin_url = database_roles
    tenant = str(uuid4())
    kinds = ("recall_drill", "recall", "future_evidence_kind", "review_item")
    try:
        with engine.begin() as conn:
            conn.execute(
                text("INSERT INTO public.tenants(id,name,slug) VALUES (:id,'retention test',:id)"), {"id": tenant}
            )
            for kind in kinds:
                conn.execute(
                    text(
                        "INSERT INTO fsma.task_queue(tenant_id,task_type,payload,status,created_at,completed_at) VALUES (:tid,:kind,'{}'::jsonb,'completed',now()-interval '400 days',now()-interval '400 days')"
                    ),
                    {"tid": tenant, "kind": kind},
                )
        admin = create_engine(sync_postgres_url(admin_url))
        try:
            with patch("services.admin.app.database.SessionLocal", sessionmaker(bind=admin)):
                SchedulerService.purge_old_tasks(SchedulerService.__new__(SchedulerService))
        finally:
            admin.dispose()
        with engine.connect() as conn:
            remaining = set(
                conn.execute(
                    text("SELECT task_type FROM fsma.task_queue WHERE tenant_id=:tid"), {"tid": tenant}
                ).scalars()
            )
        assert remaining == set(kinds) - {"review_item"}
    finally:
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM fsma.task_queue WHERE tenant_id=:tid"), {"tid": tenant})
            conn.execute(text("DELETE FROM public.tenants WHERE id=:tid"), {"tid": tenant})
