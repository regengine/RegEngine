"""The E2E bootstrap must reject deployed or ambiguous database targets."""

import importlib.util
from pathlib import Path

import pytest

PATH = Path(__file__).resolve().parents[2] / "scripts/setup_e2e_postgres.py"


@pytest.mark.parametrize(
    "environment,mode,url",
    [
        ("production", "true", "postgresql://postgres@localhost/playwright_shared"),
        ("test", "false", "postgresql://postgres@localhost/playwright_shared"),
        ("test", "true", "postgresql://postgres@remote.invalid/playwright_shared"),
        ("test", "true", "postgresql://postgres@localhost/production"),
        ("test", "true", "sqlite:///playwright_shared"),
    ],
)
def test_rejects_non_fixture_target_before_opening_connection(monkeypatch, environment, mode, url):
    spec = importlib.util.spec_from_file_location("setup_e2e", PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("REGENGINE_ENV", environment)
    monkeypatch.setenv("REGENGINE_E2E_MODE", mode)
    monkeypatch.setenv("DATABASE_URL", url)

    def unexpected_connection(*args, **kwargs):
        raise AssertionError("unsafe target reached the database")

    monkeypatch.setattr(module, "create_engine", unexpected_connection)
    with pytest.raises(SystemExit, match="Refusing to prepare"):
        module.main()
