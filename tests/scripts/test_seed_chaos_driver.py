"""The scheduler seed must not require the removed psycopg2 driver."""

import importlib.util
from pathlib import Path

import pytest
from apscheduler.jobstores import sqlalchemy as jobstore_module
from apscheduler.schedulers.background import BackgroundScheduler


@pytest.fixture
def seed_chaos_data():
    path = Path(__file__).resolve().parents[2] / "scripts" / "seed_chaos_data.py"
    spec = importlib.util.spec_from_file_location("chaos_seeder_driver_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("url", "driver"),
    [
        ("postgresql://seed@localhost/synthetic", "psycopg"),
        ("postgres://seed@localhost/synthetic", "psycopg"),
        ("postgresql+psycopg2://seed@localhost/synthetic", "psycopg"),
        ("postgresql+asyncpg://seed@localhost/synthetic", "psycopg"),
        ("postgresql+psycopg://seed@localhost/synthetic", "psycopg"),
        ("sqlite:///:memory:", "pysqlite"),
    ],
)
def test_scheduler_seed_selects_installed_sync_driver(monkeypatch, seed_chaos_data, url, driver):
    engines = []
    real_jobstore = jobstore_module.SQLAlchemyJobStore

    def capture_jobstore(**kwargs):
        store = real_jobstore(**kwargs)
        engines.append(store.engine)
        return store

    monkeypatch.setattr(seed_chaos_data, "POSTGRES_URL", url)
    monkeypatch.setattr(jobstore_module, "SQLAlchemyJobStore", capture_jobstore)
    # Keep real engine construction and job validation, but never start a
    # scheduler thread or connect its persistent store to a database.
    monkeypatch.setattr(BackgroundScheduler, "start", lambda self, **kwargs: None)
    monkeypatch.setattr(BackgroundScheduler, "shutdown", lambda self: None)
    try:
        assert seed_chaos_data.seed_scheduler_jobs() == {"postgres_scheduler_jobs": 15}
        assert len(engines) == 1
        assert engines[0].dialect.driver == driver
    finally:
        for engine in engines:
            engine.dispose()
