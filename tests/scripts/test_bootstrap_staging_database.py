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
            "pghost": "postgres.railway.internal",
            "pgport": "5432",
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


def _fake_role_psql(logins, failing: set | None = None):
    def fake(ctx, role, password, sql, sentinel, what):
        logins.append((role, password))
        if failing and role in failing:
            raise boot.BootstrapError(f"{what} failed (exit 2): password authentication failed")
        if "need_seed" in sql:
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
    monkeypatch.setattr(boot, "read_psql_major", lambda psql: 16)  # hermetic: no real psql needed
    railway.role_logins = logins
    return railway


def _existing_roles(fake: FakeRailway, *extra_rows: str, managed: bool = True, target: bool = True) -> None:
    """Roles already on the cluster; managed=True means an earlier bootstrap run created them."""
    flag = "true" if managed else "false"
    fake.inventory_rows += [f"role|{role}|true|false|false|false|false|false|{flag}" for role in boot.ALL_ROLES]
    if target:
        fake.inventory_rows.append("database|regengine_staging|regengine_migrator")
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
     "regengine_x;drop", 'regengine_"x', "", "regengine_nl\n", "regengine_nl\n\n", " regengine_x"],
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


def test_elevated_existing_role_is_outside_use_even_without_objects_or_sessions(fake, capsys):
    """R1: a SUPERUSER regengine with no detectable objects/sessions is not silently demoted."""
    _existing_roles(fake, "outside|regengine|has elevated attributes (SUPERUSER)")
    assert boot.main(["--dry-run"]) == boot.EXIT_REFUSED
    assert "OUTSIDE USE: role regengine has elevated attributes (SUPERUSER)" in capsys.readouterr().out
    assert boot.main(["--apply", "--rotate-passwords"]) == boot.EXIT_REFUSED
    assert fake.sets() == []
    assert not any(boot.PROVIDER_SENTINEL in sql for sql in fake.provider_sql)
    # The same rule is part of the server-side guard, not only the client check.
    usage_sql = boot.outside_usage_sql("regengine_staging")
    assert "rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication" in usage_sql
    assert "has elevated attributes" in boot.provider_sql("regengine_staging", {}, adopt_existing_roles=False)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda f: f.variables.pop("MIGRATIONS_DATABASE_URL"),
        lambda f: f.sealed.add("DATABASE_URL"),
        lambda f: f.variables.update(ADMIN_DATABASE_URL="postgresql://postgres:x@host:5432/railway"),
    ],
)
def test_foreign_existing_role_without_matching_url_requires_adoption(fake, capsys, mutate):
    """R1: roles this bootstrap did not create need --adopt-existing-roles unless their URL already points at them."""
    _existing_roles(fake, managed=False)
    fake.variables.update(_stored_urls())
    mutate(fake)
    assert boot.main(["--apply", "--rotate-passwords"]) == boot.EXIT_REFUSED
    assert "was not created by this bootstrap" in capsys.readouterr().err
    assert fake.sets() == []
    assert boot.main(["--apply", "--rotate-passwords", "--adopt-existing-roles"]) == 0
    provisioning = next(sql for sql in fake.provider_sql if boot.PROVIDER_SENTINEL in sql)
    assert "COMMENT ON ROLE %I IS %L" in provisioning and boot.MANAGED_ROLE_PREFIX in provisioning


def test_foreign_existing_roles_whose_urls_already_point_at_them_are_kept_without_adoption(fake):
    _existing_roles(fake, managed=False)
    fake.variables.update(_stored_urls())
    assert boot.main(["--apply"]) == 0
    assert not {"DATABASE_URL", "ADMIN_DATABASE_URL", "MIGRATIONS_DATABASE_URL"} & set(fake.sets())


def test_stale_kept_password_is_refused_before_any_superuser_step(fake, monkeypatch, capsys):
    """R2: a stored password that no longer logs in is caught before provisioning, with a non-looping hint."""
    _existing_roles(fake)
    fake.variables.update(_stored_urls())
    logins: list = []
    monkeypatch.setattr(boot, "role_psql", _fake_role_psql(logins, failing={boot.ADMIN_ROLE}))
    assert boot.main(["--apply"]) == boot.EXIT_REFUSED
    err = capsys.readouterr().err
    assert (
        "stored URL password for regengine_sysadmin does not log in; re-run with: "
        "bash scripts/railway/bootstrap_staging_database.sh --apply --rotate-passwords"
    ) in err
    assert not any(boot.PROVIDER_SENTINEL in sql for sql in fake.provider_sql)
    assert fake.sets() == []
    assert boot.main(["--dry-run"]) == boot.EXIT_REFUSED  # the dry run reports it too


