"""QA5: tenant display names must be stored verbatim, never HTML-escaped.

``_create_tenant_for_actor`` (services/admin/app/routes.py) used to run
``html.escape`` over the name before the DB write. Escaping is an
output-encoding concern: on write it permanently corrupts the stored
value (``A&W Foods`` became ``A&amp;W Foods``), double-escapes on
every render, and pollutes the derived slug with ``amp`` fragments.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("sqlalchemy")

service_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(service_dir))

from app.routes import TenantCreateRequest, _create_tenant_for_actor  # noqa: E402
from app.sqlalchemy_models import TenantModel  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TenantModel.__table__.create(engine, checkfirst=True)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _request():
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/admin/tenants",
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def _actor():
    return SimpleNamespace(
        actor_type="workload",
        actor_id="provisioner-1",
        actor_name=None,
        session_id=None,
        auth_method="api_key",
        tenant_id=None,
    )


def test_tenant_name_with_ampersand_stored_verbatim(db):
    """A name like ``A&W Foods`` must land in the DB byte-for-byte, and
    the slug must not contain ``amp`` fragments from escaping."""
    response = _create_tenant_for_actor(
        request=_request(),
        body=TenantCreateRequest(name="A&W Foods"),
        actor=_actor(),
        db=db,
    )

    assert response.name == "A&W Foods"
    row = db.query(TenantModel).filter(TenantModel.id == uuid.UUID(response.tenant_id)).one()
    assert row.name == "A&W Foods"
    assert "amp" not in row.slug
    assert row.slug.startswith("a-w-foods")


def test_tenant_name_with_quotes_and_brackets_stored_verbatim(db):
    """Quotes and angle brackets are data, not markup, at the storage
    layer. They must survive the write untouched."""
    response = _create_tenant_for_actor(
        request=_request(),
        body=TenantCreateRequest(name="Ben & Jerry's < foods >"),
        actor=_actor(),
        db=db,
    )

    row = db.query(TenantModel).filter(TenantModel.id == uuid.UUID(response.tenant_id)).one()
    assert row.name == "Ben & Jerry's < foods >"
    assert response.name == "Ben & Jerry's < foods >"
