"""Pure-python tests for scripts/railway/bootstrap_staging_database.py.

No Docker, Postgres or Railway: the single ``railway()`` seam and the direct
role-login ``role_psql()`` are replaced with in-memory fakes. The live
rehearsal (real Postgres 18 + a fake ``railway`` executable) is described in
docs/operations/DATABASE_ROLE_CUTOVER.md.

Every credential-looking value below is a sentinel, never a real secret.
"""

from __future__ import annotations

import base64
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "railway" / "bootstrap_staging_database.py"
WRAPPER = REPO_ROOT / "scripts" / "railway" / "bootstrap_staging_database.sh"

_SPEC = importlib.util.spec_from_file_location("bootstrap_staging_database", SCRIPT)
assert _SPEC and _SPEC.loader
boot = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = boot  # dataclasses resolve annotations through sys.modules
_SPEC.loader.exec_module(boot)

SENTINEL_SECRET = "sentinel-existing-secret-value-must-never-print"  # pragma: allowlist secret


class FakeRailway:
    """In-memory stand-in for the Railway CLI, recording argv and stdin separately."""

    def __init__(self, variables: dict):
        self.variables = dict(variables)
        self.calls: list[list[str]] = []
        self.stdins: list[str] = []
        self.provider_sql: list[str] = []

    def __call__(self, args, *, stdin=""):
        args = list(args)
        self.calls.append(args)
        self.stdins.append(stdin)
        out = ""
        if args == ["whoami"]:
            out = "Logged in as Test"
        elif args[:2] == ["run", "--help"]:
            out = "Options:\n      --no-local   Skip local develop overrides\n"
        elif args[0] == "run":
            child = args[args.index("--") + 1 :]
            if "-c" in child and child[0] == sys.executable:
                out = json.dumps(
                    {
                        "stdin_ok": stdin == boot.STDIN_PROBE,
                        "environment": "staging",
                        "project": boot.DEFAULT_PROJECT_ID,
                        "host": "proxy.example.invalid",
                        "port": 15432,
                        "user": "postgres",
                        "database": "railway",
                        "sslmode": "",
                    }
                )
            elif child[:2] == ["sh", "-c"]:
                self.provider_sql.append(stdin)
                if boot.INVENTORY_SENTINEL in stdin:
                    out = f"whoami|postgres|true|railway|180006\n{boot.INVENTORY_SENTINEL}\n"
                elif boot.PROVIDER_SENTINEL in stdin:
                    out = f"{boot.PROVIDER_SENTINEL}\n"
        elif args[:2] == ["variable", "list"]:
            out = json.dumps(self.variables)
        elif args[:2] == ["variable", "set"]:
            self.variables[args[2]] = stdin
        return subprocess.CompletedProcess(args, 0, stdout=out, stderr="")


@pytest.fixture
def fake(monkeypatch):
    railway = FakeRailway(
        {
            "AUTH_SECRET_KEY": SENTINEL_SECRET,
            "DATABASE_URL": "postgresql://postgres:" + SENTINEL_SECRET + "@postgres.railway.internal:5432/railway",
            "AUTH_OTP_HMAC_SECRET": None,  # sealed: present, value hidden
            "REDIS_URL": "redis://default:" + SENTINEL_SECRET + "@redis.railway.internal:6379",
            "REGENGINE_ENV": "development",
        }
    )
    role_logins: list[tuple[str, str]] = []

    def fake_role_psql(ctx, role, password, sql, sentinel, what):
        role_logins.append((role, password))
        if role == boot.MIGRATOR_ROLE:
            return [
                ["identity", role, role, ctx.database, "public, fsma, extensions", "UTC"],
                ["seed", "created"],
                ["function-owner", role],
                ["alembic", ""],
                ["fsma-tables", "false"],
                [sentinel],
            ]
        return [["identity", role, role, ctx.database], [sentinel]]

    monkeypatch.setattr(boot, "railway", railway)
    monkeypatch.setattr(boot, "role_psql", fake_role_psql)
    monkeypatch.setattr(boot.shutil, "which", lambda name: "/usr/bin/" + os.path.basename(name))
    railway.role_logins = role_logins
    return railway


@pytest.mark.parametrize("environment", ["production", "Production", " production ", "prod", "Staging", "", "dev"])
def test_refuses_every_environment_except_exact_staging_before_any_railway_call(fake, capsys, environment):
    assert boot.main(["--apply", "--environment", environment]) == boot.EXIT_REFUSED
    assert fake.calls == []
    assert "REFUSED" in capsys.readouterr().err


