"""Alembic environment configuration for RegEngine.

Reads the schema-owner ``MIGRATIONS_DATABASE_URL`` in deployed environments
and supports both offline (SQL-script) and online (live DB) migration modes.
Local development and CI may fall back to ``DATABASE_URL`` for disposable
owner-run databases; a cloud/staging/production process never may.
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

# Override sqlalchemy.url from the migration-only credential.  Import the
# canonical cloud-marker inventory after ``services/`` is added to sys.path so
# Alembic cannot drift from application environment detection.
from shared.db_url import sync_postgres_url  # noqa: E402
from shared.env import CLOUD_ENV_VARS  # noqa: E402

_migration_url = os.environ.get("MIGRATIONS_DATABASE_URL", "").strip()
_environment = (
    os.environ.get("REGENGINE_ENV", "").strip().lower()
    or os.environ.get("ENVIRONMENT", "").strip().lower()
    or os.environ.get("ENV", "").strip().lower()
)
_deployed = _environment in {"production", "staging"} or any(
    os.environ.get(marker) for marker in CLOUD_ENV_VARS
)

if not _migration_url:
    if _deployed:
        raise RuntimeError(
            "MIGRATIONS_DATABASE_URL is required for deployed Alembic runs; "
            "refusing DATABASE_URL runtime-credential fallback"
        )
    _migration_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://regengine:regengine@postgres:5432/regengine",
    )

# psycopg 3 for every Postgres scheme, same driver as the app (shared.db_url).
config.set_main_option("sqlalchemy.url", sync_postgres_url(_migration_url))

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


# WS-2c: the agent-operator ORM overlay is now fully aligned with the
# v079/v080 DDL (nullability, defaults, comments, unique sets), so the
# former KNOWN_DRIFT_TABLES quarantine is gone. What remains excluded is
# a fixed set of DESC-ordered indexes: the database orders their trailing
# timestamp column DESC, which SQLAlchemy reflection surfaces as an
# expression element autogenerate can never match. Each verified
# equivalent by hand against the migrated schema. Do not grow this set.
DESC_INDEX_QUARANTINE = {
    "idx_audit_tenant_time",
    "idx_agent_artifacts_tenant_created",
    "idx_agent_artifacts_tenant_run",
    "idx_agent_reviews_tenant_status",
}


def include_object(object_, name, type_, reflected, compare_to):  # noqa: ANN001
    """One-directional drift contract (WS-2b).

    ``reflected and compare_to is None`` == a table/index/CHECK constraint
    that exists in the database but has no ORM counterpart. That is the
    normal state for the raw-SQL-managed majority of the schema, so it is
    excluded from autogenerate/check instead of being flagged as a drop
    candidate. Everything defined on an ORM Base is compared for real.

    ``check_constraint`` joined this set when alembic 1.19 began comparing
    CHECK constraints during autogenerate. The rule is unchanged, only its
    reach: 26 raw-SQL CHECKs on auth_challenges, organizations,
    webauthn_challenges, fsma.agent_artifacts, fsma.agent_artifact_reviews,
    fsma.ingestion_runs and fsma.ingestion_run_receipts started arriving as
    remove_constraint proposals purely because no ORM model claims them.

    Note this stays one-directional. A CHECK constraint declared on an ORM
    model but absent from the database is ``reflected is False``, so it is
    still compared and still fails the gate — which is what caught the three
    name mismatches fixed alongside this change.

    ``foreign_key_constraint`` joined the same set when FK comparison was
    turned on: four v079 FKs on fsma.ingestion_run_receipts (event,
    evidence, rule-eval, export) exist only in the database because their
    referenced tables are raw-SQL-managed with no ORM model — declaring
    them on AdvisoryReceiptModel raises NoReferencedTableError during
    comparison. They are baselined here, verified by hand against the v079
    DDL (all ON DELETE RESTRICT). The reverse direction stays compared: an
    FK declared on an ORM model but missing or re-optioned in the database
    fails the gate, which is what caught the 20 missing ondelete options
    fixed alongside this change.
    """
    if type_ in {"table", "index", "check_constraint", "foreign_key_constraint"} and reflected and compare_to is None:
        return False
    # Known-equivalent representations that autogenerate cannot compare
    # faithfully (verified manually against the migrated schema):
    #   - DESC_INDEX_QUARANTINE — see above.
    #   - api_keys key_id uniqueness: enforced in the database as a UNIQUE
    #     constraint (api_keys_key_id_key) while the ORM expresses it as
    #     unique=True on the column — same guarantee, different object.
    if type_ == "index" and name in DESC_INDEX_QUARANTINE:
        return False
    if type_ == "unique_constraint" and getattr(object_, "table", None) is not None and object_.table.name == "api_keys":
        return False
    # Foreign-key constraints are compared for real: a missing, extra, or
    # option-mismatched FK (ondelete, deferrability) is structural drift,
    # not representation noise. Tables with no ORM counterpart stay
    # excluded by the one-directional rule above, so raw-SQL-managed
    # tables never surface here through their own constraints.
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
