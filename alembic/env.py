"""Alembic environment configuration for RegEngine.

Reads DATABASE_URL from the environment (falling back to the local dev default)
and supports both offline (SQL-script) and online (live DB) migration modes.
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Path setup — make `services/` importable so shared modules work if needed.
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services"))

# ---------------------------------------------------------------------------
# Alembic Config object (provides access to alembic.ini values)
# ---------------------------------------------------------------------------
config = context.config

# Override sqlalchemy.url from environment variable
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://regengine:regengine@postgres:5432/regengine",
)
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Python logging from the config file
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Target metadata — imports EVERY SQLAlchemy ORM Base in the tree so
# `alembic revision --autogenerate` / `alembic check` can detect
# model↔schema drift across all of them (WS-2b). Before this, only the
# admin Base was registered, so ORM models elsewhere silently escaped
# tracking (e.g. scheduler_seen_items existed only via a runtime
# create_all with no migration).
#
# NOTE: most RegEngine tables (fsma.*, canonical/CTE persistence, RLS
# infrastructure) are raw-SQL-managed — they have NO ORM model by design.
# The include_object hook below makes drift detection one-directional:
# every ORM model must match the migrated schema, but database tables
# without an ORM counterpart are ignored rather than proposed for DROP.
# ---------------------------------------------------------------------------
from services.admin.app.sqlalchemy_models import Base as AdminBase  # noqa: E402
from services.scheduler.app.state import Base as SchedulerStateBase  # noqa: E402
from services.shared.agent_operator_models import Base as AgentOperatorBase  # noqa: E402
from services.shared.api_key_store import Base as ApiKeyStoreBase  # noqa: E402

target_metadata = [
    AdminBase.metadata,
    AgentOperatorBase.metadata,
    ApiKeyStoreBase.metadata,
    SchedulerStateBase.metadata,
]


# Tables whose ORM declaration is KNOWN to lag the raw-SQL schema that
# v079/v080 created (comments, DESC index expressions, nullability, and
# composite-unique sets all differ). They stay registered in
# target_metadata so autogenerate can scaffold future changes, but they
# are quarantined from the drift GATE until the agent-operator ORM is
# aligned (tracked as part of WS-2c). Shrink this set — never grow it.
KNOWN_DRIFT_TABLES = {
    "ingestion_runs",
    "ingestion_run_receipts",
    "agent_artifacts",
    "agent_artifact_reviews",
}


def include_object(object_, name, type_, reflected, compare_to):  # noqa: ANN001
    """One-directional drift contract (WS-2b).

    ``reflected and compare_to is None`` == a table/index that exists in
    the database but has no ORM counterpart. That is the normal state for
    the raw-SQL-managed majority of the schema, so it is excluded from
    autogenerate/check instead of being flagged as a drop candidate.
    Everything defined on an ORM Base is compared for real.
    """
    if type_ in {"table", "index"} and reflected and compare_to is None:
        return False
    if type_ == "table" and name in KNOWN_DRIFT_TABLES:
        return False
    if type_ == "index" and getattr(object_, "table", None) is not None and object_.table.name in KNOWN_DRIFT_TABLES:
        return False
    # Known-equivalent representations that autogenerate cannot compare
    # faithfully (verified manually against the migrated schema, WS-2b):
    #   - idx_audit_tenant_time: the database index orders timestamp DESC
    #     (an expression element autogenerate always sees as different).
    #   - api_keys key_id uniqueness: enforced in the database as a UNIQUE
    #     constraint (api_keys_key_id_key) while the ORM expresses it as
    #     unique=True on the column — same guarantee, different object.
    if type_ == "index" and name == "idx_audit_tenant_time":
        return False
    if type_ == "unique_constraint" and getattr(object_, "table", None) is not None and object_.table.name == "api_keys":
        return False
    # FK *option* churn (ondelete/match representation) produces noisy
    # remove/add pairs on tables that are structurally in sync. Constraint
    # alignment is tracked by the WS-2c type/constraint audit, not this
    # structural gate.
    if type_ == "foreign_key_constraint":
        return False
    return True


def _guard_baseline_downgrade() -> None:
    """Block destructive full-chain downgrades before any revision runs."""
    args = sys.argv[1:]
    if "downgrade" not in args:
        return

    downgrade_index = args.index("downgrade")
    destinations = [arg for arg in args[downgrade_index + 1 :] if not arg.startswith("-")]
    if not any(dest == "base" or dest.endswith(":base") for dest in destinations):
        return

    env = os.environ.get("REGENGINE_ENV", "unset").lower()
    ack = os.environ.get("REGENGINE_ALLOW_BASELINE_DOWNGRADE", "0")
    if env in {"development", "dev", "test", "ci"} and ack == "1":
        return

    raise RuntimeError(
        "Baseline downgrade blocked (#1264). This migration path drops every "
        "baseline FSMA table and must not run unless BOTH "
        "REGENGINE_ENV=development and REGENGINE_ALLOW_BASELINE_DOWNGRADE=1 "
        f"are set. Current: REGENGINE_ENV={env!r}, "
        f"REGENGINE_ALLOW_BASELINE_DOWNGRADE={ack!r}"
    )


_guard_baseline_downgrade()


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Emits SQL to stdout instead of executing against a live database.
    Useful for generating migration scripts for review or manual application.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        include_object=include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    Creates an engine, connects, and runs migrations against the live database.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            # ORM models live in both public and fsma schemas — reflect all
            # schemas so fsma-based models (agent_operator_models) are found
            # instead of being reported as missing tables.
            include_schemas=True,
            # Structural gate only (WS-2b): tables/columns/indexes. Type
            # representation differences (TEXT vs VARCHAR, ARRAY flavors)
            # are enforced at boot by verify_orm_db_type_alignment and by
            # the WS-2c audit — comparing them here double-reports with
            # different heuristics.
            compare_type=False,
            compare_server_default=False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
