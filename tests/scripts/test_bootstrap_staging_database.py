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
import time
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
PROJECT = boot.DEFAULT_PROJECT_ID


class FakeRailway:
    """In-memory stand-in for the Railway CLI, recording argv and stdin separately."""

    def __init__(self, variables: dict):
        self.variables = dict(variables)
        self.sealed: set[str] = set()
        self.calls: list[list[str]] = []
        self.stdins: list[str] = []
        self.provider_sql: list[str] = []
        self.version = "railway 5.62.1"
        self.probe = {
            "stdin_ok": True,
            "environment": "staging",
            "project": PROJECT,
            "proxy_domain": "proxy.example.invalid",
            "proxy_port": "15432",
            "host": "proxy.example.invalid",
            "port": "15432",
            "user": "postgres",
            "database": "railway",
        }
        self.inventory_rows = ["whoami|postgres|true|railway|180006|true"]
        self.fail_set: str | None = None

    def __call__(self, args, *, stdin=""):
        args = list(args)
        self.calls.append(args)
        self.stdins.append(stdin)
        out, code = "", 0
        if args == ["--version"]:
            out = self.version
        elif args == ["whoami"]:
            out = "Logged in as Test"
        elif args[:2] == ["run", "--help"]:
            out = "Options:\n      --no-local   Skip local develop overrides\n"
        elif args[0] == "run":
            if stdin == boot.STDIN_PROBE:
                out = json.dumps(self.probe)
            elif boot.INVENTORY_SENTINEL in stdin:
                self.provider_sql.append(stdin)
                out = "\n".join(self.inventory_rows + [boot.INVENTORY_SENTINEL]) + "\n"
            elif boot.PROVIDER_SENTINEL in stdin:
                self.provider_sql.append(stdin)
                out = f"{boot.PROVIDER_SENTINEL}\n"
        elif args[:2] == ["variable", "list"]:
            out = json.dumps({k: (None if k in self.sealed else v) for k, v in self.variables.items()})
        elif args[:2] == ["variable", "set"]:
            if args[2] == self.fail_set:
                return subprocess.CompletedProcess(args, 1, stdout="", stderr="simulated Railway API error")
            self.variables[args[2]] = stdin
        return subprocess.CompletedProcess(args, code, stdout=out, stderr="")

    def sets(self) -> list[str]:
        return [call[2] for call in self.calls if call[:2] == ["variable", "set"]]


def _fake_role_psql(logins):
    def fake(ctx, role, password, sql, sentinel, what):
        logins.append((role, password))
        if role == boot.MIGRATOR_ROLE:
            return [
                ["identity", role, role, ctx.database, "public, fsma, extensions", "UTC", "true"],
                ["seed", "created"],
                ["function-owner", role],
                ["alembic", ""],
                ["fsma-tables", "false"],
                [sentinel],
            ]
        return [["identity", role, role, ctx.database, "true"], [sentinel]]

    return fake


@pytest.fixture
def fake(monkeypatch):
    railway = FakeRailway(
        {
            "AUTH_SECRET_KEY": SENTINEL_SECRET,
            "DATABASE_URL": "postgresql://postgres:" + SENTINEL_SECRET + "@postgres.railway.internal:5432/railway",
            "AUTH_OTP_HMAC_SECRET": SENTINEL_SECRET,
            "REDIS_URL": "redis://default:" + SENTINEL_SECRET + "@redis.railway.internal:6379",
            "REGENGINE_ENV": "development",
        }
    )
    railway.sealed.add("AUTH_OTP_HMAC_SECRET")  # sealed: present, value hidden
    logins: list[tuple[str, str]] = []
    monkeypatch.setattr(boot, "railway", railway)
    monkeypatch.setattr(boot, "role_psql", _fake_role_psql(logins))
    monkeypatch.setattr(boot.shutil, "which", lambda name: "/usr/bin/" + os.path.basename(name))
    railway.role_logins = logins
    return railway


def _existing_roles(fake: FakeRailway, *extra_rows: str) -> None:
    fake.inventory_rows += [f"role|{role}|true|false|false|false|false|false" for role in boot.ALL_ROLES]
    fake.inventory_rows += list(extra_rows)


def _stored_urls(password: str = "a" * 64) -> dict:
    return {name: boot.database_url(role, password, "regengine_staging") for name, role in boot.ROLE_URL_VARIABLES}


# --- target guards ---------------------------------------------------------


@pytest.mark.parametrize("environment", ["production", "Production", " production ", "prod", "Staging", "", "dev"])
def test_refuses_every_environment_except_exact_staging_before_any_railway_call(fake, capsys, environment):
    assert boot.main(["--apply", "--environment", environment]) == boot.EXIT_REFUSED
    assert fake.calls == []
    assert "REFUSED" in capsys.readouterr().err