@pytest.mark.parametrize("database", ["railway", "postgres", "template1", "Regengine", "drop;table", ""])
def test_refuses_archive_system_or_invalid_database_names(fake, database):
    assert boot.main(["--apply", "--database", database]) == boot.EXIT_REFUSED
    assert fake.calls == []


def test_wrapper_refuses_production_without_invoking_railway(tmp_path):
    marker = tmp_path / "railway-was-called"
    fake_bin = tmp_path / "railway"
    fake_bin.write_text(f"#!/bin/sh\ntouch {marker}\nexit 0\n")
    fake_bin.chmod(fake_bin.stat().st_mode | stat.S_IEXEC)
    env = dict(os.environ, PATH=f"{tmp_path}{os.pathsep}{os.environ['PATH']}", PYTHON_BIN=sys.executable)
    result = subprocess.run(
        ["bash", str(WRAPPER), "--apply", "--environment", "production"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert result.returncode == boot.EXIT_REFUSED
    assert "never targets production" in result.stderr
    assert not marker.exists()


def test_redeploy_requires_apply(fake):
    with pytest.raises(SystemExit) as exc:
        boot.main(["--redeploy"])
    assert exc.value.code == 2
    assert fake.calls == []


def test_dry_run_changes_nothing_and_prints_no_secret(fake, capsys):
    assert boot.main([]) == 0  # dry run is the default
    out = capsys.readouterr().out
    assert SENTINEL_SECRET not in out
    mutating = [c for c in fake.calls if c[:2] == ["variable", "set"] or c[0] == "redeploy"]
    assert mutating == []
    assert fake.role_logins == []
    # Only the read-only inventory reached psql; the provisioning SQL was printed, not run.
    assert len(fake.provider_sql) == 1 and boot.INVENTORY_SENTINEL in fake.provider_sql[0]
    assert "DRY RUN: nothing was changed" in out
    assert "${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/regengine_staging" in out
    assert "AUTH_OTP_HMAC_SECRET: present: keep" in out
    assert "AUDIT_INTEGRITY_KEY: missing: generate" in out


def test_apply_sends_values_over_stdin_only_and_keeps_existing_secrets(fake, capsys):
    assert boot.main(["--apply"]) == 0
    out = capsys.readouterr().out

    sets = [(call, stdin) for call, stdin in zip(fake.calls, fake.stdins) if call[:2] == ["variable", "set"]]
    stored = {call[2]: stdin for call, stdin in sets}
    for call, _ in sets:
        assert "--stdin" in call and "--skip-deploys" in call
        assert not any("=" in arg for arg in call), call  # no KEY=VALUE argv form
        assert call[call.index("-e") + 1] == "staging"
        assert call[call.index("-s") + 1] == boot.APP_SERVICE

    # Sealed/present secret kept; missing ones generated; literals pinned.
    assert "AUTH_OTP_HMAC_SECRET" not in stored
    assert len(stored["AUDIT_INTEGRITY_KEY"]) >= 32
    assert len(stored["TOOL_ACCESS_SECRET"]) >= 64
    assert stored["TOOL_ACCESS_SECRET"] != SENTINEL_SECRET
    assert stored["REGENGINE_ENV"] == "staging"
    assert stored["REGENGINE_REQUIRE_RLS_ENFORCEMENT"] == "1"
    assert "REDIS_URL" not in stored  # present, so never overwritten

    passwords = {}
    for name, role in boot.ROLE_URL_VARIABLES:
        match = re.fullmatch(
            rf"postgresql://{role}:([0-9a-f]{{64}})@\$\{{\{{Postgres\.PGHOST\}}\}}:\$\{{\{{Postgres\.PGPORT\}}\}}/regengine_staging",
            stored[name],
        )
        assert match, name
        passwords[role] = match.group(1)
    assert len(set(passwords.values())) == 3
    assert dict(fake.role_logins) == passwords  # each login used the password that was stored

    generated = list(passwords.values()) + [stored["AUDIT_INTEGRITY_KEY"], stored["TOOL_ACCESS_SECRET"]]
    everything_in_argv = " ".join(" ".join(call) for call in fake.calls)
    provisioning = next(sql for sql in fake.provider_sql if boot.PROVIDER_SENTINEL in sql)
    for value in generated + [SENTINEL_SECRET]:
        assert value not in everything_in_argv
        assert value not in out
        assert value not in provisioning  # the server only ever receives SCRAM verifiers
    assert provisioning.count("PASSWORD 'SCRAM-SHA-256$4096:") == 3
    assert "CREATE DATABASE %I OWNER %I TEMPLATE template0" in provisioning
    assert "IN DATABASE regengine_staging SET search_path = public, fsma, extensions" in provisioning
    assert not any(call[0] == "redeploy" for call in fake.calls)


def test_apply_with_redeploy_targets_staging_app_only(fake):
    assert boot.main(["--apply", "--redeploy"]) == 0
    redeploys = [call for call in fake.calls if call[0] == "redeploy"]
    assert redeploys == [["redeploy", "-p", boot.DEFAULT_PROJECT_ID, "-e", "staging", "-s", "RegEngine", "--yes"]]


def test_apply_refuses_unversioned_schema_in_existing_target(fake, monkeypatch):
    def unversioned(ctx, role, password, sql, sentinel, what):
        return [
            ["identity", role, role, ctx.database, "public", "UTC"],
            ["seed", "already-present"],
            ["function-owner", role],
            ["alembic", ""],
            ["fsma-tables", "true"],
            [sentinel],
        ]

    monkeypatch.setattr(boot, "role_psql", unversioned)
    assert boot.main(["--apply"]) == boot.EXIT_FAILED
    assert not any(call[:2] == ["variable", "set"] for call in fake.calls)


def test_missing_stdin_forwarding_is_fatal_before_any_change(fake, monkeypatch):
    original = fake.__call__

    def no_stdin(args, *, stdin=""):
        return original(args, stdin="" if list(args)[:1] == ["run"] else stdin)

    monkeypatch.setattr(boot, "railway", no_stdin)
    assert boot.main(["--apply"]) == boot.EXIT_FAILED
    assert fake.provider_sql == []
    assert not any(call[:2] == ["variable", "set"] for call in fake.calls)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ('{"A": "x", "B": null, "C": ""}', {"A": True, "B": True, "C": False}),
        ('[{"name": "A", "value": "x"}, {"key": "B", "value": null}]', {"A": True, "B": True}),
        ('A new version of the Railway CLI is available\n{"A": "x"}', {"A": True}),
    ],
)
def test_parse_variable_presence_reports_names_only(raw, expected):
    assert boot.parse_variable_presence(raw) == expected


