#!/usr/bin/env python3
"""One-command bootstrap of a FRESH RegEngine staging database on Railway.

Why
---
Since 85df24e (2026-08-31) ``scripts/run-migrations.sh`` exits 64 on Railway
unless ``MIGRATIONS_DATABASE_URL`` is set, and v111 only accepts a URL that
logs in as a dedicated owner role: NOSUPERUSER, NOBYPASSRLS, no memberships,
owning the database and every protected object, with the runtime roles
``regengine`` and ``regengine_sysadmin`` already provisioned. Staging never
had that topology, so every staging deploy since then stops before gunicorn.

What ``--apply`` does
---------------------
1. Read-only preflight: Railway CLI login, ``railway run`` forwards stdin,
   the Postgres service exposes ``DATABASE_PUBLIC_URL`` for this environment,
   and a read-only inventory of the three roles and the target database.
2. As the Railway Postgres template superuser, reached only inside
   ``railway run -s Postgres`` so this script never sees that password:
   create or pin ``regengine``, ``regengine_sysadmin`` and
   ``regengine_migrator`` (LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB
   NOCREATEROLE NOREPLICATION), revoke any membership involving them, set
   fresh random passwords (sent as SCRAM verifiers, never as plaintext),
   ``CREATE DATABASE <db> OWNER regengine_migrator TEMPLATE template0`` if it
   is absent, ``GRANT CONNECT``, and pin the migrator's ``search_path`` and
   ``timezone`` inside the new database only.
3. Log in AS ``regengine_migrator`` to the new database and create
   ``get_tenant_context()`` exactly as the backend-ci live-db-suite does for
   a fresh chain (only if it is absent).
4. Log in as ``regengine`` and ``regengine_sysadmin`` to prove the passwords
   and CONNECT grants.
5. Store ``MIGRATIONS_DATABASE_URL``, ``DATABASE_URL`` and
   ``ADMIN_DATABASE_URL`` on the RegEngine service, pointing at the new
   database over the private network via ``${{Postgres.PGHOST}}`` and
   ``${{Postgres.PGPORT}}`` references.
6. Generate ``AUTH_OTP_HMAC_SECRET``, ``AUDIT_INTEGRITY_KEY`` and
   ``TOOL_ACCESS_SECRET`` only when missing; set ``REGENGINE_ENV=staging``,
   ``REGENGINE_REQUIRE_RLS_ENFORCEMENT=1`` and
   ``REGENGINE_MIGRATIONS_ROLE=regengine_migrator``; set
   ``REDIS_URL=${{Redis.REDIS_URL}}`` only when missing.
7. Print the checklist. Redeploy only when ``--redeploy`` is passed.

Every variable value travels over stdin to ``railway variable set NAME
--stdin --skip-deploys``; no value is placed in argv, printed, or written to
disk. The existing database (the one ``DATABASE_PUBLIC_URL`` names, usually
``railway``) is left untouched as an archive: the provider session only runs
cluster-wide role and database statements, and the script refuses to target
that database.

Re-running is safe: every step converges. Each ``--apply`` run rotates the
three database passwords and re-stores the matching URLs, so redeploy after
any re-run.

The script is stdlib-only and Python 3.9 compatible so it runs on a stock
macOS ``python3``. Every Railway CLI call goes through :func:`railway`, so a
rehearsal can put a fake ``railway`` executable first on ``PATH``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

DEFAULT_PROJECT_ID = "4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51"  # RegEngine-Prod project (an identifier, not a secret)
REQUIRED_ENVIRONMENT = "staging"
DEFAULT_DATABASE = "regengine_staging"

APP_SERVICE = "RegEngine"
POSTGRES_SERVICE = "Postgres"
REDIS_SERVICE = "Redis"

MIGRATOR_ROLE = "regengine_migrator"
RUNTIME_ROLE = "regengine"
ADMIN_ROLE = "regengine_sysadmin"
ALL_ROLES = (RUNTIME_ROLE, ADMIN_ROLE, MIGRATOR_ROLE)

# Variable name -> login role encoded in its URL.
ROLE_URL_VARIABLES: Tuple[Tuple[str, str], ...] = (
    ("MIGRATIONS_DATABASE_URL", MIGRATOR_ROLE),
    ("DATABASE_URL", RUNTIME_ROLE),
    ("ADMIN_DATABASE_URL", ADMIN_ROLE),
)
# Generated only when missing: rotating these later breaks stored email
# fingerprints / audit HMAC continuity, so an existing value is always kept.
GENERATED_IF_MISSING: Tuple[Tuple[str, int], ...] = (
    ("AUTH_OTP_HMAC_SECRET", 48),  # v094 + boot fingerprint repair; >= 32 bytes
    ("AUDIT_INTEGRITY_KEY", 48),  # audit HMAC chain key
    ("TOOL_ACCESS_SECRET", 64),  # must differ from AUTH_SECRET_KEY
)
LITERALS_ALWAYS: Tuple[Tuple[str, str], ...] = (
    ("REGENGINE_ENV", "staging"),
    ("REGENGINE_REQUIRE_RLS_ENFORCEMENT", "1"),
    ("REGENGINE_MIGRATIONS_ROLE", MIGRATOR_ROLE),
)
# Railway reference syntax, resolved by Railway at deploy time.
PGHOST_REF = "${{" + POSTGRES_SERVICE + ".PGHOST}}"
PGPORT_REF = "${{" + POSTGRES_SERVICE + ".PGPORT}}"
REDIS_URL_REF = "${{" + REDIS_SERVICE + ".REDIS_URL}}"
LITERALS_IF_MISSING: Tuple[Tuple[str, str], ...] = (("REDIS_URL", REDIS_URL_REF),)
SECRET_VARIABLES_TO_SEAL = tuple(name for name, _ in ROLE_URL_VARIABLES) + tuple(
    name for name, _ in GENERATED_IF_MISSING
)

# Databases this script must never create, adopt, or point the app at.
FORBIDDEN_DATABASES = frozenset({"postgres", "railway", "template0", "template1"})
_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")

PROVIDER_SENTINEL = "bootstrap-provider-sql-complete"
INVENTORY_SENTINEL = "bootstrap-inventory-complete"
MIGRATOR_SENTINEL = "bootstrap-migrator-sql-complete"
STDIN_PROBE = "regengine-bootstrap-stdin-probe"
COMMAND_TIMEOUT_S = 300

EXIT_REFUSED = 2
EXIT_FAILED = 1


class BootstrapError(RuntimeError):
    """A step failed; the message never contains a secret."""


class Refused(ValueError):
    """The requested target is not allowed; nothing was contacted."""


# ---------------------------------------------------------------------------
# Secret bookkeeping: everything generated is registered so any subprocess
# output that is shown to the operator can be redacted first.
# ---------------------------------------------------------------------------
_REGISTERED_SECRETS: List[str] = []


def _register_secret(value: str) -> str:
    if value:
        _REGISTERED_SECRETS.append(value)
    return value


def redact(text: str) -> str:
    for value in _REGISTERED_SECRETS:
        text = text.replace(value, "<redacted>")
    return text


def generate_password() -> str:
    # Hex keeps the value URL-safe inside postgresql:// URLs.
    return _register_secret(secrets.token_hex(32))


def generate_secret(nbytes: int) -> str:
    return _register_secret(secrets.token_urlsafe(nbytes))


def scram_sha256_verifier(password: str, *, salt: Optional[bytes] = None, iterations: int = 4096) -> str:
    """Return a PostgreSQL SCRAM-SHA-256 verifier (RFC 5802 / RFC 7677).

    ``ALTER ROLE ... PASSWORD '<verifier>'`` stores it as-is, so the plaintext
    never reaches the server or its logs (a failed statement is logged with
    its text by default).
    """
    salt = salt if salt is not None else secrets.token_bytes(16)
    salted = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    client_key = hmac.new(salted, b"Client Key", hashlib.sha256).digest()
    stored_key = hashlib.sha256(client_key).digest()
    server_key = hmac.new(salted, b"Server Key", hashlib.sha256).digest()

    def b64(raw: bytes) -> str:
        return base64.b64encode(raw).decode("ascii")

    return _register_secret(f"SCRAM-SHA-256${iterations}:{b64(salt)}${b64(stored_key)}:{b64(server_key)}")


# ---------------------------------------------------------------------------
# The single Railway CLI seam.
# ---------------------------------------------------------------------------
def railway_bin() -> str:
    return os.environ.get("RAILWAY_BIN", "railway")


def railway(args: Sequence[str], *, stdin: str = "") -> subprocess.CompletedProcess:
    """Run the Railway CLI. This is the ONLY place the script invokes it.

    ``stdin`` defaults to empty so a CLI prompt fails fast instead of hanging.
    Output is captured; callers decide what (redacted) text to show.
    """
    return subprocess.run(
        [railway_bin(), *args],
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        timeout=COMMAND_TIMEOUT_S,
    )


@dataclass
class Context:
    project: str
    environment: str
    database: str
    apply: bool
    redeploy: bool
    run_flags: List[str] = field(default_factory=list)  # e.g. ["--no-local"]
    psql: str = "psql"
    endpoint: Dict[str, object] = field(default_factory=dict)

    @property
    def scope(self) -> List[str]:
        return ["-p", self.project, "-e", self.environment]


def _fail_command(what: str, result: subprocess.CompletedProcess) -> BootstrapError:
    detail = redact((result.stderr or "").strip() or (result.stdout or "").strip())
    if len(detail) > 2000:
        detail = detail[-2000:]
    return BootstrapError(f"{what} failed (exit {result.returncode}): {detail or '<no output>'}")


def railway_run(ctx: Context, service: str, command: Sequence[str], *, stdin: str = "") -> subprocess.CompletedProcess:
    return railway(["run", *ctx.scope, "-s", service, *ctx.run_flags, "--", *command], stdin=stdin)


def provider_psql(ctx: Context, sql: str, sentinel: str, what: str) -> List[List[str]]:
    """Run SQL as the Postgres template superuser inside ``railway run``.

    The superuser URL only ever exists in the child's environment; the SQL
    travels over stdin. A missing sentinel means psql did not receive the
    whole script (for example stdin was not forwarded), which is fatal.
    """
    shell = (
        "PGAPPNAME=regengine-staging-bootstrap PGCONNECT_TIMEOUT=15; export PGAPPNAME PGCONNECT_TIMEOUT; "
        'exec "$1" "$DATABASE_PUBLIC_URL" -X -q -v ON_ERROR_STOP=1 -At -F "|" -f -'
    )
    result = railway_run(ctx, POSTGRES_SERVICE, ["sh", "-c", shell, "sh", ctx.psql], stdin=sql)
    if result.returncode != 0:
        raise _fail_command(what, result)
    rows = _rows(result.stdout)
    if [sentinel] not in rows:
        raise BootstrapError(f"{what}: psql did not finish the script (sentinel missing); nothing further was run")
    _show_notices(result.stderr)
    return rows


def role_psql(ctx: Context, role: str, password: str, sql: str, sentinel: str, what: str) -> List[List[str]]:
    """Log in as ``role`` to the new database over the public TCP proxy.

    The password is handed to psql through PGPASSWORD in the child's
    environment only; the conninfo in argv carries no secret.
    """
    endpoint = ctx.endpoint
    conninfo = (
        f"host={endpoint['host']} port={endpoint['port']} dbname={ctx.database} user={role} "
        "connect_timeout=15 application_name=regengine-staging-bootstrap"
    )
    if endpoint.get("sslmode"):
        conninfo += f" sslmode={endpoint['sslmode']}"
    env = {k: v for k, v in os.environ.items() if not k.startswith("PG")}
    env["PGPASSWORD"] = password
    result = subprocess.run(
        [ctx.psql, conninfo, "-X", "-q", "-v", "ON_ERROR_STOP=1", "-At", "-F", "|", "-f", "-"],
        input=sql,
        text=True,
        capture_output=True,
        env=env,
        check=False,
        timeout=COMMAND_TIMEOUT_S,
    )
    if result.returncode != 0:
        raise _fail_command(what, result)
    rows = _rows(result.stdout)
    if [sentinel] not in rows:
        raise BootstrapError(f"{what}: psql did not finish the script (sentinel missing)")
    _show_notices(result.stderr)
    return rows


def _rows(stdout: str) -> List[List[str]]:
    return [line.split("|") for line in (stdout or "").splitlines() if line.strip()]


def _show_notices(stderr: str) -> None:
    for line in (stderr or "").splitlines():
        if "NOTICE:" in line:
            print(f"    {redact(line.strip())}")


# ---------------------------------------------------------------------------
# SQL builders. Role and database names are validated identifiers.
# ---------------------------------------------------------------------------
def _roles_array() -> str:
    return "ARRAY[" + ", ".join(f"'{role}'" for role in ALL_ROLES) + "]"


def inventory_sql(database: str) -> str:
    return f"""