@pytest.mark.parametrize(
    "database",
    ["railway", "postgres", "template1", "user", "regengine", "regengine_", "Regengine_x", "regengine-staging",
     "regengine_x;drop", 'regengine_"x', ""],
)  # fmt: skip
def test_refuses_database_names_outside_the_regengine_namespace(fake, database):
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


@pytest.mark.parametrize("version,allowed", [("railway 5.47.1", False), ("railway 4.9.0", False), ("garbage", False),
                                             ("railway 5.47.2", True), ("railway 5.62.1", True)])  # fmt: skip
def test_refuses_railway_cli_older_than_5_47_2(fake, version, allowed):
    fake.version = version
    code = boot.main(["--apply"])
    if allowed:
        assert code == 0
    else:
        assert code == boot.EXIT_REFUSED
        assert not any(call[0] == "run" for call in fake.calls)  # refused before any railway run
        assert fake.sets() == []


@pytest.mark.parametrize(
    "override",
    [
        {"environment": "production"},
        {"environment": ""},  # marker missing: fail closed
        {"project": "00000000-0000-0000-0000-000000000000"},
        {"project": ""},
        {"proxy_domain": "attacker.example.invalid"},
        {"proxy_port": "5432"},
        {"proxy_domain": "", "proxy_port": ""},
        {"database": "regengine_staging"},  # DATABASE_PUBLIC_URL already names the target
    ],
)
def test_probe_mismatch_refuses_before_any_sql_or_write(fake, override):
    fake.probe.update(override)
    assert boot.main(["--apply"]) == boot.EXIT_REFUSED
    assert fake.provider_sql == []
    assert fake.sets() == []


def test_missing_stdin_forwarding_is_fatal_before_any_change(fake):
    fake.probe["stdin_ok"] = False
    assert boot.main(["--apply"]) == boot.EXIT_FAILED
    assert fake.provider_sql == []
    assert fake.sets() == []


def test_refuses_old_server_and_foreign_owned_target(fake):
    fake.inventory_rows = ["whoami|postgres|true|railway|140011|true"]
    assert boot.main(["--apply"]) == boot.EXIT_REFUSED
    fake.inventory_rows = ["whoami|postgres|true|railway|180006|true", "database|regengine_staging|postgres"]
    assert boot.main(["--apply"]) == boot.EXIT_REFUSED
    assert fake.sets() == []
    assert not any(boot.PROVIDER_SENTINEL in sql for sql in fake.provider_sql)


# --- pre-existing roles (cluster-wide) --------------------------------------


def test_existing_role_used_outside_target_is_refused_without_adoption(fake, capsys):
    _existing_roles(fake, "outside|regengine|owns 3 object(s) in database railway",
                    "outside|regengine|has 1 open session(s) in database railway")  # fmt: skip
    fake.variables.update(_stored_urls())
    assert boot.main(["--dry-run"]) == boot.EXIT_REFUSED
    captured = capsys.readouterr()
    assert "OUTSIDE USE: role regengine owns 3 object(s) in database railway" in captured.out
    assert "--adopt-existing-roles" in captured.err
    assert boot.main(["--apply"]) == boot.EXIT_REFUSED
    assert fake.sets() == []
    assert not any(boot.PROVIDER_SENTINEL in sql for sql in fake.provider_sql)  # no write reached the server


def test_adopt_existing_roles_proceeds_and_arms_server_side_guard_only_when_asked(fake):
    _existing_roles(fake, "outside|regengine_sysadmin|is a member of role pg_read_all_data")
    fake.variables.update(_stored_urls())
    assert boot.main(["--apply", "--adopt-existing-roles"]) == 0
    provisioning = next(sql for sql in fake.provider_sql if boot.PROVIDER_SENTINEL in sql)
    assert "IF true THEN\n        RETURN;" in provisioning
    assert "RESET ALL" in provisioning and "VALID UNTIL %L" in provisioning

    guarded = boot.provider_sql("regengine_staging", {}, adopt_existing_roles=False)
    assert "IF false THEN\n        RETURN;" in guarded
    assert "pre-existing RegEngine roles are used outside" in guarded


def test_existing_roles_keep_verified_passwords_and_write_no_urls(fake):
    _existing_roles(fake)
    fake.variables.update(_stored_urls())
    assert boot.main(["--apply"]) == 0
    provisioning = next(sql for sql in fake.provider_sql if boot.PROVIDER_SENTINEL in sql)
    assert "PASSWORD" not in provisioning
    assert not {"DATABASE_URL", "ADMIN_DATABASE_URL", "MIGRATIONS_DATABASE_URL"} & set(fake.sets())
    assert {role for role, _ in fake.role_logins} == set(boot.ALL_ROLES)
    assert {password for _, password in fake.role_logins} == {"a" * 64}  # logged in with the stored passwords