def test_kept_password_needs_an_existing_target_database_to_be_tested(fake, capsys):
    _existing_roles(fake, target=False)
    fake.variables.update(_stored_urls())
    assert boot.main(["--apply"]) == boot.EXIT_REFUSED
    assert "cannot be tested" in capsys.readouterr().err
    assert fake.role_logins == []


@pytest.mark.parametrize(
    "host_port,accepted",
    [
        ("${{Postgres.PGHOST}}:${{Postgres.PGPORT}}", True),
        ("postgres.railway.internal:5432", True),
        ("Postgres.Railway.Internal:5432", True),
        ("postgres.railway.internal:6543", False),
        ("other-db.railway.internal:5432", False),
        ("proxy.example.invalid:15432", False),  # the public proxy is not the private endpoint
        ("${{Other.PGHOST}}:${{Postgres.PGPORT}}", False),
    ],
)
def test_kept_url_must_point_at_the_staging_private_endpoint(host_port, accepted):
    """R3: host:port must be the Postgres reference form or its rendered private endpoint."""
    hosts = {(boot.PGHOST_REF, boot.PGPORT_REF), ("postgres.railway.internal", "5432")}
    url = f"postgresql://regengine:{'b' * 64}@{host_port}/regengine_staging"
    result = boot._url_matches(url, "regengine", "regengine_staging", hosts)
    assert (result == "b" * 64) is accepted


def test_role_psql_runs_with_a_private_home_and_no_inherited_libpq_settings(tmp_path, monkeypatch):
    """R5: a personal ~/.postgresql/root.crt or PGSSLROOTCERT cannot change TLS behaviour."""
    capture = tmp_path / "env.json"
    fake_psql = tmp_path / "psql"
    fake_psql.write_text(
        "#!" + sys.executable + "\nimport json, os, sys\n"
        f"sys.stdin.read(); json.dump(dict(os.environ), open({str(capture)!r}, 'w'))\n"
        "print('identity|regengine|regengine|regengine_staging|true'); print('bootstrap-login-sql-complete')\n"
    )
    fake_psql.chmod(0o755)
    personal = tmp_path / "personal"
    (personal / ".postgresql").mkdir(parents=True)
    (personal / ".postgresql" / "root.crt").write_text("not a real CA\n")
    monkeypatch.setenv("HOME", str(personal))
    monkeypatch.setenv("PGSSLROOTCERT", str(personal / ".postgresql" / "root.crt"))
    monkeypatch.setenv("PGSSLMODE", "verify-full")
    private_home = tmp_path / "private"
    private_home.mkdir()
    ctx = boot.Context(project=PROJECT, environment="staging", database="regengine_staging", apply=True)
    ctx.psql, ctx.psql_home = str(fake_psql), str(private_home)
    ctx.endpoint = {"host": "proxy.example.invalid", "port": "15432", "user": "postgres", "database": "railway"}
    boot.role_psql(ctx, "regengine", "c" * 64, boot.runtime_login_sql(), boot.LOGIN_SENTINEL, "login")
    env = json.loads(capture.read_text())
    assert env["HOME"] == str(private_home)
    assert env["PGSSLMODE"] == "require"
    assert env["PGCHANNELBINDING"] == "require"  # SCRAM-SHA-256-PLUS: no cleartext/MD5 password to a MITM
    assert "PGSSLROOTCERT" not in env


def test_role_psql_channel_binding_cannot_be_overridden_by_the_operator_env(tmp_path, monkeypatch):
    capture = tmp_path / "env.json"
    fake_psql = tmp_path / "psql"
    fake_psql.write_text(
        "#!" + sys.executable + "\nimport json, os, sys\n"
        f"sys.stdin.read(); json.dump(dict(os.environ), open({str(capture)!r}, 'w'))\n"
        "print('identity|regengine|regengine|regengine_staging|true'); print('bootstrap-login-sql-complete')\n"
    )
    fake_psql.chmod(0o755)
    monkeypatch.setenv("PGCHANNELBINDING", "disable")
    ctx = boot.Context(project=PROJECT, environment="staging", database="regengine_staging", apply=True)
    ctx.psql, ctx.psql_home = str(fake_psql), str(tmp_path)
    ctx.endpoint = {"host": "proxy.example.invalid", "port": "15432", "user": "postgres", "database": "railway"}
    boot.role_psql(ctx, "regengine", "c" * 64, boot.runtime_login_sql(), boot.LOGIN_SENTINEL, "login")
    assert json.loads(capture.read_text())["PGCHANNELBINDING"] == "require"


