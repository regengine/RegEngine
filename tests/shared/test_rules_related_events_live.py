"""Real PostgreSQL regression for psycopg3 nullable exclusion parameter typing."""

from uuid import uuid4

import pytest
from shared.rules.evaluators.relational import fetch_related_events
from shared.tenant_context import set_tenant_guc
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from tests.migrations.rls_db import guarded_live_database_url

DATABASE_URL = guarded_live_database_url()
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="requires explicitly designated disposable PostgreSQL")


@pytest.mark.parametrize("exclude_event_id", [None, str(uuid4())])
def test_related_event_query_types_nullable_uuid_on_postgres(exclude_event_id):
    # An unused tenant/lot requires no inserts and still exercises PostgreSQL's
    # parameter parsing. psycopg3 rejects the untyped `:exclude_id IS NULL`
    # before executing the query, including when a non-null UUID is supplied.
    engine = create_engine(make_url(DATABASE_URL).set(drivername="postgresql+psycopg"))
    try:
        with Session(engine) as session:
            tenant = str(uuid4())
            set_tenant_guc(session, tenant)
            assert fetch_related_events(session, "synthetic-unwritten-lot", tenant, exclude_event_id) == []
    finally:
        engine.dispose()
