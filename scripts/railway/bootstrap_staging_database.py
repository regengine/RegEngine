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
1. Read-only preflight. It refuses a Railway CLI older than 5.47.2, which
   hides sealed variables. It proves that ``railway run`` forwards stdin and
   resolves exactly this project and environment. It checks that the Postgres
   service's ``DATABASE_PUBLIC_URL`` is that service's own TCP proxy. It then
   takes a read-only inventory of the three roles, the target database, and
   any use of a pre-existing role outside the target database. For a role it
   would keep, it tests the stored password by logging in before anything is
   written.
2. As the Railway Postgres template superuser: create or pin
   ``regengine``, ``regengine_sysadmin`` and ``regengine_migrator`` (LOGIN
   NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION, VALID
   UNTIL infinity, no connection limit, no role-level settings), revoke
   memberships involving them, and mark each with a ``COMMENT ON ROLE``. A
   pre-existing role is only changed with ``--adopt-existing-roles`` when it
   is used outside the target database (owned objects, privileges, sessions,
   settings, memberships) or has elevated attributes, or when this bootstrap
   did not create it and its URL variable does not already point at
   role@target on the staging private endpoint. Then
   ``CREATE DATABASE <db> OWNER regengine_migrator TEMPLATE template0`` if it
   is absent, ``REVOKE ALL ... FROM PUBLIC`` plus explicit ``CONNECT`` grants,
   and the migrator's ``search_path``/``timezone`` inside that database only.
   The superuser URL is used only inside the process that ``railway run``
   starts. A small launcher there turns it into libpq environment variables
   (PGPASSWORD, PGSSLMODE=require, PGCHANNELBINDING=require) and execs psql.
   The URL and password never appear in any command line, in the output, or in
   a file, and this script's own process never holds them.
   Every psql connection requires TLS and SCRAM-SHA-256 with channel binding
   (SCRAM-SHA-256-PLUS over tls-server-end-point). That is what protects the
   passwords on the wire: psql refuses cleartext, MD5, or unbound SCRAM
   authentication. An interceptor presenting its own certificate therefore
   gets no password and cannot relay the login. Railway's proxy certificate is
   self-signed, so the certificate itself is not CA-verified. The preflight
   refuses psql older than 13, because older libpq silently ignores
   PGCHANNELBINDING. Every psql child gets a private empty HOME, so a personal
   ~/.postgresql/root.crt cannot turn sslmode=require into CA verification,
   which would fail against that self-signed certificate.
3. Log in AS ``regengine_migrator`` and create ``get_tenant_context()``
   exactly as the backend-ci live-db-suite does for a fresh chain (only if it
   is absent).
4. Log in as ``regengine`` and ``regengine_sysadmin`` to prove each password.
5. Write the RegEngine variables. ``MIGRATIONS_DATABASE_URL`` is written LAST.
   Railway CLI writes take effect immediately (they are not staged) and
   staging deploys on every push, so a deploy can start before the run
   completes. Such a deploy stops at run-migrations.sh and gunicorn never
   starts. On a first run it exits 64 because ``MIGRATIONS_DATABASE_URL`` is
   still unset. On a ``--rotate-passwords`` re-run the variable still holds
   the old password, so the migration login fails password authentication.
   The order is:
   ``DATABASE_URL``, ``ADMIN_DATABASE_URL``, then ``AUTH_OTP_HMAC_SECRET``,
   ``AUDIT_INTEGRITY_KEY`` and ``TOOL_ACCESS_SECRET`` (each only when
   missing), then ``REGENGINE_ENV=staging``,
   ``REGENGINE_REQUIRE_RLS_ENFORCEMENT=1``,
   ``REGENGINE_MIGRATIONS_ROLE=regengine_migrator``, then
   ``REDIS_URL=${{Redis.REDIS_URL}}`` only when missing, and finally
   ``MIGRATIONS_DATABASE_URL``. The database URLs use the private
   ``${{Postgres.PGHOST}}``/``${{Postgres.PGPORT}}`` references.
6. Print the checklist. Redeploy only when ``--redeploy`` is passed.

Passwords are set only for roles this run creates, or for every role with
``--rotate-passwords``. An existing role keeps its password when its URL
variable is readable, names that role and the target database on the staging
private endpoint, and logs in (tested before any write). Otherwise, including
when the URL variable is sealed or its password no longer logs in, the run
refuses (exit 2) until ``--rotate-passwords`` is given. After any rotation,
redeploy.

Every value travels over stdin to ``railway variable set NAME --stdin
--skip-deploys``. ``--skip-deploys`` only stops the CLI from starting a
deploy; the values are live at once. Presence checks read the raw variable
values into memory: names are printed, values never are. The existing
database named by ``DATABASE_PUBLIC_URL`` (usually ``railway``) is left
untouched as an archive.

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
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Set, Tuple
from urllib.parse import unquote, urlsplit

DEFAULT_PROJECT_ID = "4e1d16d9-0d88-4b88-8eb9-5c0ae38e2b51"  # RegEngine-Prod project (an identifier, not a secret)
REQUIRED_ENVIRONMENT = "staging"
DEFAULT_DATABASE = "regengine_staging"
DATABASE_NAME = re.compile(r"regengine_[a-z0-9_]{1,53}")  # always used with fullmatch()

# COMMENT ON ROLE marker for roles this bootstrap created (or the operator
# adopted with --adopt-existing-roles). Any other pre-existing role is foreign.
MANAGED_ROLE_PREFIX = "regengine-staging-bootstrap:"
MANAGED_ROLE_COMMENT = MANAGED_ROLE_PREFIX + " created or adopted by scripts/railway/bootstrap_staging_database.py"

# Older CLIs omit sealed variables from `variable list --json`; the presence
# check would then regenerate sealed secrets and rotate passwords.
MIN_CLI_VERSION = (5, 47, 2)
MIN_SERVER_VERSION_NUM = 150000  # pg_database_owner-owned public schema, as v111 expects
MIN_LIBPQ_MAJOR = 13  # first libpq that honours channel_binding / PGCHANNELBINDING

APP_SERVICE = "RegEngine"
POSTGRES_SERVICE = "Postgres"
REDIS_SERVICE = "Redis"

MIGRATOR_ROLE = "regengine_migrator"
RUNTIME_ROLE = "regengine"
ADMIN_ROLE = "regengine_sysadmin"
ALL_ROLES = (RUNTIME_ROLE, ADMIN_ROLE, MIGRATOR_ROLE)

# Railway reference syntax, resolved by Railway at deploy time.
PGHOST_REF = "${{" + POSTGRES_SERVICE + ".PGHOST}}"
PGPORT_REF = "${{" + POSTGRES_SERVICE + ".PGPORT}}"
REDIS_URL_REF = "${{" + REDIS_SERVICE + ".REDIS_URL}}"