@pytest.mark.parametrize(
    "version_text,major",
    [
        ("psql (PostgreSQL) 16.13 (Ubuntu 16.13-0ubuntu0.24.04.1)", 16),
        ("psql (PostgreSQL) 18.0", 18),
        ("psql (PostgreSQL) 13.22", 13),
        ("psql (PostgreSQL) 12.18", 12),
        ("psql (PostgreSQL) 9.6.24", 9),
        ("something else", None),
    ],
)
def test_parse_psql_major(version_text, major):
    assert boot.parse_psql_major(version_text) == major


@pytest.mark.parametrize("major,allowed", [(9, False), (12, False), (None, False), (13, True), (18, True)])
def test_refuses_psql_older_than_13_before_any_railway_run(fake, monkeypatch, major, allowed):
    """libpq < 13 silently ignores PGCHANNELBINDING, so such a psql could hand a password to a MITM."""
    monkeypatch.setattr(boot, "read_psql_major", lambda psql: major)
    code = boot.main(["--apply"])
    if allowed:
        assert code == 0
    else:
        assert code == boot.EXIT_REFUSED
        assert not any(call[0] == "run" for call in fake.calls)
        assert fake.sets() == []


def test_blocking_outgoing_grant_is_refused_even_with_adoption(fake, capsys):
    """A RegEngine role that re-granted a foreign role to a foreign role cannot be cleaned up by cascading."""
    _existing_roles(
        fake,
        "outside|regengine|is a member of role vendor_ops (granted by postgres, WITH ADMIN OPTION)",
        "outside|regengine|used its ADMIN OPTION to grant role vendor_ops to role contractor",
        "blocked-grant|regengine|vendor_ops|contractor",
    )
    fake.variables.update(_stored_urls())
    assert boot.main(["--dry-run", "--adopt-existing-roles"]) == boot.EXIT_REFUSED
    captured = capsys.readouterr()
    assert (
        "BLOCKING GRANT: regengine used its ADMIN OPTION to grant foreign role vendor_ops to contractor" in captured.out
    )
    assert "revoke them by hand" in captured.err
    assert boot.main(["--apply", "--adopt-existing-roles", "--rotate-passwords"]) == boot.EXIT_REFUSED
    assert fake.sets() == []
    assert not any(boot.PROVIDER_SENTINEL in sql for sql in fake.provider_sql)