SELECT 'whoami', current_user, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)::text,
       current_database(), current_setting('server_version_num');
SELECT 'role', rolname, rolcanlogin::text, rolsuper::text, rolbypassrls::text, rolcreatedb::text,
       rolcreaterole::text, rolreplication::text
  FROM pg_roles WHERE rolname = ANY ({_roles_array()}) ORDER BY rolname;
SELECT 'database', datname, pg_get_userbyid(datdba) FROM pg_database WHERE datname = '{database}';
SELECT 'membership', granted.rolname, member.rolname
  FROM pg_auth_members AS m
  JOIN pg_roles AS granted ON granted.oid = m.roleid
  JOIN pg_roles AS member ON member.oid = m.member
 WHERE granted.rolname = ANY ({_roles_array()}) OR member.rolname = ANY ({_roles_array()})
 ORDER BY 2, 3;
SELECT '{INVENTORY_SENTINEL}';
"""


def provider_sql(database: str, verifiers: Mapping[str, str]) -> str:
    """Cluster-wide provisioning; runs connected to the archive DB but never touches its objects."""
    password_lines = "\n".join(
        f"ALTER ROLE {role} PASSWORD '{verifiers[role]}';" for role in ALL_ROLES if role in verifiers
    )
    return f"""
DO $bootstrap_guard$
BEGIN
    IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
        RAISE EXCEPTION 'provider credential % is not a superuser; cannot provision roles', current_user;
    END IF;
    IF current_database() = '{database}' THEN
        RAISE EXCEPTION 'refusing: the provider URL already points at target database %', current_database();
    END IF;
