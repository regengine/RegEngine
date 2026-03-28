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
# Target metadata — None for now (models are Pydantic, not SQLAlchemy ORM).
# When/if SQLAlchemy ORM models are introduced, import Base.metadata here
# to enable autogenerate support.
# ---------------------------------------------------------------------------
target_metadata = None


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Emits SQL to stdout instead of executing against a live database.
    Useful for generating migration scripts for review or manual application.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
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
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