ROLE_URL_VARIABLES: Tuple[Tuple[str, str], ...] = (
    ("DATABASE_URL", RUNTIME_ROLE),
    ("ADMIN_DATABASE_URL", ADMIN_ROLE),
    ("MIGRATIONS_DATABASE_URL", MIGRATOR_ROLE),  # written last, see apply_variables()
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
LITERALS_IF_MISSING: Tuple[Tuple[str, str], ...] = (("REDIS_URL", REDIS_URL_REF),)
SECRET_VARIABLES_TO_SEAL = ("MIGRATIONS_DATABASE_URL", "DATABASE_URL", "ADMIN_DATABASE_URL") + tuple(
    name for name, _ in GENERATED_IF_MISSING
)

PROVIDER_SENTINEL = "bootstrap-provider-sql-complete"
INVENTORY_SENTINEL = "bootstrap-inventory-complete"
LOGIN_SENTINEL = "bootstrap-login-sql-complete"
STDIN_PROBE = "regengine-bootstrap-stdin-probe"
COMMAND_TIMEOUT_S = 300
PSQL_FLAGS = ("-X", "-q", "-v", "ON_ERROR_STOP=1", "-At", "-F", "|", "-f", "-")
_CHILD_ENV_KEEP = ("PATH", "HOME", "LANG", "TMPDIR", "TZ", "SYSTEMROOT")
# After a local timeout kill, the server notices the dead client within ~2 s
# even mid-statement and rolls the open transaction back (PostgreSQL 14+).
SERVER_OPTIONS = "-c client_connection_check_interval=2000"

EXIT_REFUSED = 2
EXIT_FAILED = 1


class BootstrapError(RuntimeError):
    """A step failed; the message never contains a secret."""


class Refused(ValueError):
    """A safety guard refused the run before anything was written."""


# ---------------------------------------------------------------------------
# Secret bookkeeping: every secret the script holds is registered so any
# subprocess output shown to the operator can be redacted first.
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


def quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def quote_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


# ---------------------------------------------------------------------------
# Process execution: each child gets its own process group so a timeout or
# Ctrl-C also kills psql running underneath `railway run`.
# ---------------------------------------------------------------------------
def run_process(cmd: Sequence[str], *, stdin: str = "", env: Optional[Mapping[str, str]] = None):
    proc = subprocess.Popen(
        list(cmd),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(env) if env is not None else None,
        start_new_session=True,
    )
    try:
        stdout, stderr = proc.communicate(stdin, timeout=COMMAND_TIMEOUT_S)
    except BaseException:
        _kill_process_group(proc)
        raise
    return subprocess.CompletedProcess(list(cmd), proc.returncode, stdout, stderr)


def _kill_process_group(proc: subprocess.Popen) -> None:
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    try:
        proc.communicate(timeout=5)
    except (subprocess.TimeoutExpired, ValueError, OSError):
        pass


def _child_base_env() -> Dict[str, str]:
    """Minimal environment for psql: no inherited PG* or credential variables."""
    return {k: v for k, v in os.environ.items() if k in _CHILD_ENV_KEEP or k.startswith("LC_")}


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
    return run_process([railway_bin(), *args], stdin=stdin)


# Runs inside `railway run -s Postgres`: turns DATABASE_PUBLIC_URL into libpq
# environment variables and execs psql, so neither the URL nor the password
# is ever part of any argv. stdin (the SQL) passes straight through.
# argv: <isolated HOME> <psql> <psql flags...>
PSQL_LAUNCHER = f"""\
import os, sys, urllib.parse as u
p = u.urlsplit(os.environ["DATABASE_PUBLIC_URL"])
keep = {_CHILD_ENV_KEEP!r}
env = {{k: v for k, v in os.environ.items() if k in keep or k.startswith("LC_")}}
env.update(HOME=sys.argv[1],
           PGHOST=p.hostname or "", PGPORT=str(p.port or 5432), PGUSER=u.unquote(p.username or ""),
           PGPASSWORD=u.unquote(p.password or ""), PGDATABASE=u.unquote(p.path.lstrip("/")),
           PGSSLMODE="require", PGCHANNELBINDING="require",
           PGAPPNAME="regengine-staging-bootstrap", PGCONNECT_TIMEOUT="15",
           PGOPTIONS={SERVER_OPTIONS!r})
os.execve(sys.argv[2], sys.argv[2:], env)
"""

PROBE_CODE = f"""\
import json, os, sys, urllib.parse as u
out = {{"stdin_ok": sys.stdin.read() == {STDIN_PROBE!r},
       "environment": os.environ.get("RAILWAY_ENVIRONMENT_NAME", ""),
       "project": os.environ.get("RAILWAY_PROJECT_ID", ""),
       "proxy_domain": os.environ.get("RAILWAY_TCP_PROXY_DOMAIN", ""),
       "proxy_port": os.environ.get("RAILWAY_TCP_PROXY_PORT", ""),
       "pghost": os.environ.get("PGHOST", ""),
       "pgport": os.environ.get("PGPORT", "")}}
raw = os.environ.get("DATABASE_PUBLIC_URL", "")
if raw:
    try:
        p = u.urlsplit(raw)
        out.update(host=p.hostname or "", port=str(p.port or 5432), user=u.unquote(p.username or ""),
                   database=u.unquote(p.path.lstrip("/")))
    except ValueError:
        out["url_error"] = "DATABASE_PUBLIC_URL is not a parseable URL"
print(json.dumps(out))
"""


@dataclass
class Context:
    project: str
    environment: str
    database: str
    apply: bool
    redeploy: bool = False
    adopt_existing_roles: bool = False
    rotate_passwords: bool = False
    run_flags: List[str] = field(default_factory=list)  # e.g. ["--no-local"]
    psql: str = "psql"
    psql_home: str = ""  # private empty HOME for every psql child (no ~/.postgresql, no ~/.psqlrc)
    endpoint: Dict[str, str] = field(default_factory=dict)
    private_hosts: Set[Tuple[str, str]] = field(default_factory=set)  # accepted host:port in stored URLs
    target_exists: bool = False
    existing_roles: Set[str] = field(default_factory=set)
    managed_roles: Set[str] = field(default_factory=set)
    outside_usage: List[Tuple[str, str]] = field(default_factory=list)
    blocked_grants: List[Tuple[str, str, str]] = field(default_factory=list)  # (grantor, granted, member)
    password_plan: Dict[str, str] = field(default_factory=dict)  # role -> new | rotate | keep
    kept_passwords: Dict[str, str] = field(default_factory=dict)
    passwords_changed: bool = False
    migrations_url_written: bool = False
    rotate_hint: bool = False

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

    The SQL travels over stdin; the credential exists only in the launcher's
    and psql's environment. A missing sentinel means psql did not receive the
    whole script, which is fatal.
    """
    command = [sys.executable, "-c", PSQL_LAUNCHER, ctx.psql_home, ctx.psql, *PSQL_FLAGS]
    result = railway_run(ctx, POSTGRES_SERVICE, command, stdin=sql)
    if result.returncode != 0:
        raise _fail_command(what, result)
    rows = _rows(result.stdout)
    if [sentinel] not in rows:
        raise BootstrapError(f"{what}: psql did not finish the script (sentinel missing); nothing further was run")
    _show_notices(result.stderr)
    return rows


def role_psql(ctx: Context, role: str, password: str, sql: str, sentinel: str, what: str) -> List[List[str]]:
    """Log in as ``role`` to the target database over the public TCP proxy (TLS required).

    Connection details and the password go to psql through its environment;
    its argv carries only fixed flags.
    """
    env = _child_base_env()
    env.update(
        HOME=ctx.psql_home,
        PGHOST=ctx.endpoint["host"],
        PGPORT=str(ctx.endpoint["port"]),
        PGDATABASE=ctx.database,
        PGUSER=role,
        PGPASSWORD=password,
        PGSSLMODE="require",
        PGCHANNELBINDING="require",
        PGAPPNAME="regengine-staging-bootstrap",
        PGCONNECT_TIMEOUT="15",
        PGOPTIONS=SERVER_OPTIONS,
    )
    result = run_process([ctx.psql, *PSQL_FLAGS], stdin=sql, env=env)
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
# SQL builders. Every identifier goes through quote_ident / format('%I') and
# every value through quote_literal / format('%L').
# ---------------------------------------------------------------------------
def _roles_array() -> str:
    return "ARRAY[" + ", ".join(quote_literal(role) for role in ALL_ROLES) + "]::text[]"


def outside_usage_sql(database: str) -> str:
    """(role_name, detail) rows for any use of the RegEngine roles outside ``database``.

    Covers shared dependencies (owned objects, privileges, policies) in other
    databases or on shared objects, open sessions, per-database settings for
    other databases, and role memberships. Grants and objects inside the
    target database itself are expected and excluded.
    """
    roles = _roles_array()
    target = quote_literal(database)
    return f"""
SELECT role_name, format('%s %s object(s) in %s', verb, count(*), location) AS detail
  FROM (
    SELECT r.rolname::text AS role_name,
           CASE sd.deptype WHEN 'o' THEN 'owns' WHEN 'a' THEN 'holds privileges on'
                           WHEN 'r' THEN 'is named in policies on' WHEN 'i' THEN 'has initial privileges on'
                           ELSE 'depends on' END AS verb,
           CASE WHEN sd.classid = 'pg_database'::regclass
                THEN 'database ' || coalesce((SELECT datname FROM pg_database WHERE oid = sd.objid)::text, '?')
                WHEN sd.dbid = 0 THEN 'shared catalog ' || sd.classid::regclass::text
                ELSE 'database ' || coalesce(d.datname::text, sd.dbid::text) END AS location
      FROM pg_shdepend AS sd
      JOIN pg_roles AS r ON r.oid = sd.refobjid AND sd.refclassid = 'pg_authid'::regclass
      LEFT JOIN pg_database AS d ON d.oid = sd.dbid
     WHERE r.rolname = ANY ({roles})
       AND sd.dbid IS DISTINCT FROM (SELECT oid FROM pg_database WHERE datname = {target})
       AND NOT (sd.dbid = 0 AND sd.classid = 'pg_database'::regclass
                AND sd.objid IS NOT DISTINCT FROM (SELECT oid FROM pg_database WHERE datname = {target}))
  ) AS dependency
 GROUP BY role_name, verb, location
UNION ALL
SELECT usename::text, format('has %s open session(s) in %s', count(*), coalesce('database ' || datname, 'no database'))
  FROM pg_stat_activity
 WHERE usename = ANY ({roles}) AND datname IS DISTINCT FROM {target}
 GROUP BY usename, datname
UNION ALL
SELECT r.rolname::text, format('has settings pinned in database %s', d.datname)
  FROM pg_db_role_setting AS s
  JOIN pg_roles AS r ON r.oid = s.setrole
  JOIN pg_database AS d ON d.oid = s.setdatabase
 WHERE r.rolname = ANY ({roles}) AND d.datname IS DISTINCT FROM {target}
UNION ALL
SELECT member.rolname::text,
       format('is a member of role %s (granted by %s%s)', granted.rolname, grantor.rolname,
              CASE WHEN am.admin_option THEN ', WITH ADMIN OPTION' ELSE '' END)
  FROM pg_auth_members AS am
  JOIN pg_roles AS granted ON granted.oid = am.roleid
  JOIN pg_roles AS member ON member.oid = am.member
  JOIN pg_roles AS grantor ON grantor.oid = am.grantor
 WHERE member.rolname = ANY ({roles})
UNION ALL
SELECT granted.rolname::text,
       format('is granted to role %s (granted by %s%s)', member.rolname, grantor.rolname,
              CASE WHEN am.admin_option THEN ', WITH ADMIN OPTION' ELSE '' END)
  FROM pg_auth_members AS am
  JOIN pg_roles AS granted ON granted.oid = am.roleid
  JOIN pg_roles AS member ON member.oid = am.member
  JOIN pg_roles AS grantor ON grantor.oid = am.grantor
 WHERE granted.rolname = ANY ({roles}) AND NOT member.rolname = ANY ({roles})
UNION ALL
SELECT grantor.rolname::text,
       format('used its ADMIN OPTION to grant role %s to role %s', granted.rolname, member.rolname)
  FROM pg_auth_members AS am
  JOIN pg_roles AS granted ON granted.oid = am.roleid
  JOIN pg_roles AS member ON member.oid = am.member
  JOIN pg_roles AS grantor ON grantor.oid = am.grantor
 WHERE grantor.rolname = ANY ({roles}) AND NOT granted.rolname = ANY ({roles})
UNION ALL
SELECT rolname::text,
       format('has elevated attributes (%s)',
              concat_ws(', ', CASE WHEN rolsuper THEN 'SUPERUSER' END, CASE WHEN rolbypassrls THEN 'BYPASSRLS' END,
                        CASE WHEN rolcreaterole THEN 'CREATEROLE' END, CASE WHEN rolcreatedb THEN 'CREATEDB' END,
                        CASE WHEN rolreplication THEN 'REPLICATION' END))
  FROM pg_roles
 WHERE rolname = ANY ({roles}) AND (rolsuper OR rolbypassrls OR rolcreaterole OR rolcreatedb OR rolreplication)
"""


def blocked_grants_sql() -> str:
    """(grantor, granted, member) grants that --adopt-existing-roles cannot undo.

    A RegEngine role that is a member of a foreign role WITH ADMIN OPTION and
    used it to grant that foreign role to another foreign role: revoking the
    RegEngine role's membership would need CASCADE, which would reach a
    membership outside RegEngine. Those are refused, never cascaded.
    """
    roles = _roles_array()
    return f"""
SELECT grantor.rolname::text AS grantor_name, granted.rolname::text AS granted_name,
       member.rolname::text AS member_name
  FROM pg_auth_members AS am
  JOIN pg_roles AS granted ON granted.oid = am.roleid
  JOIN pg_roles AS member ON member.oid = am.member
  JOIN pg_roles AS grantor ON grantor.oid = am.grantor
 WHERE grantor.rolname = ANY ({roles})
   AND NOT granted.rolname = ANY ({roles})
   AND NOT member.rolname = ANY ({roles})
"""


def membership_sql() -> str:
    """Revoke every membership involving the RegEngine roles (v111 forbids them).

    * Incoming (a RegEngine role granted to someone): REVOKE ... CASCADE. Every
      dependent of such a grant is itself a membership in the same RegEngine
      role, so the cascade stays inside the scope the dry run listed.
    * Outgoing (a RegEngine role is a member of a foreign role): never CASCADE.
      If a RegEngine role used that membership's ADMIN OPTION to grant the
      foreign role to a foreign role, refuse. A dependent grant that is itself
      in scope is revoked first on a later pass.
    * Each row is re-checked just before its REVOKE, so a grant already removed
      by an earlier CASCADE is skipped: no WARNING and no false "revoked" line.
    """
    roles = _roles_array()
    scope = f"granted.rolname = ANY ({roles}) OR member.rolname = ANY ({roles})"
    return f"""
DO $bootstrap_memberships$
DECLARE
    m record;
    blocked text;
    before_count integer;
    pending integer;
    progressed boolean;
BEGIN
    SELECT string_agg(format('%s granted role %s to %s', b.grantor_name, b.granted_name, b.member_name), '; ')
      INTO blocked
      FROM ({blocked_grants_sql()}) AS b;
    IF blocked IS NOT NULL THEN
        RAISE EXCEPTION 'cannot revoke outgoing RegEngine memberships without cascading outside RegEngine (%); revoke those grants by hand after review, then re-run', blocked;
    END IF;
    SELECT count(*) INTO before_count
      FROM pg_auth_members AS am
      JOIN pg_roles AS granted ON granted.oid = am.roleid
      JOIN pg_roles AS member ON member.oid = am.member
     WHERE {scope};
    LOOP
        progressed := false;
        FOR m IN
            SELECT am.roleid, am.member, am.grantor, granted.rolname AS granted_name,
                   member.rolname AS member_name, grantor.rolname AS grantor_name,
                   granted.rolname = ANY ({roles}) AS incoming
              FROM pg_auth_members AS am
              JOIN pg_roles AS granted ON granted.oid = am.roleid
              JOIN pg_roles AS member ON member.oid = am.member
              JOIN pg_roles AS grantor ON grantor.oid = am.grantor
             WHERE {scope}
             ORDER BY granted.rolname, member.rolname, grantor.rolname
        LOOP
            CONTINUE WHEN NOT EXISTS (
                SELECT 1 FROM pg_auth_members
                 WHERE roleid = m.roleid AND member = m.member AND grantor = m.grantor);
            BEGIN
                IF m.incoming THEN
                    EXECUTE format('REVOKE %I FROM %I GRANTED BY %I CASCADE',
                                   m.granted_name, m.member_name, m.grantor_name);
                ELSE
                    EXECUTE format('REVOKE %I FROM %I GRANTED BY %I', m.granted_name, m.member_name, m.grantor_name);
                END IF;
                progressed := true;
                RAISE NOTICE 'revoked membership: % from % (granted by %)%', m.granted_name, m.member_name,
                    m.grantor_name, CASE WHEN m.incoming THEN ' with CASCADE' ELSE '' END;
            -- SQLSTATE 2BP01 ("dependent privileges exist"): an in-scope grant still
            -- depends on this one; it is revoked first and this one retried next pass.
            EXCEPTION WHEN dependent_objects_still_exist THEN
                NULL;
            END;
        END LOOP;
        SELECT count(*) INTO pending
          FROM pg_auth_members AS am
          JOIN pg_roles AS granted ON granted.oid = am.roleid
          JOIN pg_roles AS member ON member.oid = am.member
         WHERE {scope};
        EXIT WHEN pending = 0;
        IF NOT progressed THEN
            RAISE EXCEPTION '% RegEngine role membership(s) could not be revoked', pending;
        END IF;
    END LOOP;
    IF before_count > 0 THEN
        RAISE NOTICE 'memberships involving RegEngine roles removed: % (including any removed by CASCADE)', before_count;
    END IF;
END
$bootstrap_memberships$;
"""


def inventory_sql(database: str) -> str:
    return f"""
SELECT 'whoami', current_user, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)::text,
       current_database(), current_setting('server_version_num'),
       coalesce((SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid())::text, 'false');