def test_main_creates_and_removes_the_private_psql_home(fake):
    seen = []
    original = boot.preflight

    def spy(ctx):
        seen.append(ctx.psql_home)
        assert os.path.isdir(ctx.psql_home) and not os.listdir(ctx.psql_home)
        assert stat.S_IMODE(os.stat(ctx.psql_home).st_mode) == 0o700
        return original(ctx)

    boot.preflight, saved = spy, boot.preflight
    try:
        assert boot.main([]) == 0
    finally:
        boot.preflight = saved
    assert seen and not os.path.exists(seen[0])


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
    err = capsys.readouterr().err
    assert "MIGRATIONS_DATABASE_URL was not updated (unset, or still holding the old password)" in err
    assert "gunicorn never starts" in err and "--rotate-passwords" in err


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["--apply"], "bash scripts/railway/bootstrap_staging_database.sh --apply --rotate-passwords"),
        (
            ["--apply", "--adopt-existing-roles", "--rotate-passwords"],
            "bash scripts/railway/bootstrap_staging_database.sh --apply --adopt-existing-roles --rotate-passwords",
        ),
        (
            ["--apply", "--adopt-existing-roles", "--rotate-passwords", "--database", "regengine_staging_b"],
            "bash scripts/railway/bootstrap_staging_database.sh --apply --adopt-existing-roles --rotate-passwords "
            "--database regengine_staging_b",
        ),
    ],
)
def test_recovery_hint_repeats_the_options_the_run_needs(fake, capsys, argv, expected):
    """A failed run's hint names a command that can work.

    Adoption leaves the pre-existing roles' grants and policies in the archive
    database, so a re-run without --adopt-existing-roles is refused again. The
    hint must carry it (and a non-default --database) instead of printing a
    bare --apply --rotate-passwords.
    """
    if "--adopt-existing-roles" in argv:
        _existing_roles(fake, managed=False)
    fake.fail_set = "REGENGINE_ENV"
    assert boot.main(argv) == boot.EXIT_FAILED
    err = capsys.readouterr().err
    assert "gunicorn never starts" in err
    assert err.rstrip().endswith(expected)


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
    private_home = tmp_path / "private-home"
    private_home.mkdir()
    subprocess.run(
        [sys.executable, "-c", boot.PSQL_LAUNCHER, str(private_home), str(fake_psql), *boot.PSQL_FLAGS],
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(tmp_path / "personal-home"),
            "DATABASE_PUBLIC_URL": url,
            "PGOPTIONS": "-c search_path=evil",
            "PGSSLROOTCERT": "/personal/root.crt",
            "PGCHANNELBINDING": "disable",
        },
        check=True,
    )
    seen = json.loads(capture.read_text())
    assert SENTINEL_SECRET not in " ".join(seen["argv"])
    assert seen["argv"][1:] == list(boot.PSQL_FLAGS)
    env = seen["env"]
    assert env["HOME"] == str(private_home)  # no personal ~/.postgresql/root.crt or ~/.psqlrc
    assert "PGSSLROOTCERT" not in env
    assert env["PGPASSWORD"] == SENTINEL_SECRET
    assert (env["PGHOST"], env["PGPORT"], env["PGUSER"], env["PGDATABASE"]) == (
        "proxy.example.invalid",
        "15432",
        "postgres",
        "railway",
    )
    assert env["PGSSLMODE"] == "require"
    assert env["PGCHANNELBINDING"] == "require"  # superuser password never offered to a MITM; not overridable
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
        try:
            if stat_file.exists() and stat_file.read_text().split()[2] == "Z":
                return  # killed; waiting to be reaped by init
        except (FileNotFoundError, ProcessLookupError):
            return  # reaped between the kill probe and the read: gone
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


# --- membership revocation against a real, disposable PostgreSQL ------------
#
# Roles are cluster-wide, so these tests never touch a shared server: they start
# their own throwaway container and run every scenario inside a transaction that
# is rolled back. Without Docker they skip, or fail under REGENGINE_REQUIRE_DB=1.

_CHAIN_ROLES = ("alice", "bob", "carol", "vendor_ops", "contractor")


def _skip_or_fail(reason: str) -> None:
    if os.getenv("REGENGINE_REQUIRE_DB", "").strip().lower() in {"1", "true", "yes"}:
        pytest.fail(f"{reason} (REGENGINE_REQUIRE_DB=1)")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def disposable_pg_url():
    try:
        import psycopg  # noqa: F401

        try:
            from testcontainers.community.postgres import PostgresContainer
        except ImportError:  # testcontainers < the community split (the pinned 4.15)
            from testcontainers.postgres import PostgresContainer
    except ImportError as exc:
        _skip_or_fail(f"psycopg/testcontainers unavailable: {exc}")
    try:
        container = PostgresContainer("postgres:17", driver=None)
        container.start()
    except Exception as exc:  # no Docker daemon, image pull blocked, ...
        _skip_or_fail(f"cannot start a disposable PostgreSQL container: {exc}")
    try:
        yield container.get_connection_url()
    finally:
        container.stop()


@pytest.fixture
def pg(disposable_pg_url):
    """(connection, notices) inside one transaction that is always rolled back."""
    import psycopg

    notices: list[tuple[str, str]] = []
    conn = psycopg.connect(disposable_pg_url)
    conn.add_notice_handler(lambda diag: notices.append((diag.severity_nonlocalized or "", diag.message_primary or "")))
    try:
        for role in (*boot.ALL_ROLES, *_CHAIN_ROLES):
            conn.execute(f"CREATE ROLE {boot.quote_ident(role)}")
        yield conn, notices
    finally:
        conn.rollback()
        conn.close()


def _as(conn, role: str, statement: str) -> None:
    conn.execute(f"SET ROLE {boot.quote_ident(role)}")
    conn.execute(statement)
    conn.execute("RESET ROLE")