def test_parse_variable_presence_rejects_garbage():
    with pytest.raises(boot.BootstrapError):
        boot.parse_variable_presence("not json")


def test_posture_warnings_never_echo_values():
    raw = json.dumps({"AUTH_OTP_HMAC_SECRET": "otp-xyz", "TOOL_ACCESS_SECRET": "dup-xyz", "AUTH_SECRET_KEY": "dup-xyz"})
    warnings = boot.posture_warnings(raw)
    assert len(warnings) == 2
    assert not any("otp-xyz" in w or "dup-xyz" in w for w in warnings)


def test_scram_verifier_matches_postgresql_known_answer():
    # Generated by PostgreSQL 18 (CREATE ROLE ... PASSWORD '<password>'), read from pg_authid.
    password = "known-answer-test-password"  # pragma: allowlist secret
    expected = (
        "SCRAM-SHA-256$4096:CAU4fHeGOVwwuzSZA8HGzA==$XDGdPCA5C8zmuTkZrWOHdlnnCdh1pwmfjkTSySFT3kI="  # pragma: allowlist secret
        ":OIaxnXrXugRWni4L6jg4oNfRMjXdjV1PXIIp668cvHU="  # pragma: allowlist secret
    )
    salt = base64.b64decode("CAU4fHeGOVwwuzSZA8HGzA==")
    assert boot.scram_sha256_verifier(password, salt=salt) == expected


def _normalize(sql: str) -> str:
    return " ".join(sql.replace("public.get_tenant_context", "get_tenant_context").split())


def test_get_tenant_context_seed_matches_ci_fresh_chain_seed():
    """The bootstrap must reuse the live-db-suite seed, not invent a new body."""
    workflow = (REPO_ROOT / ".github" / "workflows" / "backend-ci.yml").read_text(encoding="utf-8")
    seeds = re.findall(
        r"(CREATE OR REPLACE FUNCTION get_tenant_context\(\).*?\$fn\$ LANGUAGE plpgsql STABLE;)", workflow, re.S
    )
    assert seeds, "backend-ci.yml no longer seeds get_tenant_context(); re-check the fresh-chain bootstrap"
    assert _normalize(boot.GET_TENANT_CONTEXT_SQL) in {_normalize(seed) for seed in seeds}