SELECT 'role', rolname, rolcanlogin::text, rolsuper::text, rolbypassrls::text, rolcreatedb::text,
       rolcreaterole::text, rolreplication::text,
       starts_with(coalesce(shobj_description(oid, 'pg_authid'), ''), {quote_literal(MANAGED_ROLE_PREFIX)})::text
  FROM pg_roles WHERE rolname = ANY ({_roles_array()}) ORDER BY rolname;
SELECT 'database', datname, pg_get_userbyid(datdba) FROM pg_database WHERE datname = {quote_literal(database)};
SELECT 'outside', role_name, detail FROM ({outside_usage_sql(database)}) AS outside ORDER BY 2, 3;
SELECT 'target-sessions', count(*) FROM pg_stat_activity
 WHERE usename = ANY ({_roles_array()}) AND datname = {quote_literal(database)};
SELECT 'blocked-grant', grantor_name, granted_name, member_name FROM ({blocked_grants_sql()}) AS blocked ORDER BY 2, 3, 4;
SELECT {quote_literal(INVENTORY_SENTINEL)};
"""


def provider_sql(database: str, verifiers: Mapping[str, str], *, adopt_existing_roles: bool) -> str:
    """Cluster-wide provisioning; connected to the archive DB but never touching its objects."""
    db_ident = quote_ident(database)
    db_literal = quote_literal(database)
    roles = _roles_array()
    password_lines = "\n".join(
        f"ALTER ROLE {quote_ident(role)} PASSWORD {quote_literal(verifiers[role])};"
        for role in ALL_ROLES
        if role in verifiers
    )
    reset_lines = "\n".join(f"ALTER ROLE {quote_ident(role)} IN DATABASE {db_ident} RESET ALL;" for role in ALL_ROLES)
    grantees = ", ".join(quote_ident(role) for role in ALL_ROLES)
    migrator = quote_ident(MIGRATOR_ROLE)
    return f"""