END
$bootstrap_guard$;

BEGIN;
DO $bootstrap_roles$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY {_roles_array()} LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format(
                'CREATE ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
                role_name);
            RAISE NOTICE 'created role %', role_name;
        ELSE
            EXECUTE format(
                'ALTER ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION',
                role_name);
            RAISE NOTICE 'pinned attributes on existing role %', role_name;
        END IF;
    END LOOP;
END
$bootstrap_roles$;

-- v111 rejects any incoming or outgoing membership on these roles.
DO $bootstrap_memberships$
DECLARE
    m record;
BEGIN
    FOR m IN
        SELECT granted.rolname AS granted_name, member.rolname AS member_name, grantor.rolname AS grantor_name
          FROM pg_auth_members AS am
          JOIN pg_roles AS granted ON granted.oid = am.roleid
          JOIN pg_roles AS member ON member.oid = am.member
          JOIN pg_roles AS grantor ON grantor.oid = am.grantor
         WHERE granted.rolname = ANY ({_roles_array()}) OR member.rolname = ANY ({_roles_array()})
    LOOP
        EXECUTE format('REVOKE %I FROM %I GRANTED BY %I', m.granted_name, m.member_name, m.grantor_name);
        RAISE NOTICE 'revoked membership: % from %', m.granted_name, m.member_name;
    END LOOP;