@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f.variables.pop("MIGRATIONS_DATABASE_URL"),
        lambda f: f.sealed.add("DATABASE_URL"),
        lambda f: f.variables.update(ADMIN_DATABASE_URL="postgresql://postgres:x@host:5432/railway"),
    ],
)
def test_existing_roles_with_missing_sealed_or_foreign_urls_require_rotate_passwords(fake, mutate):
    _existing_roles(fake)
    fake.variables.update(_stored_urls())
    mutate(fake)
    assert boot.main(["--apply"]) == boot.EXIT_REFUSED
    assert fake.sets() == []
    assert boot.main(["--apply", "--rotate-passwords"]) == 0
    provisioning = next(sql for sql in fake.provider_sql if boot.PROVIDER_SENTINEL in sql)
    assert provisioning.count("PASSWORD 'SCRAM-SHA-256$4096:") == 3
    assert fake.sets()[-1] == "MIGRATIONS_DATABASE_URL"


# --- dry run and apply -----------------------------------------------------


def test_dry_run_changes_nothing_and_prints_no_secret(fake, capsys):
    assert boot.main([]) == 0  # dry run is the default
    out = capsys.readouterr().out
    assert SENTINEL_SECRET not in out
    mutating = [c for c in fake.calls if c[:2] == ["variable", "set"] or c[0] == "redeploy"]
    assert mutating == []
    assert fake.role_logins == []
    assert len(fake.provider_sql) == 1 and boot.INVENTORY_SENTINEL in fake.provider_sql[0]
    assert "DRY RUN: nothing was changed" in out
    assert "${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/regengine_staging" in out
    assert "AUDIT_INTEGRITY_KEY = <generated token_urlsafe(48)>" in out
    assert "AUTH_OTP_HMAC_SECRET = <present: kept>" in out
    write_section = out.split("[5]")[1].split("Next steps")[0]
    planned = [line.split(" = ")[0].strip() for line in write_section.splitlines() if " = " in line]
    planned = [name for name in planned if name != "AUTH_OTP_HMAC_SECRET" and name != "REDIS_URL"]  # kept
    assert planned[-1] == "MIGRATIONS_DATABASE_URL"


def test_apply_writes_values_over_stdin_only_in_the_safe_order(fake, capsys):
    assert boot.main(["--apply"]) == 0
    out = capsys.readouterr().out

    sets = [(call, stdin) for call, stdin in zip(fake.calls, fake.stdins) if call[:2] == ["variable", "set"]]
    stored = {call[2]: stdin for call, stdin in sets}
    for call, _ in sets:
        assert "--stdin" in call and "--skip-deploys" in call
        assert not any("=" in arg for arg in call), call  # no KEY=VALUE argv form
    assert [call[2] for call, _ in sets] == [
        "DATABASE_URL",
        "ADMIN_DATABASE_URL",
        "AUDIT_INTEGRITY_KEY",
        "TOOL_ACCESS_SECRET",
        "REGENGINE_ENV",
        "REGENGINE_REQUIRE_RLS_ENFORCEMENT",
        "REGENGINE_MIGRATIONS_ROLE",
        "MIGRATIONS_DATABASE_URL",
    ]

    assert "AUTH_OTP_HMAC_SECRET" not in stored  # sealed: present, kept
    assert len(stored["AUDIT_INTEGRITY_KEY"]) >= 32
    assert len(stored["TOOL_ACCESS_SECRET"]) >= 64
    assert stored["REGENGINE_ENV"] == "staging"
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
    assert 'REVOKE ALL ON DATABASE "regengine_staging" FROM PUBLIC;' in provisioning
    assert 'GRANT CONNECT ON DATABASE "regengine_staging" TO "regengine", "regengine_sysadmin"' in provisioning
    assert 'IN DATABASE "regengine_staging" SET search_path = public, fsma, extensions' in provisioning
    assert not any(call[0] == "redeploy" for call in fake.calls)


def test_failure_partway_leaves_migrations_url_unset(fake, capsys):
    fake.fail_set = "REGENGINE_ENV"
    assert boot.main(["--apply"]) == boot.EXIT_FAILED
    assert "MIGRATIONS_DATABASE_URL" not in fake.variables
    assert "DATABASE_URL" in fake.sets()
    assert "--rotate-passwords" in capsys.readouterr().err