DO $bootstrap_guard$
BEGIN
    IF current_setting('server_version_num')::int < {MIN_SERVER_VERSION_NUM} THEN
        RAISE EXCEPTION 'PostgreSQL % is too old; the bootstrap needs 15 or newer', current_setting('server_version');
    END IF;
    IF NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
        RAISE EXCEPTION 'provider credential % is not a superuser; cannot provision roles', current_user;
    END IF;
    IF current_database() = {db_literal} THEN
        RAISE EXCEPTION 'refusing: the provider URL already points at target database %', current_database();
    END IF;
END
$bootstrap_guard$;

BEGIN;
-- Roles are cluster-wide: never change a pre-existing role that is used
-- outside the target database unless the operator passed --adopt-existing-roles.
DO $bootstrap_adoption$
DECLARE
    usage text;
BEGIN
    IF {"true" if adopt_existing_roles else "false"} THEN
        RETURN;
    END IF;
    SELECT string_agg(role_name || ' ' || detail, '; ' ORDER BY role_name, detail)
      INTO usage
      FROM ({outside_usage_sql(database)}) AS outside;
    IF usage IS NOT NULL THEN
        RAISE EXCEPTION 'pre-existing RegEngine roles are used outside %: %. Re-run with --adopt-existing-roles after review.',
            {db_literal}, usage;
    END IF;
END
$bootstrap_adoption$;

DO $bootstrap_roles$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY {roles} LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name) THEN
            EXECUTE format('CREATE ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION '
                           'CONNECTION LIMIT -1 VALID UNTIL %L', role_name, 'infinity');
            RAISE NOTICE 'created role %', role_name;
        ELSE
            EXECUTE format('ALTER ROLE %I LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOREPLICATION '
                           'CONNECTION LIMIT -1 VALID UNTIL %L', role_name, 'infinity');
            EXECUTE format('ALTER ROLE %I RESET ALL', role_name);
            RAISE NOTICE 'pinned attributes and reset role-wide settings on existing role %', role_name;
        END IF;
        EXECUTE format('COMMENT ON ROLE %I IS %L', role_name, {quote_literal(MANAGED_ROLE_COMMENT)});
    END LOOP;
END
$bootstrap_roles$;

-- v111 rejects any incoming or outgoing membership on these roles.
{membership_sql()}
{password_lines}
COMMIT;

SELECT format('CREATE DATABASE %I OWNER %I TEMPLATE template0', {db_literal}, {quote_literal(MIGRATOR_ROLE)})
 WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = {db_literal})\\gexec

DO $bootstrap_database$
DECLARE
    owner_name text;
BEGIN
    SELECT pg_get_userbyid(datdba) INTO owner_name FROM pg_database WHERE datname = {db_literal};
    IF owner_name IS DISTINCT FROM {quote_literal(MIGRATOR_ROLE)} THEN
        RAISE EXCEPTION 'database % exists but is owned by %; refusing to adopt it', {db_literal}, owner_name;
    END IF;
END
$bootstrap_database$;

REVOKE ALL ON DATABASE {db_ident} FROM PUBLIC;
GRANT CONNECT ON DATABASE {db_ident} TO {grantees};
{reset_lines}
-- Scoped to the new database only. CI runs every migration job with
-- PGOPTIONS "-c timezone=UTC -c search_path=public,fsma,extensions"; Railway
-- has no PGOPTIONS, so pin the same session defaults on the migrator here.
ALTER ROLE {migrator} IN DATABASE {db_ident} SET search_path = public, fsma, extensions;
ALTER ROLE {migrator} IN DATABASE {db_ident} SET timezone = 'UTC';

DO $bootstrap_verify$
DECLARE
    bad record;