def _memberships(conn) -> list[tuple[str, str, str]]:
    roles = list(boot.ALL_ROLES)
    return conn.execute(
        "SELECT g.rolname, m.rolname, gr.rolname FROM pg_auth_members am "
        "JOIN pg_roles g ON g.oid = am.roleid JOIN pg_roles m ON m.oid = am.member "
        "JOIN pg_roles gr ON gr.oid = am.grantor "
        "WHERE g.rolname = ANY(%s) OR m.rolname = ANY(%s) ORDER BY 1, 2, 3",
        (roles, roles),
    ).fetchall()


def _listing(conn) -> list[tuple[str, str]]:
    return conn.execute(f"SELECT role_name, detail FROM ({boot.outside_usage_sql('regengine_staging')}) o").fetchall()


def test_incoming_admin_option_chain_is_listed_and_fully_revoked(pg):
    import psycopg

    conn, notices = pg
    superuser = conn.execute("SELECT current_user").fetchone()[0]
    conn.execute("GRANT regengine TO alice WITH ADMIN OPTION")
    _as(conn, "alice", "GRANT regengine TO bob WITH ADMIN OPTION")
    _as(conn, "bob", "GRANT regengine TO carol")

    # Dry-run listing shows every link of the chain with its grantor.
    listing = set(_listing(conn))
    assert ("regengine", f"is granted to role alice (granted by {superuser}, WITH ADMIN OPTION)") in listing
    assert ("regengine", "is granted to role bob (granted by alice, WITH ADMIN OPTION)") in listing
    assert ("regengine", "is granted to role carol (granted by bob)") in listing
    assert conn.execute(boot.blocked_grants_sql()).fetchall() == []

    # Negative control: the pre-fix statement (REVOKE without CASCADE) cannot remove the chain.
    with pytest.raises(psycopg.errors.DependentObjectsStillExist):
        with conn.transaction():
            conn.execute(f"REVOKE regengine FROM alice GRANTED BY {boot.quote_ident(superuser)}")

    notices.clear()
    conn.execute(boot.membership_sql())
    assert _memberships(conn) == []
    assert not [n for n in notices if n[0] == "WARNING"], notices
    revoked = [message for _, message in notices if message.startswith("revoked membership:")]
    assert 1 <= len(revoked) <= 3  # CASCADE may take dependents with it; never a line for a grant already gone
    assert f"revoked membership: regengine from alice (granted by {superuser}) with CASCADE" in revoked
    assert any("memberships involving RegEngine roles removed: 3" in message for _, message in notices)


def test_outgoing_membership_with_foreign_dependent_grant_is_refused_not_cascaded(pg):
    import psycopg

    conn, _ = pg
    conn.execute("GRANT vendor_ops TO regengine WITH ADMIN OPTION")
    _as(conn, "regengine", "GRANT vendor_ops TO contractor")
    before = _memberships(conn)

    assert conn.execute(boot.blocked_grants_sql()).fetchall() == [("regengine", "vendor_ops", "contractor")]
    assert ("regengine", "used its ADMIN OPTION to grant role vendor_ops to role contractor") in set(_listing(conn))
    with pytest.raises(psycopg.errors.RaiseException, match="without cascading outside RegEngine"):
        with conn.transaction():
            conn.execute(boot.membership_sql())
    assert _memberships(conn) == before  # nothing revoked
    foreign = conn.execute(
        "SELECT count(*) FROM pg_auth_members am JOIN pg_roles g ON g.oid = am.roleid "
        "JOIN pg_roles m ON m.oid = am.member WHERE g.rolname = 'vendor_ops' AND m.rolname = 'contractor'"
    ).fetchone()
    assert foreign == (1,)  # the foreign grant is untouched


def test_outgoing_chain_between_regengine_roles_is_revoked_without_cascade(pg):
    conn, notices = pg
    conn.execute("GRANT vendor_ops TO regengine_sysadmin WITH ADMIN OPTION")
    _as(conn, "regengine_sysadmin", "GRANT vendor_ops TO regengine")
    assert conn.execute(boot.blocked_grants_sql()).fetchall() == []

    notices.clear()
    conn.execute(boot.membership_sql())
    assert _memberships(conn) == []
    assert not [n for n in notices if n[0] == "WARNING"], notices
    revoked = [message for _, message in notices if message.startswith("revoked membership:")]
    assert len(revoked) == 2 and not any("CASCADE" in message for message in revoked)