END
$bootstrap_memberships$;

{password_lines}
COMMIT;

SELECT format('CREATE DATABASE %I OWNER %I TEMPLATE template0', '{database}', '{MIGRATOR_ROLE}')
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '{database}')\\gexec

DO $bootstrap_database$
DECLARE
    owner_name text;
BEGIN
    SELECT pg_get_userbyid(datdba) INTO owner_name FROM pg_database WHERE datname = '{database}';
    IF owner_name IS DISTINCT FROM '{MIGRATOR_ROLE}' THEN
        RAISE EXCEPTION 'database {database} exists but is owned by %; refusing to adopt it', owner_name;
    END IF;
END
$bootstrap_database$;

GRANT CONNECT ON DATABASE {database} TO {RUNTIME_ROLE}, {ADMIN_ROLE}, {MIGRATOR_ROLE};
-- Scoped to the new database only. CI runs every migration job with
-- PGOPTIONS "-c timezone=UTC -c search_path=public,fsma,extensions"; Railway
-- has no PGOPTIONS, so pin the same session defaults on the migrator here.
ALTER ROLE {MIGRATOR_ROLE} IN DATABASE {database} SET search_path = public, fsma, extensions;
ALTER ROLE {MIGRATOR_ROLE} IN DATABASE {database} SET timezone = 'UTC';

DO $bootstrap_verify$
DECLARE
    bad record;
BEGIN
    SELECT rolname INTO bad
      FROM pg_roles
     WHERE rolname = ANY ({_roles_array()})
       AND (NOT rolcanlogin OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication)
     LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'role % still has a forbidden attribute', bad.rolname;
    END IF;
    IF (SELECT count(*) FROM pg_roles WHERE rolname = ANY ({_roles_array()})) <> 3 THEN
        RAISE EXCEPTION 'not all three RegEngine roles exist';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_auth_members AS am
          JOIN pg_roles AS granted ON granted.oid = am.roleid
          JOIN pg_roles AS member ON member.oid = am.member
         WHERE granted.rolname = ANY ({_roles_array()}) OR member.rolname = ANY ({_roles_array()})
    ) THEN
        RAISE EXCEPTION 'a role membership involving the RegEngine roles remains';
    END IF;
END
$bootstrap_verify$;

SELECT '{PROVIDER_SENTINEL}';
"""


# Byte-for-byte the function body backend-ci.yml's live-db-suite (and
# scripts/init-postgres.sh) seed before a fresh ``alembic upgrade head``:
# baseline RLS policies reference it but no migration creates it; v097 later
# re-pins the same fail-hard STABLE body. Created while logged in as the
# migration owner so no provider-owned function hides in a protected schema.
# tests/scripts/test_bootstrap_staging_database.py pins this against the CI copy.
GET_TENANT_CONTEXT_SQL = """CREATE OR REPLACE FUNCTION public.get_tenant_context()
RETURNS UUID AS $fn$
DECLARE
    tid TEXT;
BEGIN
    tid := NULLIF(current_setting('app.tenant_id', TRUE), '');
    IF tid IS NULL THEN
        RAISE EXCEPTION 'app.tenant_id not set - tenant context required for RLS';
    END IF;
    RETURN tid::UUID;
END;
$fn$ LANGUAGE plpgsql STABLE;"""


def migrator_sql() -> str:
    return f"""
SELECT 'identity', session_user, current_user, current_database(),
       current_setting('search_path'), current_setting('TimeZone');