BEGIN
    SELECT rolname INTO bad
      FROM pg_roles
     WHERE rolname = ANY ({roles})
       AND (NOT rolcanlogin OR rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication
            OR rolconnlimit <> -1 OR rolvaliduntil IS DISTINCT FROM 'infinity'::timestamptz)
     LIMIT 1;
    IF FOUND THEN
        RAISE EXCEPTION 'role % still has a forbidden attribute', bad.rolname;
    END IF;
    IF (SELECT count(*) FROM pg_roles WHERE rolname = ANY ({roles})) <> 3 THEN
        RAISE EXCEPTION 'not all three RegEngine roles exist';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_auth_members AS am
          JOIN pg_roles AS granted ON granted.oid = am.roleid
          JOIN pg_roles AS member ON member.oid = am.member
         WHERE granted.rolname = ANY ({roles}) OR member.rolname = ANY ({roles})
    ) THEN
        RAISE EXCEPTION 'a role membership involving the RegEngine roles remains';
    END IF;
    IF EXISTS (
        SELECT 1 FROM pg_database AS d, aclexplode(d.datacl) AS acl
         WHERE d.datname = {db_literal} AND acl.grantee = 0
    ) OR (SELECT datacl IS NULL FROM pg_database WHERE datname = {db_literal}) THEN
        RAISE EXCEPTION 'PUBLIC still holds privileges on database %', {db_literal};
    END IF;
END
$bootstrap_verify$;

SELECT {quote_literal(PROVIDER_SENTINEL)};
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
       current_setting('search_path'), current_setting('TimeZone'),
       coalesce((SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid())::text, 'false');
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
SELECT {quote_literal(LOGIN_SENTINEL)};
"""


def runtime_login_sql() -> str:
    return f"""
SELECT 'identity', session_user, current_user, current_database(),
       coalesce((SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid())::text, 'false');