def test_every_run_variable_and_redeploy_call_is_scoped(fake):
    assert boot.main(["--apply", "--redeploy"]) == 0
    scoped = [c for c in fake.calls if c[0] in ("run", "redeploy", "variable") and c[:2] != ["run", "--help"]]
    assert scoped
    for call in scoped:
        assert call[call.index("-p") + 1] == PROJECT, call
        assert call[call.index("-e") + 1] == "staging", call
        assert call[call.index("-s") + 1] in (boot.APP_SERVICE, boot.POSTGRES_SERVICE), call
    for call in (c for c in scoped if c[0] == "run"):
        assert call[call.index("-s") + 1] == boot.POSTGRES_SERVICE
    redeploys = [call for call in fake.calls if call[0] == "redeploy"]
    assert redeploys == [["redeploy", "-p", PROJECT, "-e", "staging", "-s", "RegEngine", "--yes"]]


def test_provider_psql_argv_never_carries_the_connection_url(fake):
    assert boot.main(["--apply"]) == 0
    runs = [call for call in fake.calls if call[0] == "run" and "--" in call]
    for call in runs:
        child = call[call.index("--") + 1 :]
        assert "DATABASE_PUBLIC_URL" not in " ".join(child[3:])  # only the launcher source mentions it
        assert not any(arg.startswith("postgres") and "://" in arg for arg in child)


def test_apply_refuses_unversioned_schema_in_existing_target(fake, monkeypatch):
    def unversioned(ctx, role, password, sql, sentinel, what):
        return [
            ["identity", role, role, ctx.database, "public", "UTC", "true"],
            ["seed", "already-present"],
            ["function-owner", role],
            ["alembic", ""],
            ["fsma-tables", "true"],
            [sentinel],
        ]

    monkeypatch.setattr(boot, "role_psql", unversioned)
    assert boot.main(["--apply"]) == boot.EXIT_FAILED
    assert fake.sets() == []


# --- process handling -------------------------------------------------------


def test_psql_launcher_moves_the_url_into_the_environment(tmp_path):
    capture = tmp_path / "capture.json"
    fake_psql = tmp_path / "psql"
    fake_psql.write_text(
        "#!" + sys.executable + "\n"
        "import json, os, sys\n"
        f"json.dump({{'argv': sys.argv, 'env': dict(os.environ)}}, open({str(capture)!r}, 'w'))\n"
    )
    fake_psql.chmod(0o755)
    url = "postgresql://postgres:" + SENTINEL_SECRET + "@proxy.example.invalid:15432/railway"
    subprocess.run(
        [sys.executable, "-c", boot.PSQL_LAUNCHER, str(fake_psql), *boot.PSQL_FLAGS],
        env={"PATH": os.environ["PATH"], "DATABASE_PUBLIC_URL": url, "PGOPTIONS": "-c search_path=evil"},
        check=True,
    )
    seen = json.loads(capture.read_text())
    assert SENTINEL_SECRET not in " ".join(seen["argv"])
    assert seen["argv"][1:] == list(boot.PSQL_FLAGS)
    env = seen["env"]
    assert env["PGPASSWORD"] == SENTINEL_SECRET
    assert (env["PGHOST"], env["PGPORT"], env["PGUSER"], env["PGDATABASE"]) == (
        "proxy.example.invalid",
        "15432",
        "postgres",
        "railway",
    )
    assert env["PGSSLMODE"] == "require"
    assert "DATABASE_PUBLIC_URL" not in env
    assert env["PGOPTIONS"] == boot.SERVER_OPTIONS  # the inherited PGOPTIONS is replaced


def test_timeout_kills_the_whole_process_group(tmp_path, monkeypatch):
    pidfile = tmp_path / "grandchild.pid"
    fake_bin = tmp_path / "railway"
    fake_bin.write_text(f"#!/bin/sh\nsleep 60 &\necho $! > {pidfile}\nwait\n")
    fake_bin.chmod(0o755)
    monkeypatch.setenv("RAILWAY_BIN", str(fake_bin))
    monkeypatch.setattr(boot, "COMMAND_TIMEOUT_S", 1)
    with pytest.raises(subprocess.TimeoutExpired):
        boot.railway(["run", "--", "psql"])
    pid = int(pidfile.read_text().strip())
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return
        stat_file = Path(f"/proc/{pid}/stat")
        if stat_file.exists() and stat_file.read_text().split()[2] == "Z":
            return  # killed; waiting to be reaped by init
        time.sleep(0.1)
    pytest.fail("grandchild of the timed-out railway call survived")


# --- parsing and fixtures ---------------------------------------------------


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
    short, duplicate = "otp-xyz", "dup-xyz"
    values = {"AUTH_OTP_HMAC_SECRET": short, "TOOL_ACCESS_SECRET": duplicate, "AUTH_SECRET_KEY": duplicate}
    warnings = boot.posture_warnings(values)
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


def test_quoting_helpers():
    assert boot.quote_ident('a"b') == '"a""b"'
    assert boot.quote_literal("it's") == "'it''s'"


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