SELECT to_regprocedure('public.get_tenant_context()') IS NULL AS need_seed \\gset
\\if :need_seed
{GET_TENANT_CONTEXT_SQL}
SELECT 'seed', 'created';
\\else
SELECT 'seed', 'already-present';
\\endif
SELECT 'function-owner', pg_get_userbyid(proowner) FROM pg_proc
 WHERE oid = to_regprocedure('public.get_tenant_context()');
SELECT to_regclass('public.alembic_version') IS NOT NULL AS has_alembic \\gset
\\if :has_alembic
SELECT 'alembic', coalesce((SELECT string_agg(version_num, ',') FROM public.alembic_version), '');
\\else
SELECT 'alembic', '';
\\endif
SELECT 'fsma-tables', EXISTS (
    SELECT 1 FROM pg_class AS c JOIN pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname = 'fsma' AND c.relkind IN ('r', 'p'))::text;
SELECT '{MIGRATOR_SENTINEL}';
"""


def runtime_login_sql() -> str:
    return f"""
SELECT 'identity', session_user, current_user, current_database();
SELECT '{MIGRATOR_SENTINEL}';
"""


def database_url(role: str, password: str, database: str) -> str:
    """Private-network URL; Railway resolves the references at deploy time."""
    return f"postgresql://{role}:{password}@{PGHOST_REF}:{PGPORT_REF}/{database}"


# ---------------------------------------------------------------------------
# Variable presence (names only; values are never printed).
# ---------------------------------------------------------------------------
def _load_json_payload(raw: str) -> object:
    """Parse CLI JSON output, tolerating banner lines (e.g. update notices) before it."""
    text = raw or ""
    try:
        return json.loads(text)
    except ValueError:
        pass
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("{", "[")):
            try:
                return json.loads("\n".join(lines[index:]))
            except ValueError:
                continue
    return None


def parse_variable_presence(raw_json: str) -> Dict[str, bool]:
    """Map variable NAME -> usable, from ``railway variable list --json``.

    Sealed variables come back with a null value: they are present and
    usable. An empty string counts as missing. Values are inspected only for
    emptiness and never returned or printed.
    """
    data = _load_json_payload(raw_json)
    if data is None:
        raise BootstrapError("could not parse `railway variable list --json` output")
    presence: Dict[str, bool] = {}
    if isinstance(data, dict):
        items = data.items()
    elif isinstance(data, list):
        items = []
        for entry in data:
            if isinstance(entry, dict):
                name = entry.get("name", entry.get("key"))
                if isinstance(name, str):
                    items.append((name, entry.get("value")))
    else:
        raise BootstrapError("unexpected `railway variable list --json` shape")
    for name, value in items:
        presence[str(name)] = value is None or (isinstance(value, str) and value != "")
    return presence


def posture_warnings(raw_json: str) -> List[str]:
    """Warn about visible (unsealed) values that will fail boot; never prints values."""
    data = _load_json_payload(raw_json)
    if not isinstance(data, dict):
        return []
    warnings: List[str] = []
    otp = data.get("AUTH_OTP_HMAC_SECRET")
    if isinstance(otp, str) and otp and len(otp.encode("utf-8")) < 32:
        warnings.append("AUTH_OTP_HMAC_SECRET is shorter than 32 bytes; boot will fail. Replace it.")
    tool, auth = data.get("TOOL_ACCESS_SECRET"), data.get("AUTH_SECRET_KEY")
    if isinstance(tool, str) and tool and tool == auth:
        warnings.append("TOOL_ACCESS_SECRET equals AUTH_SECRET_KEY; it must differ. Replace it.")
    return warnings


def read_app_variables(ctx: Context) -> str:
    result = railway(["variable", "list", *ctx.scope, "-s", APP_SERVICE, "--json"])
    if result.returncode != 0:
        # stderr of a list call carries no values; still redact defensively.
        raise _fail_command(f"reading variable names of {APP_SERVICE}", result)
    return result.stdout


def set_variable(ctx: Context, name: str, value: str) -> None:
    """Store one variable. The value goes over stdin only, never argv."""
    result = railway(
        ["variable", "set", name, "--stdin", *ctx.scope, "-s", APP_SERVICE, "--skip-deploys"],
        stdin=value,
    )
    if result.returncode != 0:
        raise _fail_command(f"railway variable set {name}", result)


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------
def validate_target(environment: str, database: str) -> None:
    if environment.strip().lower() == "production":
        raise Refused(
            "REFUSED: this bootstrap never targets production. It rotates database passwords and "
            "repoints DATABASE_URL; production uses the reviewed runbook in docs/operations/DATABASE_ROLE_CUTOVER.md."
        )
    if environment != REQUIRED_ENVIRONMENT:
        raise Refused(f"REFUSED: environment must be exactly '{REQUIRED_ENVIRONMENT}' (got {environment!r}).")
    if not _IDENTIFIER.match(database) or database in FORBIDDEN_DATABASES:
        raise Refused(
            f"REFUSED: --database {database!r} must be a new lowercase identifier and not one of "
            f"{sorted(FORBIDDEN_DATABASES)}."
        )


def step(number: int, title: str) -> None:
    print(f"\n[{number}] {title}")


def preflight(ctx: Context) -> None:
    step(1, "Preflight (read-only)")
    if shutil.which(railway_bin()) is None:
        raise BootstrapError("Railway CLI not found on PATH (install: https://docs.railway.com/guides/cli)")
    psql = shutil.which(os.environ.get("PSQL", "psql"))
    if psql is None:
        raise BootstrapError("psql not found (macOS: brew install libpq, then add its bin/ to PATH or set PSQL)")
    ctx.psql = psql
    who = railway(["whoami"])
    if who.returncode != 0:
        raise BootstrapError("Railway CLI is not logged in; run `railway login` first")
    print("    railway CLI: logged in")
    run_help = railway(["run", "--help"])
    if "--no-local" in (run_help.stdout or ""):
        ctx.run_flags = ["--no-local"]  # never let `railway dev` overrides redirect the target
    probe_code = (
        "import json, os, sys, urllib.parse as u\n"
        "raw = os.environ.get('DATABASE_PUBLIC_URL', '')\n"
        f"out = {{'stdin_ok': sys.stdin.read() == {STDIN_PROBE!r},\n"
        "       'environment': os.environ.get('RAILWAY_ENVIRONMENT_NAME', ''),\n"
        "       'project': os.environ.get('RAILWAY_PROJECT_ID', '')}\n"
        "if raw:\n"
        "    p = u.urlsplit(raw)\n"
        "    q = u.parse_qs(p.query)\n"
        "    out.update(host=p.hostname or '', port=p.port or 5432, user=u.unquote(p.username or ''),\n"
        "               database=u.unquote(p.path.lstrip('/')), sslmode=(q.get('sslmode') or [''])[0])\n"
        "print(json.dumps(out))\n"
    )
    probe = railway_run(ctx, POSTGRES_SERVICE, [sys.executable, "-c", probe_code], stdin=STDIN_PROBE)
    if probe.returncode != 0:
        raise _fail_command(f"railway run -s {POSTGRES_SERVICE} probe", probe)
    try:
        info = json.loads(probe.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise BootstrapError("could not read the Postgres service probe output") from exc
    if not info.get("stdin_ok"):
        raise BootstrapError("`railway run` did not forward stdin to the child process; cannot send SQL safely")
    if info.get("environment") and info["environment"] != ctx.environment:
        raise BootstrapError(f"railway run resolved environment {info['environment']!r}, expected {ctx.environment!r}")
    if info.get("project") and info["project"] != ctx.project:
        raise BootstrapError("railway run resolved a different project than --project")
    if not info.get("host"):
        raise BootstrapError(
            f"{POSTGRES_SERVICE} has no DATABASE_PUBLIC_URL in {ctx.environment}; enable its TCP proxy first"
        )
    ctx.endpoint = info
    print(f"    stdin forwarding through `railway run`: ok{' (with --no-local)' if ctx.run_flags else ''}")
    print(f"    provider login: {info.get('user')} (public TCP proxy {info['host']}:{info['port']})")
    print(f"    existing database (archive, left untouched): {info.get('database')}")
    if info.get("database") == ctx.database:
        raise BootstrapError(
            f"DATABASE_PUBLIC_URL already names {ctx.database!r}; refusing to treat the archive database as the target"
        )

    rows = provider_psql(ctx, inventory_sql(ctx.database), INVENTORY_SENTINEL, "read-only inventory")
    for row in rows:
        tag = row[0]
        if tag == "whoami":
            print(f"    connected as {row[1]} (superuser={row[2]}) to {row[3]}, server_version_num={row[4]}")
            if row[2] != "true":
                raise BootstrapError("the Postgres service credential is not a superuser; cannot provision roles")
        elif tag == "role":
            print(
                f"    role {row[1]}: login={row[2]} super={row[3]} bypassrls={row[4]} createdb={row[5]} "
                f"createrole={row[6]} replication={row[7]}"
            )
        elif tag == "database":
            print(f"    target database {row[1]} exists, owner={row[2]}")
            if row[2] != MIGRATOR_ROLE:
                raise BootstrapError(f"database {row[1]} exists but is owned by {row[2]}; refusing to adopt it")
        elif tag == "membership":
            print(f"    membership {row[1]} -> {row[2]} (will be revoked)")
    if not any(row[0] == "database" for row in rows):
        print(f"    target database {ctx.database}: absent (will be created)")


def print_plan(ctx: Context, presence: Mapping[str, bool]) -> None:
    placeholder = {role: f"<scram-sha-256 verifier for a new random password: {role}>" for role in ALL_ROLES}
    step(2, f"Provision roles and database {ctx.database} as the {POSTGRES_SERVICE} template superuser")
    print(
        f"    via: railway run -p {ctx.project} -e {ctx.environment} -s {POSTGRES_SERVICE} -- psql $DATABASE_PUBLIC_URL"
    )
    print("    SQL (over stdin):")
    for line in provider_sql(ctx.database, placeholder).strip().splitlines():
        print(f"      {line}")
    step(3, f"Seed get_tenant_context() logged in as {MIGRATOR_ROLE} (only if absent)")
    for line in GET_TENANT_CONTEXT_SQL.splitlines():
        print(f"      {line}")
    step(4, f"Prove {RUNTIME_ROLE} and {ADMIN_ROLE} can log in to {ctx.database}")
    step(5, f"Store database URLs on {APP_SERVICE} (values over stdin, --skip-deploys)")
    for name, role in ROLE_URL_VARIABLES:
        shown = database_url(role, "<new password>", ctx.database)
        print(f"    {name} = {shown}")
    step(6, f"App secrets and settings on {APP_SERVICE}")
    for name, nbytes in GENERATED_IF_MISSING:
        action = "present: keep" if presence.get(name) else f"missing: generate token_urlsafe({nbytes})"
        print(f"    {name}: {action}")
    for name, value in LITERALS_ALWAYS:
        print(f"    {name} = {value} (always)")
    for name, value in LITERALS_IF_MISSING:
        action = "present: keep" if presence.get(name) else f"missing: set to {value}"
        print(f"    {name}: {action}")


def apply_database(ctx: Context) -> Dict[str, str]:
    passwords = {role: generate_password() for role in ALL_ROLES}
    verifiers = {role: scram_sha256_verifier(passwords[role]) for role in ALL_ROLES}

    step(2, f"Provision roles and database {ctx.database} as the {POSTGRES_SERVICE} template superuser")
    provider_psql(ctx, provider_sql(ctx.database, verifiers), PROVIDER_SENTINEL, "provider provisioning")
    print(f"    roles pinned, passwords rotated, database {ctx.database} owned by {MIGRATOR_ROLE}, CONNECT granted")

    step(3, f"Seed get_tenant_context() logged in as {MIGRATOR_ROLE}")
    rows = role_psql(ctx, MIGRATOR_ROLE, passwords[MIGRATOR_ROLE], migrator_sql(), MIGRATOR_SENTINEL, "migrator login")
    facts = {row[0]: row[1:] for row in rows}
    identity = facts.get("identity", [])
    if identity[:3] != [MIGRATOR_ROLE, MIGRATOR_ROLE, ctx.database]:
        raise BootstrapError(f"migrator login resolved to {identity[:3]!r}")
    print(f"    logged in as {identity[0]} to {identity[2]}; search_path={identity[3]}; timezone={identity[4]}")
    print(f"    get_tenant_context(): {facts.get('seed', ['?'])[0]} (owner {facts.get('function-owner', ['?'])[0]})")
    if facts.get("function-owner", [""])[0] != MIGRATOR_ROLE:
        raise BootstrapError("get_tenant_context() is not owned by the migration role; v111 would reject it")
    alembic_revision = facts.get("alembic", [""])[0]
    has_fsma = facts.get("fsma-tables", ["false"])[0] == "true"
    if alembic_revision:
        print(f"    migration state: ALREADY_MANAGED at {alembic_revision} (the deploy upgrades it to head)")
    elif has_fsma:
        raise BootstrapError(
            f"{ctx.database} has fsma tables but no alembic revision; run-migrations.sh would refuse (exit 65)"
        )
    else:
        print("    migration state: FRESH (the deploy runs the full chain)")

    step(4, f"Prove {RUNTIME_ROLE} and {ADMIN_ROLE} can log in to {ctx.database}")
    for role in (RUNTIME_ROLE, ADMIN_ROLE):
        rows = role_psql(ctx, role, passwords[role], runtime_login_sql(), MIGRATOR_SENTINEL, f"{role} login")
        identity = next((row[1:] for row in rows if row[0] == "identity"), [])
        if identity[:3] != [role, role, ctx.database]:
            raise BootstrapError(f"{role} login resolved to {identity[:3]!r}")
        print(f"    {role}: login ok")
    return passwords


def apply_variables(ctx: Context, passwords: Mapping[str, str], presence: Mapping[str, bool]) -> None:
    step(5, f"Store database URLs on {APP_SERVICE} (values over stdin, --skip-deploys)")
    for name, role in ROLE_URL_VARIABLES:
        set_variable(ctx, name, database_url(role, passwords[role], ctx.database))
        print(f"    {name}: set (role {role}, database {ctx.database}, host {PGHOST_REF})")

    step(6, f"App secrets and settings on {APP_SERVICE}")
    for name, nbytes in GENERATED_IF_MISSING:
        if presence.get(name):
            print(f"    {name}: present, kept")
            continue
        set_variable(ctx, name, generate_secret(nbytes))
        print(f"    {name}: generated and stored (value not displayed)")
    for name, value in LITERALS_ALWAYS:
        set_variable(ctx, name, value)
        print(f"    {name} = {value}")
    for name, value in LITERALS_IF_MISSING:
        if presence.get(name):
            print(f"    {name}: present, kept")
            continue
        set_variable(ctx, name, value)
        print(f"    {name} = {value}")

    after = parse_variable_presence(read_app_variables(ctx))
    required = [name for name, _ in ROLE_URL_VARIABLES] + [name for name, _ in GENERATED_IF_MISSING]
    required += [name for name, _ in LITERALS_ALWAYS] + [name for name, _ in LITERALS_IF_MISSING]
    missing = [name for name in required if not after.get(name)]
    if missing:
        raise BootstrapError(f"read-back is missing variables: {', '.join(missing)}")
    print(f"    read-back by name: all {len(required)} required variables present")


def redeploy_command(ctx: Context) -> str:
    return f"railway redeploy -p {ctx.project} -e {ctx.environment} -s {APP_SERVICE} --yes"


def print_checklist(ctx: Context, *, applied: bool) -> None:
    print("\nNext steps")
    archive = ctx.endpoint.get("database") or "the existing database"
    if ctx.redeploy:
        deploy = "Redeploy requested. If the dashboard still shows staged variable changes, Deploy them."
    else:
        deploy = "Deploy once: " + redeploy_command(ctx) + "  (or Deploy the staged changes in the dashboard)"
    lines = [
        f"Old database '{archive}' is left untouched as an archive; the new URLs point at '{ctx.database}'.",
        "In the Railway dashboard (staging -> RegEngine -> Variables) Seal: " + ", ".join(SECRET_VARIABLES_TO_SEAL),
        deploy,
        "Expect in the deploy log: 'DB state: FRESH' (ALREADY_MANAGED after a previous deploy), Alembic "
        "upgrades ending at the current head, "
        f"'runtime role cutover applied as role={MIGRATOR_ROLE} database={ctx.database}', then gunicorn boot.",
        "Verify: GET /readiness returns 200 with postgres ok and redis ok (neo4j may only mark it degraded).",
        "Re-running --apply is safe but rotates the three DB passwords; redeploy after any re-run.",
    ]
    if not applied:
        lines.insert(0, "DRY RUN: nothing was changed. Re-run with --apply to execute steps 2-6.")
    for line in lines:
        print(f"    - {line}")


def parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap a FRESH RegEngine staging database on Railway (dry-run by default).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print every step without changing anything (default)")
    mode.add_argument("--apply", action="store_true", help="execute the steps")
    parser.add_argument("--redeploy", action="store_true", help="with --apply: redeploy RegEngine afterwards")
    parser.add_argument("--environment", default=REQUIRED_ENVIRONMENT, help="must be exactly 'staging'")
    parser.add_argument("--project", default=DEFAULT_PROJECT_ID, help="Railway project ID (default: RegEngine-Prod)")
    parser.add_argument("--database", default=DEFAULT_DATABASE, help=f"new database name (default {DEFAULT_DATABASE})")
    args = parser.parse_args(argv)
    if args.redeploy and not args.apply:
        parser.error("--redeploy requires --apply")
    return args


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        validate_target(args.environment, args.database)
    except Refused as refusal:
        print(str(refusal), file=sys.stderr)
        return EXIT_REFUSED
    ctx = Context(
        project=args.project,
        environment=args.environment,
        database=args.database,
        apply=bool(args.apply),
        redeploy=bool(args.redeploy),
    )
    mode = "APPLY" if ctx.apply else "DRY RUN"
    print(f"RegEngine staging database bootstrap [{mode}] project={ctx.project} environment={ctx.environment}")
    try:
        preflight(ctx)
        raw_variables = read_app_variables(ctx)
        presence = parse_variable_presence(raw_variables)
        for warning in posture_warnings(raw_variables):
            print(f"    WARNING: {warning}")
        del raw_variables
        if not ctx.apply:
            print_plan(ctx, presence)
            print_checklist(ctx, applied=False)
            return 0
        passwords = apply_database(ctx)
        apply_variables(ctx, passwords, presence)
        if ctx.redeploy:
            step(7, f"Redeploy {APP_SERVICE}")
            result = railway(["redeploy", *ctx.scope, "-s", APP_SERVICE, "--yes"])
            if result.returncode != 0:
                raise _fail_command("railway redeploy", result)
            print("    redeploy requested; watch the deploy log for the lines in the checklist")
        print_checklist(ctx, applied=True)
        return 0
    except BootstrapError as exc:
        print(f"\nFAILED: {redact(str(exc))}", file=sys.stderr)
        print("Every step is idempotent: fix the cause and re-run the same command.", file=sys.stderr)
        return EXIT_FAILED
    except subprocess.TimeoutExpired as exc:
        print(f"\nFAILED: command timed out after {exc.timeout}s; re-run when the network is healthy.", file=sys.stderr)
        return EXIT_FAILED


if __name__ == "__main__":
    raise SystemExit(main())