SELECT {quote_literal(LOGIN_SENTINEL)};
"""


def database_url(role: str, password: str, database: str) -> str:
    """Private-network URL; Railway resolves the references at deploy time."""
    return f"postgresql://{role}:{password}@{PGHOST_REF}:{PGPORT_REF}/{database}"


# ---------------------------------------------------------------------------
# Variables. Raw values are read into memory for presence/shape checks and
# are never printed.
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


def parse_variable_values(raw_json: str) -> Dict[str, Optional[str]]:
    """Map variable NAME -> raw value (None when sealed) from ``railway variable list --json``."""
    data = _load_json_payload(raw_json)
    if data is None:
        raise BootstrapError("could not parse `railway variable list --json` output")
    values: Dict[str, Optional[str]] = {}
    if isinstance(data, dict):
        for name, value in data.items():
            values[str(name)] = value if isinstance(value, str) or value is None else str(value)
    elif isinstance(data, list):
        for entry in data:
            if isinstance(entry, dict):
                name = entry.get("name", entry.get("key"))
                if isinstance(name, str):
                    value = entry.get("value")
                    values[name] = value if isinstance(value, str) or value is None else str(value)
    else:
        raise BootstrapError("unexpected `railway variable list --json` shape")
    return values


def parse_variable_presence(raw_json: str) -> Dict[str, bool]:
    """NAME -> usable. Sealed (null) counts as present; an empty string as missing."""
    return {name: value is None or value != "" for name, value in parse_variable_values(raw_json).items()}


def posture_warnings(values: Mapping[str, Optional[str]]) -> List[str]:
    """Warn about visible (unsealed) values that will fail boot; never prints values."""
    warnings: List[str] = []
    otp = values.get("AUTH_OTP_HMAC_SECRET")
    if isinstance(otp, str) and otp and len(otp.encode("utf-8")) < 32:
        warnings.append("AUTH_OTP_HMAC_SECRET is shorter than 32 bytes; boot will fail. Replace it.")
    tool, auth = values.get("TOOL_ACCESS_SECRET"), values.get("AUTH_SECRET_KEY")
    if isinstance(tool, str) and tool and tool == auth:
        warnings.append("TOOL_ACCESS_SECRET equals AUTH_SECRET_KEY; it must differ. Replace it.")
    return warnings


def read_app_variables(ctx: Context) -> str:
    result = railway(["variable", "list", *ctx.scope, "-s", APP_SERVICE, "--json"])
    if result.returncode != 0:
        raise _fail_command(f"reading variables of {APP_SERVICE}", result)
    return result.stdout


def set_variable(ctx: Context, name: str, value: str) -> None:
    """Store one variable. The value goes over stdin only, never argv. Live immediately."""
    result = railway(
        ["variable", "set", name, "--stdin", *ctx.scope, "-s", APP_SERVICE, "--skip-deploys"],
        stdin=value,
    )
    if result.returncode != 0:
        raise _fail_command(f"railway variable set {name}", result)


# ---------------------------------------------------------------------------
# Guards and planning (all read-only).
# ---------------------------------------------------------------------------
def parse_psql_major(text: str) -> Optional[int]:
    """Major version from ``psql --version`` ("psql (PostgreSQL) 16.13 (Ubuntu ...)")."""
    match = re.search(r"\(PostgreSQL\)\s+(\d+)", text or "")
    return int(match.group(1)) if match else None


def read_psql_major(psql: str) -> Optional[int]:
    """``psql --version`` (no connection, no config files read)."""
    result = run_process([psql, "--version"], env=_child_base_env())
    return parse_psql_major(result.stdout) if result.returncode == 0 else None


def parse_cli_version(text: str) -> Optional[Tuple[int, int, int]]:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return tuple(int(part) for part in match.groups()) if match else None  # type: ignore[return-value]


def validate_target(environment: str, database: str) -> None:
    if environment.strip().lower() == "production":
        raise Refused(
            "REFUSED: this bootstrap never targets production. It creates roles and repoints DATABASE_URL; "
            "production uses the reviewed runbook in docs/operations/DATABASE_ROLE_CUTOVER.md."
        )
    if environment != REQUIRED_ENVIRONMENT:
        raise Refused(f"REFUSED: environment must be exactly '{REQUIRED_ENVIRONMENT}' (got {environment!r}).")
    if not DATABASE_NAME.fullmatch(database):
        raise Refused(
            f"REFUSED: --database {database!r} must match ^{DATABASE_NAME.pattern}$ (for example regengine_staging)."
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
    # PGCHANNELBINDING=require is what keeps passwords off the wire (see
    # PSQL_LAUNCHER); libpq before 13 silently ignores it. This relies on psql
    # being linked against the libpq of its own major version, as the PGDG,
    # Homebrew (libpq / postgresql@N) and Debian/Ubuntu packages are.
    major = read_psql_major(psql)
    if major is None or major < MIN_LIBPQ_MAJOR:
        raise Refused(
            f"REFUSED: psql {major if major is not None else 'of unknown version'} is older than "
            f"{MIN_LIBPQ_MAJOR}; channel binding (PGCHANNELBINDING=require) needs psql/libpq {MIN_LIBPQ_MAJOR}+ "
            "and older clients would silently send passwords without it. Install a newer psql "
            "(macOS: brew install libpq)."
        )
    ctx.psql = psql
    print(f"    psql {major}: channel binding enforced (PGCHANNELBINDING=require)")

    version = railway(["--version"])
    parsed = parse_cli_version(version.stdout if version.returncode == 0 else "")
    if parsed is None or parsed < MIN_CLI_VERSION:
        minimum = ".".join(str(part) for part in MIN_CLI_VERSION)
        found = ".".join(str(part) for part in parsed) if parsed else "unknown"
        raise Refused(
            f"REFUSED: Railway CLI {found} is older than {minimum}; older CLIs hide sealed variables, "
            "so existing secrets would be regenerated. Run `railway upgrade --yes` first."
        )
    who = railway(["whoami"])
    if who.returncode != 0:
        raise BootstrapError("Railway CLI is not logged in; run `railway login` first")
    print(f"    railway CLI {'.'.join(str(p) for p in parsed)}: logged in")
    run_help = railway(["run", "--help"])
    if "--no-local" in (run_help.stdout or ""):
        ctx.run_flags = ["--no-local"]  # never let `railway dev` overrides redirect the target

    probe = railway_run(ctx, POSTGRES_SERVICE, [sys.executable, "-c", PROBE_CODE], stdin=STDIN_PROBE)
    if probe.returncode != 0:
        raise _fail_command(f"railway run -s {POSTGRES_SERVICE} probe", probe)
    try:
        info = json.loads(probe.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError) as exc:
        raise BootstrapError("could not read the Postgres service probe output") from exc
    check_probe(ctx, info)
    ctx.endpoint = {k: str(info[k]) for k in ("host", "port", "user", "database")}
    # A kept URL must point at the Postgres service's private endpoint, either as
    # the reference form this script writes or as Railway's rendered value.
    ctx.private_hosts = {(PGHOST_REF, PGPORT_REF)}
    if info.get("pghost") and info.get("pgport"):
        ctx.private_hosts.add((str(info["pghost"]).lower(), str(info["pgport"])))
    print(f"    stdin forwarding through `railway run`: ok{' (with --no-local)' if ctx.run_flags else ''}")
    print(f"    railway run resolved project {info['project']} environment {info['environment']}")
    print(
        f"    provider login: {info.get('user')} via the service's own TCP proxy {info['host']}:{info['port']} "
        "(TLS + SCRAM channel binding)"
    )
    print(f"    existing database (archive, left untouched): {info.get('database')}")
    print(
        f"    private endpoint for stored URLs: {PGHOST_REF}:{PGPORT_REF} = {info.get('pghost')}:{info.get('pgport')}"
    )
    personal_tls = [
        name
        for name, present in (
            ("~/.postgresql/root.crt", (Path.home() / ".postgresql" / "root.crt").exists()),
            ("PGSSLROOTCERT", bool(os.environ.get("PGSSLROOTCERT"))),
            ("PGSSLMODE", bool(os.environ.get("PGSSLMODE"))),
        )
        if present
    ]
    if personal_tls:
        print(
            f"    note: ignoring {', '.join(personal_tls)}. psql runs with a private empty HOME and no inherited PG* "
            "settings. Railway's proxy certificate is self-signed and is not CA-verified; passwords are protected "
            "by SCRAM-SHA-256 with channel binding (PGCHANNELBINDING=require), never sent in cleartext."
        )

    rows = provider_psql(ctx, inventory_sql(ctx.database), INVENTORY_SENTINEL, "read-only inventory")
    record_inventory(ctx, rows)


def check_probe(ctx: Context, info: Mapping[str, object]) -> None:
    """Fail closed unless `railway run` resolved exactly the intended project, environment and proxy."""
    if not info.get("stdin_ok"):
        raise BootstrapError("`railway run` did not forward stdin to the child process; cannot send SQL safely")
    if info.get("environment") != ctx.environment:
        raise Refused(
            f"REFUSED: railway run resolved RAILWAY_ENVIRONMENT_NAME={info.get('environment')!r}, "
            f"expected {ctx.environment!r}"
        )
    if info.get("project") != ctx.project:
        raise Refused(
            f"REFUSED: railway run resolved RAILWAY_PROJECT_ID={info.get('project')!r}, expected {ctx.project}"
        )
    if info.get("url_error") or not info.get("host"):
        raise Refused(f"REFUSED: {POSTGRES_SERVICE} has no usable DATABASE_PUBLIC_URL in {ctx.environment}")
    proxy = (str(info.get("proxy_domain") or ""), str(info.get("proxy_port") or ""))
    if not all(proxy) or (str(info["host"]), str(info.get("port"))) != proxy:
        raise Refused(
            "REFUSED: DATABASE_PUBLIC_URL does not point at this service's RAILWAY_TCP_PROXY_DOMAIN:"
            "RAILWAY_TCP_PROXY_PORT; refusing to send credentials anywhere else"
        )
    if info.get("database") == ctx.database:
        raise Refused(
            f"REFUSED: DATABASE_PUBLIC_URL already names {ctx.database!r}; the archive database cannot be the target"
        )


def record_inventory(ctx: Context, rows: Sequence[Sequence[str]]) -> None:
    for row in rows:
        tag = row[0]
        if tag == "whoami":
            print(
                f"    connected as {row[1]} (superuser={row[2]}, ssl={row[5]}) to {row[3]}, server_version_num={row[4]}"
            )
            if row[2] != "true":
                raise BootstrapError("the Postgres service credential is not a superuser; cannot provision roles")
            if int(row[4]) < MIN_SERVER_VERSION_NUM:
                raise Refused(f"REFUSED: PostgreSQL server_version_num {row[4]} is older than 15")
        elif tag == "role":
            ctx.existing_roles.add(row[1])
            if row[8] == "true":
                ctx.managed_roles.add(row[1])
            print(
                f"    existing role {row[1]}: login={row[2]} super={row[3]} bypassrls={row[4]} createdb={row[5]} "
                f"createrole={row[6]} replication={row[7]} "
                f"({'created by this bootstrap' if row[8] == 'true' else 'NOT created by this bootstrap'})"
            )
        elif tag == "database":
            ctx.target_exists = True
            print(f"    target database {row[1]} exists, owner={row[2]}")
            if row[2] != MIGRATOR_ROLE:
                raise Refused(f"REFUSED: database {row[1]} exists but is owned by {row[2]}; refusing to adopt it")
        elif tag == "outside":
            ctx.outside_usage.append((row[1], row[2]))
            print(f"    OUTSIDE USE: role {row[1]} {row[2]}")
        elif tag == "blocked-grant":
            ctx.blocked_grants.append((row[1], row[2], row[3]))
            print(f"    BLOCKING GRANT: {row[1]} used its ADMIN OPTION to grant foreign role {row[2]} to {row[3]}")
        elif tag == "target-sessions" and row[1] != "0":
            print(f"    {row[1]} open session(s) by RegEngine roles in {ctx.database} (a running deployment)")
    if not any(row[0] == "database" for row in rows):
        print(f"    target database {ctx.database}: absent (will be created)")
    for role in ALL_ROLES:
        if role not in ctx.existing_roles:
            print(f"    role {role}: absent (will be created)")


def _url_matches(value: str, role: str, database: str, private_hosts: Set[Tuple[str, str]]) -> Optional[str]:
    """Return the password when ``value`` is a URL for role@database on the staging private endpoint.

    The host:port must be the ``${{Postgres.PGHOST}}:${{Postgres.PGPORT}}``
    reference form or its rendered value. The password is never printed.
    """
    try:
        parts = urlsplit(value)
        user, password = unquote(parts.username or ""), unquote(parts.password or "")
        dbname = unquote(parts.path.lstrip("/"))
    except ValueError:
        return None
    host, _, port = parts.netloc.rpartition("@")[2].rpartition(":")
    host_port = (host if host.startswith("${{") else host.lower(), port)
    if parts.scheme not in ("postgresql", "postgres") or user != role or dbname != database or not password:
        return None
    if host_port not in private_hosts:
        return None
    return password


def _url_problem(values: Mapping[str, Optional[str]], variable: str, role: str, ctx: Context) -> Optional[str]:
    """None when ``variable`` points at role@target on the staging private endpoint, else why not."""
    if variable not in values:
        return f"{variable} is missing"
    if values[variable] is None:
        return f"{variable} is sealed, so it cannot be verified"
    password = _url_matches(values[variable] or "", role, ctx.database, ctx.private_hosts)
    if password is None:
        return f"{variable} does not point at {role}@{ctx.database} on the staging Postgres private endpoint"
    ctx.kept_passwords[role] = _register_secret(password)
    return None


def plan(ctx: Context, values: Mapping[str, Optional[str]]) -> List[str]:
    """Decide adoption and password handling; return blockers (reasons --apply must refuse).

    Read-only. A role this run would keep has its stored password tested by
    logging in before anything is written.
    """
    blockers: List[str] = []
    if ctx.blocked_grants:
        detail = "; ".join(
            f"{grantor} granted role {granted} to {member}" for grantor, granted, member in ctx.blocked_grants
        )
        blockers.append(
            f"these grants depend on a RegEngine role's membership of a foreign role and would have to be cascaded "
            f"away outside RegEngine ({detail}). --adopt-existing-roles never does that: revoke them by hand after "
            "review, then re-run."
        )
    if ctx.outside_usage and not ctx.adopt_existing_roles:
        detail = "; ".join(f"{role} {what}" for role, what in ctx.outside_usage)
        blockers.append(
            f"pre-existing roles are used outside {ctx.database} ({detail}). Review, then pass --adopt-existing-roles."
        )
    foreign: List[str] = []
    needs_rotation: List[str] = []
    for variable, role in ROLE_URL_VARIABLES:
        if role not in ctx.existing_roles:
            ctx.password_plan[role] = "new"
            continue
        problem = _url_problem(values, variable, role, ctx)
        if problem and role not in ctx.managed_roles and not ctx.adopt_existing_roles:
            foreign.append(f"{role} was not created by this bootstrap and {problem}")
        if ctx.rotate_passwords:
            ctx.password_plan[role] = "rotate"
        elif problem:
            needs_rotation.append(problem)
        elif not ctx.target_exists:
            needs_rotation.append(
                f"{ctx.database} does not exist yet, so the stored password for {role} cannot be tested"
            )
        else:
            ctx.password_plan[role] = "keep"
    if foreign:
        blockers.append("; ".join(foreign) + ". Review, then pass --adopt-existing-roles.")
    if needs_rotation:
        blockers.append("; ".join(needs_rotation) + ". Pass --rotate-passwords to set new passwords (then redeploy).")
    for role in ALL_ROLES:
        if ctx.password_plan.get(role) != "keep":
            continue
        try:
            rows = role_psql(ctx, role, ctx.kept_passwords[role], runtime_login_sql(), LOGIN_SENTINEL, f"{role} login")
            identity = next((row[1:] for row in rows if row[0] == "identity"), [])
            if identity[:3] != [role, role, ctx.database]:
                raise BootstrapError(f"login resolved to {identity[:3]!r}")
        except BootstrapError:
            blockers.append(f"stored URL password for {role} does not log in; re-run with --apply --rotate-passwords.")
            continue
        print(f"    stored password for {role}: logs in to {ctx.database} (kept)")
    return blockers


# ---------------------------------------------------------------------------
# Output.
# ---------------------------------------------------------------------------
def print_plan(ctx: Context, presence: Mapping[str, bool]) -> None:
    placeholder = {
        role: f"<scram-sha-256 verifier for a new random password: {role}>"
        for role in ALL_ROLES
        if ctx.password_plan.get(role) in ("new", "rotate")
    }
    step(2, f"Provision roles and database {ctx.database} as the {POSTGRES_SERVICE} template superuser")
    print(f"    via: railway run {' '.join(ctx.scope)} -s {POSTGRES_SERVICE} -- <launcher: URL -> PG* env> psql -f -")
    for role in ALL_ROLES:
        print(f"    password for {role}: {ctx.password_plan.get(role, 'blocked')}")
    print("    SQL (over stdin):")
    sql = provider_sql(ctx.database, placeholder, adopt_existing_roles=ctx.adopt_existing_roles)
    for line in sql.strip().splitlines():
        print(f"      {line}")
    step(3, f"Seed get_tenant_context() logged in as {MIGRATOR_ROLE} (only if absent)")
    for line in GET_TENANT_CONTEXT_SQL.splitlines():
        print(f"      {line}")
    step(4, f"Prove {RUNTIME_ROLE} and {ADMIN_ROLE} can log in to {ctx.database} (TLS)")
    step(5, f"Write {APP_SERVICE} variables in this order (stdin only; each write is live immediately)")
    for name, value in write_order(ctx, presence, preview=True):
        print(f"    {name} = {value}")


def write_order(ctx: Context, presence: Mapping[str, bool], *, preview: bool) -> List[Tuple[str, str]]:
    """The (name, shown-value) sequence; MIGRATIONS_DATABASE_URL is always last."""
    ordered: List[Tuple[str, str]] = []
    urls = {variable: role for variable, role in ROLE_URL_VARIABLES}
    for variable in ("DATABASE_URL", "ADMIN_DATABASE_URL"):
        role = urls[variable]
        if ctx.password_plan.get(role) in ("new", "rotate"):
            ordered.append((variable, database_url(role, "<new password>", ctx.database)))
    for name, nbytes in GENERATED_IF_MISSING:
        if not presence.get(name):
            ordered.append((name, f"<generated token_urlsafe({nbytes})>"))
    for name, value in LITERALS_ALWAYS:
        ordered.append((name, value))
    for name, value in LITERALS_IF_MISSING:
        if not presence.get(name):
            ordered.append((name, value))
    if ctx.password_plan.get(MIGRATOR_ROLE) in ("new", "rotate"):
        ordered.append(("MIGRATIONS_DATABASE_URL", database_url(MIGRATOR_ROLE, "<new password>", ctx.database)))
    if preview:
        kept = [n for n, r in ROLE_URL_VARIABLES if ctx.password_plan.get(r) == "keep"]
        kept += [n for n, _ in GENERATED_IF_MISSING if presence.get(n)]
        kept += [n for n, _ in LITERALS_IF_MISSING if presence.get(n)]
        ordered += [(name, "<present: kept>") for name in kept]
    return ordered


def redeploy_command(ctx: Context) -> str:
    return f"railway redeploy -p {ctx.project} -e {ctx.environment} -s {APP_SERVICE} --yes"


def print_checklist(ctx: Context, *, applied: bool) -> None:
    print("\nNext steps")
    archive = ctx.endpoint.get("database") or "the existing database"
    if ctx.redeploy:
        deploy = "Redeploy requested."
    else:
        deploy = f"Deploy once: {redeploy_command(ctx)}  (any push to the tracked branch also deploys these values)"
    lines = [
        f"Old database '{archive}' is left untouched as an archive; the new URLs point at '{ctx.database}'.",
        "Variables written by the CLI are live immediately (not staged); the next deploy uses them.",
        "In the Railway dashboard (staging -> RegEngine -> Variables) Seal: " + ", ".join(SECRET_VARIABLES_TO_SEAL),
        deploy,
        "Expect in the deploy log: 'DB state: FRESH' (ALREADY_MANAGED after a previous deploy), Alembic "
        "upgrades ending at the current head, "
        f"'runtime role cutover applied as role={MIGRATOR_ROLE} database={ctx.database}', then gunicorn boot.",
        "Verify: GET /readiness returns 200 with postgres ok and redis ok (neo4j may only mark it degraded).",
        "Re-running --apply is safe. It keeps passwords unless roles are new or --rotate-passwords is given; "
        "after a rotation, redeploy. Once the URLs are sealed a re-run needs --rotate-passwords.",
    ]
    if not applied:
        lines.insert(0, "DRY RUN: nothing was changed. Re-run with --apply to execute steps 2-5.")
    for line in lines:
        print(f"    - {line}")


# ---------------------------------------------------------------------------
# Apply.
# ---------------------------------------------------------------------------
def apply_database(ctx: Context) -> Dict[str, str]:
    passwords: Dict[str, str] = {}
    verifiers: Dict[str, str] = {}
    for role in ALL_ROLES:
        if ctx.password_plan[role] in ("new", "rotate"):
            passwords[role] = generate_password()
            verifiers[role] = scram_sha256_verifier(passwords[role])
        else:
            passwords[role] = ctx.kept_passwords[role]

    step(2, f"Provision roles and database {ctx.database} as the {POSTGRES_SERVICE} template superuser")
    ctx.passwords_changed = bool(verifiers)
    provider_psql(
        ctx,
        provider_sql(ctx.database, verifiers, adopt_existing_roles=ctx.adopt_existing_roles),
        PROVIDER_SENTINEL,
        "provider provisioning",
    )
    changed = ", ".join(sorted(verifiers)) or "none"
    print(f"    roles pinned; new passwords: {changed}; database {ctx.database} owned by {MIGRATOR_ROLE}")
    print("    PUBLIC privileges revoked on the database; CONNECT granted to the three roles")

    step(3, f"Seed get_tenant_context() logged in as {MIGRATOR_ROLE}")
    rows = _login(ctx, MIGRATOR_ROLE, passwords[MIGRATOR_ROLE], migrator_sql())
    facts = {row[0]: row[1:] for row in rows}
    identity = facts.get("identity", [])
    if identity[:3] != [MIGRATOR_ROLE, MIGRATOR_ROLE, ctx.database]:
        raise BootstrapError(f"migrator login resolved to {identity[:3]!r}")
    print(
        f"    logged in as {identity[0]} to {identity[2]} (ssl={identity[5]}); "
        f"search_path={identity[3]}; timezone={identity[4]}"
    )
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
        rows = _login(ctx, role, passwords[role], runtime_login_sql())
        identity = next((row[1:] for row in rows if row[0] == "identity"), [])
        if identity[:3] != [role, role, ctx.database]:
            raise BootstrapError(f"{role} login resolved to {identity[:3]!r}")
        print(f"    {role}: login ok (ssl={identity[3]}, password {ctx.password_plan[role]})")
    return passwords


def _login(ctx: Context, role: str, password: str, sql: str) -> List[List[str]]:
    """Log in as ``role``. A kept password that stopped working can only be fixed by rotating."""
    try:
        return role_psql(ctx, role, password, sql, LOGIN_SENTINEL, f"{role} login")
    except BootstrapError:
        if ctx.password_plan.get(role) != "keep":
            raise
        ctx.rotate_hint = True
        raise BootstrapError(
            f"stored URL password for {role} does not log in; re-run with --apply --rotate-passwords"
        ) from None


def apply_variables(
    ctx: Context,
    passwords: Mapping[str, str],
    values: Mapping[str, Optional[str]],
    presence: Mapping[str, bool],
) -> None:
    step(5, f"Write {APP_SERVICE} variables (stdin only; MIGRATIONS_DATABASE_URL last)")
    urls = {variable: role for variable, role in ROLE_URL_VARIABLES}
    for name, _ in write_order(ctx, presence, preview=False):
        if name in urls:
            role = urls[name]
            set_variable(ctx, name, database_url(role, passwords[role], ctx.database))
            if name == "MIGRATIONS_DATABASE_URL":
                ctx.migrations_url_written = True
            print(f"    {name}: set (role {role}, database {ctx.database}, host {PGHOST_REF})")
        elif name in dict(GENERATED_IF_MISSING):
            set_variable(ctx, name, generate_secret(dict(GENERATED_IF_MISSING)[name]))
            print(f"    {name}: generated and stored (value not displayed)")
        else:
            value = dict(LITERALS_ALWAYS + LITERALS_IF_MISSING)[name]
            if values.get(name) == value:
                print(f"    {name} = {value} (already set)")
                continue
            set_variable(ctx, name, value)
            print(f"    {name} = {value}")
    for variable, role in ROLE_URL_VARIABLES:
        if ctx.password_plan[role] == "keep":
            print(f"    {variable}: kept (verified by logging in as {role})")

    after = parse_variable_presence(read_app_variables(ctx))
    required = [name for name, _ in ROLE_URL_VARIABLES] + [name for name, _ in GENERATED_IF_MISSING]
    required += [name for name, _ in LITERALS_ALWAYS] + [name for name, _ in LITERALS_IF_MISSING]
    missing = [name for name in required if not after.get(name)]
    if missing:
        raise BootstrapError(f"read-back is missing variables: {', '.join(missing)}")
    print(f"    read-back by name: all {len(required)} required variables present")


def parse_args(argv: Optional[Sequence[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap a FRESH RegEngine staging database on Railway (dry-run by default).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="print every step without changing anything (default)")
    mode.add_argument("--apply", action="store_true", help="execute the steps")
    parser.add_argument("--redeploy", action="store_true", help="with --apply: redeploy RegEngine afterwards")
    parser.add_argument(
        "--rotate-passwords",
        action="store_true",
        help="set new passwords for all three roles even when they already exist (redeploy afterwards)",
    )
    parser.add_argument(
        "--adopt-existing-roles",
        action="store_true",
        help="allow changing pre-existing roles that are used outside the target database or have elevated "
        "attributes, or that this bootstrap did not create and whose URL variable does not point at them "
        "(after review)",
    )
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
        adopt_existing_roles=bool(args.adopt_existing_roles),
        rotate_passwords=bool(args.rotate_passwords),
    )
    mode = "APPLY" if ctx.apply else "DRY RUN"
    print(f"RegEngine staging database bootstrap [{mode}] project={ctx.project} environment={ctx.environment}")
    ctx.psql_home = tempfile.mkdtemp(prefix="regengine-bootstrap-psql-home-")  # 0700, empty
    try:
        return _run(ctx)
    finally:
        shutil.rmtree(ctx.psql_home, ignore_errors=True)


def _run(ctx: Context) -> int:
    try:
        preflight(ctx)
        values = parse_variable_values(read_app_variables(ctx))
        presence = {name: value is None or value != "" for name, value in values.items()}
        for warning in posture_warnings(values):
            print(f"    WARNING: {warning}")
        blockers = plan(ctx, values)
        if not ctx.apply:
            print_plan(ctx, presence)
            if blockers:
                print("\n--apply would REFUSE:", file=sys.stderr)
                for blocker in blockers:
                    print(f"    - {blocker}", file=sys.stderr)
                return EXIT_REFUSED
            print_checklist(ctx, applied=False)
            return 0
        if blockers:
            raise Refused("REFUSED before any change: " + " | ".join(blockers))
        passwords = apply_database(ctx)
        apply_variables(ctx, passwords, values, presence)
        if ctx.redeploy:
            step(6, f"Redeploy {APP_SERVICE}")
            result = railway(["redeploy", *ctx.scope, "-s", APP_SERVICE, "--yes"])
            if result.returncode != 0:
                raise _fail_command("railway redeploy", result)
            print("    redeploy requested; watch the deploy log for the lines in the checklist")
        print_checklist(ctx, applied=True)
        return 0
    except Refused as refusal:
        print(f"\n{redact(str(refusal))}", file=sys.stderr)
        return EXIT_REFUSED
    except BootstrapError as exc:
        print(f"\nFAILED: {redact(str(exc))}", file=sys.stderr)
        _print_recovery_hint(ctx)
        return EXIT_FAILED
    except subprocess.TimeoutExpired as exc:
        print(f"\nFAILED: a command timed out after {exc.timeout}s and its process group was killed.", file=sys.stderr)
        _print_recovery_hint(ctx)
        return EXIT_FAILED
    except KeyboardInterrupt:
        print("\nINTERRUPTED: the running command's process group was killed.", file=sys.stderr)
        _print_recovery_hint(ctx)
        return 130


def _print_recovery_hint(ctx: Context) -> None:
    if ctx.rotate_hint:
        print(
            "Only new passwords can fix this: re-run with --apply --rotate-passwords, then redeploy.", file=sys.stderr
        )
    elif ctx.passwords_changed and not ctx.migrations_url_written:
        print(
            "Passwords were changed but MIGRATIONS_DATABASE_URL was not updated (unset, or still holding the old "
            "password), so any deploy stops at run-migrations.sh and gunicorn never starts. Fix the cause and re-run "
            "with --apply --rotate-passwords.",
            file=sys.stderr,
        )
    else:
        print("Every step converges: fix the cause and re-run the same command.", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
