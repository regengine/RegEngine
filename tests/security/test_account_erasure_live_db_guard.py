"""Fail-closed admission tests for the destructive account-erasure DB proof."""

from __future__ import annotations

import pytest

from tests.security import test_account_erasure_identity_isolation_pg as live_test

_ROLE_URL_NAMES = (
    "MIGRATIONS_DATABASE_URL",
    "DATABASE_URL",
    "ADMIN_DATABASE_URL",
    "ROLE_ADMIN_DATABASE_URL",
)


def _clear_admission_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        *_ROLE_URL_NAMES,
        "CI",
        "GITHUB_ACTIONS",
        "REGENGINE_ALLOW_DESTRUCTIVE_DB_TESTS",
        "REGENGINE_MIGRATION_TEST_DB",
    ):
        monkeypatch.delenv(name, raising=False)


def _set_role_urls(
    monkeypatch: pytest.MonkeyPatch,
    *,
    host: str = "localhost",
    database: str = "live_suite",
) -> tuple[str, ...]:
    urls = tuple(
        f"postgresql://role_{index}:secret_{index}@{host}:5432/{database}"  # pragma: allowlist secret
        for index, _name in enumerate(_ROLE_URL_NAMES)
    )
    for name, url in zip(_ROLE_URL_NAMES, urls, strict=True):
        monkeypatch.setenv(name, url)
    return urls


def test_guard_rejects_missing_role_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_admission_env(monkeypatch)
    _set_role_urls(monkeypatch)
    monkeypatch.delenv("ADMIN_DATABASE_URL")
    monkeypatch.setenv("CI", "true")

    with pytest.raises(pytest.fail.Exception, match="all four"):
        live_test._validated_direct_role_urls()


@pytest.mark.parametrize(
    "invalid_url",
    (
        "not-a-url-with-secret-password",
        "mysql://role:secret-password@localhost/live_suite",  # pragma: allowlist secret
    ),
)
def test_guard_rejects_malformed_or_non_postgres_url_without_leaking_credentials(
    monkeypatch: pytest.MonkeyPatch,
    invalid_url: str,
) -> None:
    _clear_admission_env(monkeypatch)
    _set_role_urls(monkeypatch)
    monkeypatch.setenv("MIGRATIONS_DATABASE_URL", invalid_url)
    monkeypatch.setenv("CI", "true")

    with pytest.raises(pytest.fail.Exception) as exc:
        live_test._validated_direct_role_urls()

    assert "secret-password" not in str(exc.value)


@pytest.mark.parametrize(
    ("variable", "replacement"),
    (
        (
            "ADMIN_DATABASE_URL",
            "postgresql://admin:secret@localhost:5432/not_live_suite",  # pragma: allowlist secret
        ),
        (
            "ROLE_ADMIN_DATABASE_URL",
            "postgresql://provider:secret@other-host:5432/live_suite",  # pragma: allowlist secret
        ),
    ),
)
def test_guard_rejects_mismatched_database_or_host(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    replacement: str,
) -> None:
    _clear_admission_env(monkeypatch)
    _set_role_urls(monkeypatch)
    monkeypatch.setenv(variable, replacement)
    monkeypatch.setenv("CI", "true")

    with pytest.raises(pytest.fail.Exception, match="same PostgreSQL database target"):
        live_test._validated_direct_role_urls()


@pytest.mark.parametrize("database", ("regengine", "regengine_admin"))
def test_guard_always_rejects_local_dev_stack_databases(
    monkeypatch: pytest.MonkeyPatch,
    database: str,
) -> None:
    _clear_admission_env(monkeypatch)
    _set_role_urls(monkeypatch, database=database)
    monkeypatch.setenv("CI", "true")

    with pytest.raises(pytest.fail.Exception, match="dev-stack"):
        live_test._validated_direct_role_urls()


def test_guard_rejects_remote_production_shaped_target_without_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_admission_env(monkeypatch)
    _set_role_urls(
        monkeypatch,
        host="primary.prod.example.com",
        database="regengine_production",
    )
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    with pytest.raises(pytest.fail.Exception, match="explicit destructive-test opt-in"):
        live_test._validated_direct_role_urls()


def test_guard_accepts_known_local_ci_live_suite(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_admission_env(monkeypatch)
    expected = _set_role_urls(monkeypatch)
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_ACTIONS", "true")

    assert live_test._validated_direct_role_urls() == expected


def test_guard_rejects_ci_flag_without_github_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_admission_env(monkeypatch)
    _set_role_urls(monkeypatch)
    monkeypatch.setenv("CI", "true")

    with pytest.raises(pytest.fail.Exception, match="explicit destructive-test opt-in"):
        live_test._validated_direct_role_urls()


def test_guard_accepts_explicitly_designated_disposable_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_admission_env(monkeypatch)
    expected = _set_role_urls(
        monkeypatch,
        host="scratch-db.example.test",
        database="erasure_scratch",
    )
    monkeypatch.setenv("REGENGINE_ALLOW_DESTRUCTIVE_DB_TESTS", "1")
    monkeypatch.setenv(
        "REGENGINE_MIGRATION_TEST_DB",
        "postgresql://designator:another-secret@scratch-db.example.test:5432/erasure_scratch",  # pragma: allowlist secret
    )

    assert live_test._validated_direct_role_urls() == expected


def test_guard_rejects_opt_in_when_designated_target_does_not_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_admission_env(monkeypatch)
    _set_role_urls(monkeypatch, database="erasure_scratch")
    monkeypatch.setenv("REGENGINE_ALLOW_DESTRUCTIVE_DB_TESTS", "true")
    monkeypatch.setenv(
        "REGENGINE_MIGRATION_TEST_DB",
        "postgresql://designator:secret@localhost:5432/different_scratch",  # pragma: allowlist secret
    )

    with pytest.raises(pytest.fail.Exception, match="must match"):
        live_test._validated_direct_role_urls()
