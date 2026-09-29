import asyncio
import hashlib
import os
import random
import threading
import time
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass

import structlog
from prometheus_client import REGISTRY, CollectorRegistry, Gauge
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

logger = structlog.get_logger("shared.database")


# Prometheus Metrics — guard against duplicate registration on re-import
def _safe_gauge(name: str, description: str) -> Gauge:
    """Return existing Gauge if already registered, else create a new one."""
    try:
        return Gauge(name, description)
    except ValueError:
        # Already registered — return the existing collector
        return REGISTRY._names_to_collectors.get(name, Gauge(name, description, registry=None))


db_circuit_breaker_state = _safe_gauge("db_circuit_breaker_state", "0=closed, 1=open, 2=half_open")
db_pool_checkedout = _safe_gauge("db_pool_checkedout", "Active connections")
db_pool_overflow = _safe_gauge("db_pool_overflow", "Overflow connections")

# Resilience Parameters
BULKHEAD_LIMIT = int(os.getenv("DB_BULKHEAD_LIMIT", "20"))
sync_bulkhead = threading.Semaphore(BULKHEAD_LIMIT)
async_bulkhead = asyncio.Semaphore(BULKHEAD_LIMIT)


class CircuitBreaker:
    def __init__(self, failure_threshold=5, base_recovery=30, backoff_factor=2):
        self.failure_threshold = failure_threshold
        self.base_recovery = base_recovery
        self.backoff_factor = backoff_factor
        self.failure_count = 0
        self.last_failure = 0
        self.state = "CLOSED"

    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            elapsed = time.time() - self.last_failure
            recovery = self.base_recovery * (self.backoff_factor**self.failure_count)
            if elapsed > recovery:
                self.state = "HALF_OPEN"
                db_circuit_breaker_state.set(2)
            else:
                db_circuit_breaker_state.set(1)
                raise ConnectionError(f"Circuit breaker OPEN (cooling for {int(recovery - elapsed)}s)")
        try:
            result = func(*args, **kwargs) if callable(func) else func
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
            self.failure_count = 0
            db_circuit_breaker_state.set(0)
            return result
        except OperationalError:
            self.failure_count += 1
            self.last_failure = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = "OPEN"
                db_circuit_breaker_state.set(1)
            raise


def retry_with_jitter(func, max_retries=3, base_delay=0.1):
    """Execute function with exponential backoff and 20% jitter."""
    for attempt in range(max_retries):
        try:
            return func()
        except OperationalError:
            if attempt == max_retries - 1:
                raise
            delay = base_delay * (2**attempt) * (1 + random.uniform(-0.2, 0.2))
            logger.warning("database_retry", attempt=attempt + 1, delay=delay)
            time.sleep(delay)


# Engine initialization
_DEV_DATABASE_URL = "postgresql://regengine:regengine@postgres:5432/regengine"
# #2461: importing tenant_context installs the class-level RLS GUC
# "begin" hook BEFORE the module-level create_engine() below, so every
# transaction on this engine (and every other Engine in the process)
# gets a fail-closed security-GUC baseline plus app.tenant_id from the
# seeded contextvar. Import kept under the ``shared.`` alias — the
# canonical runtime alias — so exactly one module instance (and one
# ContextVar pair) exists.
import shared.tenant_context  # noqa: F401,E402  (side effect: install_rls_guc_hook)
from shared.db_url import sync_postgres_connect_args, sync_postgres_url
from shared.env import is_production

_is_prod = is_production()
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    if _is_prod:
        raise ValueError(
            "DATABASE_URL environment variable must be set in production. Refusing to start with default credentials."
        )
    logger.warning(
        "database_url_default",
        msg="DATABASE_URL not set — using dev default. Do NOT use in production.",
    )
    DATABASE_URL = _DEV_DATABASE_URL


# Pool-sizing kwargs are only valid for connection-pooled dialects.
# SQLite (used by tests with ``DATABASE_URL=sqlite:///:memory:``) picks
# ``SingletonThreadPool`` or ``StaticPool`` which reject
# ``pool_size`` / ``max_overflow`` / ``pool_timeout`` / ``pool_recycle``
# with a ``TypeError`` at engine construction. Previously this failed
# collection of every ingestion-service pytest run that transitively
# imported ``shared.database``. Production uses Postgres so this guard
# is invisible there.
def _build_engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {"pool_pre_ping": True}
    if not database_url.startswith("sqlite"):
        kwargs.update(
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
            pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
            pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
            # Bounded connect + dead-peer detection, so a Postgres restart
            # cannot block a request or scheduler job forever; no server-side
            # prepared statements (transaction-mode pooler safe).
            connect_args=sync_postgres_connect_args(database_url),
        )
    return kwargs


# psycopg 3 for every Postgres scheme; see shared.db_url. DATABASE_URL itself
# stays as configured for callers that read it.
_ENGINE_URL = sync_postgres_url(DATABASE_URL)
_engine_kwargs = _build_engine_kwargs(_ENGINE_URL)
engine = create_engine(_ENGINE_URL, **_engine_kwargs)

# SQLite's SingletonThreadPool/StaticPool (test envs, see above) have no
# checkedout()/overflow(); report 0 instead of failing every metrics scrape.
db_pool_checkedout.set_function(lambda: getattr(engine.pool, "checkedout", lambda: 0)())
db_pool_overflow.set_function(lambda: getattr(engine.pool, "overflow", lambda: 0)())


# #2461: 1 when the connected role is SUPERUSER/BYPASSRLS (RLS inert),
# 0 when enforced. Labeled per engine because the admin service may
# point at a different database than the shared engine.
def _safe_labeled_gauge(name: str, description: str, labelnames: list[str]) -> Gauge:
    try:
        return Gauge(name, description, labelnames)
    except ValueError:
        existing = REGISTRY._names_to_collectors.get(name)
        if existing is not None:
            return existing  # type: ignore[return-value]
        return Gauge(name, description, labelnames, registry=None)


regengine_rls_enforcement_inert = _safe_labeled_gauge(
    "regengine_rls_enforcement_inert",
    "1 when the DB role can bypass RLS or the required v111 catalog controls are missing, 0 when enforced.",
    ["engine"],
)


# A role-name/rolbypassrls probe alone can report a false green after an
# unmanaged database is stamped at head or after policy/ACL drift.  This
# catalog-only canary intentionally touches no tenant data and is executable
# with both least-privilege runtime roles.  It proves the critical v111 FORCE
# RLS, policy, role-topology, ownership, and privilege signatures before the
# metric can report zero.
_RUNTIME_CUTOVER_CANARY_SQL = """
WITH required_relations(schema_name, relation_name) AS (
    VALUES
        ('public', 'api_keys'),
        ('public', 'users'),
        ('public', 'sessions'),
        ('public', 'user_emails'),
        ('public', 'organization_memberships'),
        ('public', 'organizations'),
        ('public', 'auth_challenges'),
        ('public', 'webauthn_credentials'),
        ('public', 'webauthn_challenges'),
        ('public', 'admin_mfa_recovery_codes'),
        ('public', 'memberships'),
        ('public', 'roles'),
        ('public', 'tenants'),
        ('public', 'funnel_events'),
        ('public', 'audit_log_buffer'),
        ('fsma', 'agent_artifacts'),
        ('fsma', 'agent_artifact_reviews'),
        ('fsma', 'ingestion_run_receipts'),
        ('fsma', 'ingestion_runs'),
        ('fsma', 'task_queue'),
        ('fsma', 'fsma_audit_trail'),
        ('ingestion', 'documents'),
        ('ingestion', 'jobs'),
        ('ingestion', 'audit_log'),
        ('dlq', 'webhook_failures'),
        ('fsma', 'incidents'),
        ('fsma', 'exchange_packages'),
        ('fsma', 'organizations')
),
policy_manifest AS (
    SELECT COALESCE(
               string_agg(
                   concat_ws(
                       chr(31),
                       policy.schemaname,
                       policy.tablename,
                       policy.policyname,
                       policy.permissive,
                       array_to_string(policy.roles, ','),
                       policy.cmd,
                       regexp_replace(
                           trim(COALESCE(policy.qual, '<NULL>')),
                           '\\s+',
                           ' ',
                           'g'
                       ),
                       regexp_replace(
                           trim(COALESCE(policy.with_check, '<NULL>')),
                           '\\s+',
                           ' ',
                           'g'
                       )
                   ),
                   chr(30) ORDER BY
                       policy.schemaname,
                       policy.tablename,
                       policy.policyname,
                       policy.cmd,
                       policy.roles::text
               ),
               ''
           ) AS manifest
      FROM pg_policies AS policy
      JOIN required_relations AS required
        ON required.schema_name = policy.schemaname
       AND required.relation_name = policy.tablename
     WHERE current_user = ANY(policy.roles)
        OR 'public'::name = ANY(policy.roles)
),
relation_posture AS (
    SELECT COALESCE(
               bool_and(
                   c.oid IS NOT NULL
                   AND c.relrowsecurity
                   AND c.relforcerowsecurity
               ),
               false
           ) AS ok
      FROM required_relations AS required
      LEFT JOIN pg_namespace AS n ON n.nspname = required.schema_name
      LEFT JOIN pg_class AS c
        ON c.relnamespace = n.oid
       AND c.relname = required.relation_name
       AND c.relkind IN ('r', 'p')
),
policy_guards AS (
    SELECT NOT EXISTS (
        SELECT 1
          FROM pg_policies
         WHERE COALESCE(qual, '') LIKE '%regengine.system_context%'
            OR COALESCE(with_check, '') LIKE '%regengine.system_context%'
            OR (
                COALESCE(qual, '') LIKE '%regengine.is_sysadmin%'
                AND (
                    lower(COALESCE(qual, '')) NOT LIKE '%current_user%'
                    OR lower(COALESCE(qual, '')) NOT LIKE '%regengine_sysadmin%'
                )
            )
            OR (
                COALESCE(with_check, '') LIKE '%regengine.is_sysadmin%'
                AND (
                    lower(COALESCE(with_check, '')) NOT LIKE '%current_user%'
                    OR lower(COALESCE(with_check, '')) NOT LIKE '%regengine_sysadmin%'
                )
            )
    ) AS ok
),
implicit_authority AS (
    SELECT NOT EXISTS (
               SELECT 1
                 FROM pg_auth_members
                WHERE member = (SELECT oid FROM pg_roles WHERE rolname = current_user)
                   OR roleid = (SELECT oid FROM pg_roles WHERE rolname = current_user)
           )
           AND NOT EXISTS (
               SELECT 1
                 FROM pg_database
                WHERE datname = current_database()
                  AND datdba = (SELECT oid FROM pg_roles WHERE rolname = current_user)
           )
           AND NOT EXISTS (
               SELECT 1
                 FROM pg_namespace
                WHERE nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
                  AND nspowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
           )
           AND NOT EXISTS (
               SELECT 1
                 FROM pg_class AS c
                 JOIN pg_namespace AS n ON n.oid = c.relnamespace
                WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
                  AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
                  AND c.relowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
           )
           AND NOT EXISTS (
               SELECT 1
                 FROM pg_proc AS p
                 JOIN pg_namespace AS n ON n.oid = p.pronamespace
                WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
                  AND p.proowner = (SELECT oid FROM pg_roles WHERE rolname = current_user)
           ) AS ok
),
privilege_posture AS (
    SELECT
        NOT EXISTS (
            SELECT 1
              FROM unnest(ARRAY['public', 'fsma', 'audit', 'dlq', 'ingestion'])
                   AS protected_schema(schema_name)
             WHERE has_schema_privilege(
                       current_user,
                       protected_schema.schema_name,
                       'CREATE'
                   )
        )
        AND NOT has_table_privilege(current_user, 'public.alembic_version', 'SELECT')
        AND NOT has_table_privilege(current_user, 'public.alembic_version', 'INSERT')
        AND NOT has_table_privilege(current_user, 'public.alembic_version', 'UPDATE')
        AND NOT has_table_privilege(current_user, 'public.alembic_version', 'DELETE')
        AND CASE current_user
            WHEN 'regengine' THEN
                has_table_privilege(current_user, 'fsma.task_queue', 'SELECT')
                AND has_table_privilege(current_user, 'fsma.task_queue', 'INSERT')
                AND NOT has_table_privilege(current_user, 'fsma.task_queue', 'UPDATE')
                AND NOT has_table_privilege(current_user, 'fsma.task_queue', 'DELETE')
                AND NOT has_table_privilege(current_user, 'public.audit_log_buffer', 'SELECT')
                AND NOT has_table_privilege(current_user, 'dlq.webhook_failures', 'SELECT')
                AND has_table_privilege(current_user, 'public.compliance_alerts', 'SELECT')
                AND has_table_privilege(current_user, 'public.compliance_alerts', 'INSERT')
                AND NOT has_table_privilege(current_user, 'public.compliance_alerts', 'UPDATE')
                AND NOT has_table_privilege(current_user, 'public.compliance_notifications', 'SELECT')
                AND NOT has_table_privilege(current_user, 'public.compliance_status_log', 'SELECT')
                AND has_table_privilege(current_user, 'fsma.notification_outbox', 'SELECT')
                AND has_table_privilege(current_user, 'fsma.notification_outbox', 'UPDATE')
                AND has_table_privilege(current_user, 'fsma.remediation_tokens', 'SELECT')
                AND has_table_privilege(current_user, 'fsma.remediation_tokens', 'INSERT')
                AND has_table_privilege(current_user, 'fsma.remediation_tokens', 'UPDATE')
                AND has_function_privilege(current_user, 'public.set_tenant_context(text)', 'EXECUTE')
                AND NOT has_function_privilege(current_user, 'public.set_admin_context(boolean)', 'EXECUTE')
                AND NOT has_function_privilege(current_user, 'fsma.get_remediation_token_by_hash(text)', 'EXECUTE')
                AND NOT has_function_privilege(current_user, 'fsma.get_remediation_token_by_session_hash(text)', 'EXECUTE')
            WHEN 'regengine_sysadmin' THEN
                has_table_privilege(current_user, 'fsma.task_queue', 'SELECT')
                AND NOT has_table_privilege(current_user, 'fsma.task_queue', 'INSERT')
                AND NOT has_table_privilege(current_user, 'fsma.task_queue', 'UPDATE')
                AND has_column_privilege(current_user, 'fsma.task_queue', 'status', 'UPDATE')
                AND has_table_privilege(current_user, 'fsma.task_queue', 'DELETE')
                AND has_table_privilege(current_user, 'public.audit_log_buffer', 'SELECT')
                AND NOT has_table_privilege(current_user, 'public.audit_log_buffer', 'UPDATE')
                AND has_column_privilege(current_user, 'public.audit_log_buffer', 'replayed_at', 'UPDATE')
                AND has_table_privilege(current_user, 'dlq.webhook_failures', 'SELECT')
                AND NOT has_table_privilege(current_user, 'dlq.webhook_failures', 'UPDATE')
                AND has_column_privilege(current_user, 'dlq.webhook_failures', 'status', 'UPDATE')
                AND has_table_privilege(current_user, 'public.api_keys', 'SELECT')
                AND has_table_privilege(current_user, 'public.api_keys', 'INSERT')
                AND NOT has_table_privilege(current_user, 'public.api_keys', 'UPDATE')
                AND has_column_privilege(current_user, 'public.api_keys', 'enabled', 'UPDATE')
                AND NOT has_table_privilege(current_user, 'public.api_keys', 'DELETE')
                AND has_function_privilege(current_user, 'public.set_admin_context(boolean)', 'EXECUTE')
            ELSE false
        END AS ok
),
disabled_surface_posture AS (
    SELECT NOT EXISTS (
               SELECT 1
                 FROM pg_policies
                WHERE (schemaname, tablename) IN (
                          ('fsma', 'incidents'),
                          ('fsma', 'exchange_packages'),
                          ('fsma', 'organizations')
                      )
           )
           AND NOT EXISTS (
               SELECT 1
                 FROM unnest(
                          ARRAY[
                              'fsma.incidents',
                              'fsma.exchange_packages',
                              'fsma.organizations'
                          ]
                      ) AS disabled_table(table_name)
                WHERE has_table_privilege(
                          current_user,
                          disabled_table.table_name,
                          'SELECT,INSERT,UPDATE,DELETE'
                      )
           ) AS ok
)
SELECT relation_posture.ok,
       policy_manifest.manifest,
       policy_guards.ok,
       implicit_authority.ok,
       privilege_posture.ok AND disabled_surface_posture.ok
  FROM relation_posture,
       policy_manifest,
       policy_guards,
       implicit_authority,
       privilege_posture,
       disabled_surface_posture
"""

# SHA-256 of the exact sorted catalog tuples emitted above.  The source of
# truth remains v111's policy DDL; these fingerprints were generated by the
# direct-role migrated-PostgreSQL gate.  Whitespace alone is normalized.
_EXPECTED_RUNTIME_POLICY_MANIFEST_SHA256 = {
    "regengine": "37a00b9eeb2c2ff127c5c9bc4be6093e6c887a9e783ef891f28d419b0318b329",  # pragma: allowlist secret
    "regengine_sysadmin": "a7bacda65dc495ccaa238d7b01a53b409eb0136efb0f97d86328afe1dc209b41",  # pragma: allowlist secret
}


@dataclass(frozen=True)
class DatabaseIdentity:
    """Non-secret identity returned by PostgreSQL for cross-engine checks."""

    database: str
    server_address: str
    server_port: int


def _rls_enforcement_required() -> bool:
    """Production cannot opt out; staging can explicitly activate the gate."""
    return is_production() or os.getenv("REGENGINE_REQUIRE_RLS_ENFORCEMENT") == "1"


def _record_rls_metric(*, label: str, inert: bool) -> None:
    try:
        regengine_rls_enforcement_inert.labels(engine=label).set(1 if inert else 0)
    except Exception:  # pragma: no cover — metrics must never break boot
        pass


def _probe_with_retries(target_engine, *, label: str, statement, required: bool):
    attempts = 3 if required else 1
    probe_error: Exception | None = None
    row = None
    for attempt in range(1, attempts + 1):
        try:
            with target_engine.connect() as conn:
                row = conn.execute(statement).fetchone()
            probe_error = None
            break
        except Exception as exc:  # noqa: BLE001 - startup probe must classify all DB failures
            probe_error = exc
            logger.warning(
                "database_posture_probe_failed",
                engine=label,
                attempt=attempt,
                attempts=attempts,
                error=str(exc),
            )
            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 4))

    if probe_error is not None and required:
        raise RuntimeError(
            f"RLS enforcement required but the posture probe for the '{label}' engine "
            f"failed after {attempts} attempts ({probe_error}) — refusing to boot blind."
        ) from probe_error
    return row


def _runtime_cutover_canary(
    target_engine,
    *,
    label: str,
    expected_role: str,
    required: bool,
) -> bool:
    """Prove critical v111 catalog state using the runtime credential itself."""

    try:
        row = _probe_with_retries(
            target_engine,
            label=f"{label}-v111-catalog",
            statement=text(_RUNTIME_CUTOVER_CANARY_SQL),
            required=required,
        )
    except RuntimeError:
        _record_rls_metric(label=label, inert=True)
        raise

    if row is None:
        _record_rls_metric(label=label, inert=True)
        return False

    expected_policy_fingerprint = _EXPECTED_RUNTIME_POLICY_MANIFEST_SHA256.get(
        expected_role
    )
    policy_manifest = row[1]
    actual_policy_fingerprint = hashlib.sha256(
        str(policy_manifest).encode("utf-8")
    ).hexdigest()
    checks = (
        bool(row[0]),
        bool(expected_policy_fingerprint)
        and actual_policy_fingerprint == expected_policy_fingerprint,
        bool(row[2]),
        bool(row[3]),
        bool(row[4]),
    )
    if all(checks):
        return True

    _record_rls_metric(label=label, inert=True)
    logger.error(
        "runtime_cutover_catalog_canary_failed",
        engine=label,
        forced_rls=checks[0],
        policies=checks[1],
        policy_guards=checks[2],
        implicit_authority=checks[3],
        privileges=checks[4],
    )
    if required:
        raise RuntimeError(
            f"RLS enforcement required but the '{label}' engine failed the "
            "v111 catalog canary (FORCE RLS, policy, membership/ownership, or "
            "privilege drift) — refusing to boot."
        )
    return False


def check_rls_posture(
    target_engine=None,
    *,
    label: str = "shared",
    expected_role: str | None = None,
) -> str:
    """Validate that a runtime connection cannot bypass row-level security.

    Production always fails closed on a non-PostgreSQL engine, an unknown
    posture, a SUPERUSER/BYPASSRLS role, or a role other than
    ``expected_role``. ``REGENGINE_REQUIRE_RLS_ENFORCEMENT=1`` activates the
    same hard gate in staging. Other local/test environments retain the
    historical best-effort ``"unknown"``/``"inert"`` return values.
    """
    eng = target_engine if target_engine is not None else engine
    required = _rls_enforcement_required()
    if eng.dialect.name != "postgresql":
        if required:
            raise RuntimeError(
                f"RLS enforcement required but the '{label}' engine uses "
                f"{eng.dialect.name!r}, not PostgreSQL."
            )
        return "unknown"

    row = _probe_with_retries(
        eng,
        label=label,
        statement=text(
            "SELECT session_user, current_user, rolsuper, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        ),
        required=required,
    )
    if row is None:
        _record_rls_metric(label=label, inert=True)
        if required:
            raise RuntimeError(
                f"RLS enforcement required but the posture probe for the '{label}' engine "
                "returned no current role — refusing to boot blind."
            )
        return "unknown"

    session_role, rolname, rolsuper, rolbypassrls = row
    switched_role = session_role != rolname
    inert = bool(rolsuper) or bool(rolbypassrls) or switched_role
    if inert:
        _record_rls_metric(label=label, inert=True)
        logger.error(
            "rls_enforcement_inert",
            role=rolname,
            session_role=session_role,
            switched_role=switched_role,
            superuser=bool(rolsuper),
            bypassrls=bool(rolbypassrls),
            engine=label,
        )
        if required:
            raise RuntimeError(
                f"RLS enforcement required but the '{label}' engine connects as "
                f"session role {session_role!r} and effective role {rolname!r} "
                f"(superuser={bool(rolsuper)}, bypassrls={bool(rolbypassrls)})."
            )
        return "inert"

    if expected_role is not None and rolname != expected_role:
        _record_rls_metric(label=label, inert=True)
        logger.error(
            "database_runtime_role_unexpected",
            engine=label,
            role=rolname,
            expected_role=expected_role,
        )
        if required:
            raise RuntimeError(
                f"The '{label}' engine connects as role {rolname!r}; expected {expected_role!r}. "
                "Refusing to start with an unverified runtime role."
            )
        return "unknown"

    if expected_role in {"regengine", "regengine_sysadmin"}:
        if not _runtime_cutover_canary(
            eng,
            label=label,
            expected_role=expected_role,
            required=required,
        ):
            return "inert"

    _record_rls_metric(label=label, inert=False)
    logger.info("rls_enforcement_active", role=rolname, engine=label)
    return "enforced"


def _database_identity(target_engine, *, label: str, required: bool) -> DatabaseIdentity | None:
    if target_engine.dialect.name != "postgresql":
        if required:
            raise RuntimeError(f"Cannot verify database identity for non-PostgreSQL '{label}' engine.")
        return None

    row = _probe_with_retries(
        target_engine,
        label=label,
        statement=text("SELECT current_database(), inet_server_addr()::text, inet_server_port()"),
        required=required,
    )
    if row is None:
        if required:
            raise RuntimeError(f"Database identity probe for the '{label}' engine returned no row.")
        return None

    database, server_address, server_port = row
    if not database or not server_address or server_port is None:
        if required:
            raise RuntimeError(
                f"Database identity probe for the '{label}' engine was incomplete; "
                "refusing to compare credential-bearing URLs."
            )
        return None
    return DatabaseIdentity(str(database), str(server_address), int(server_port))


def validate_runtime_database_posture(shared_engine, admin_engine) -> dict[str, DatabaseIdentity | None]:
    """Validate both runtime roles and prove both engines target one database.

    The comparison uses values returned by PostgreSQL, never raw URLs, so
    credentials cannot leak into logs or exceptions. Production (and staging
    with ``REGENGINE_REQUIRE_RLS_ENFORCEMENT=1``) rejects unknown or mismatched
    identities.
    """
    required = _rls_enforcement_required()
    check_rls_posture(shared_engine, label="shared", expected_role="regengine")
    check_rls_posture(admin_engine, label="admin", expected_role="regengine_sysadmin")

    identities = {
        "shared": _database_identity(shared_engine, label="shared", required=required),
        "admin": _database_identity(admin_engine, label="admin", required=required),
    }
    if identities["shared"] != identities["admin"]:
        logger.error("runtime_database_identity_mismatch", **identities)
        if required:
            raise RuntimeError(
                "DATABASE_URL and ADMIN_DATABASE_URL resolve to different PostgreSQL databases; "
                "both runtime credentials must target the same migrated database."
            )
    else:
        logger.info("runtime_database_identity_verified", identity=identities["shared"])
    return identities


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
circuit_breaker = CircuitBreaker()


@contextmanager
def get_db():
    """Sync session generator with bulkhead, circuit breaker, and retry logic.

    The circuit breaker wraps a lightweight health-check query so that
    persistent DB failures trip the breaker.  The *session* itself is
    yielded directly — callers execute queries on it as normal.
    """
    with sync_bulkhead:
        db = SessionLocal()
        try:
            # Validate the connection through the circuit breaker
            retry_with_jitter(lambda: circuit_breaker.call(lambda: db.execute(text("SELECT 1"))))
            yield db
        finally:
            db.close()


@asynccontextmanager
async def get_db_async():
    """Async session generator with bulkhead, circuit breaker, and retry logic."""
    async with async_bulkhead:
        db = SessionLocal()
        try:
            retry_with_jitter(lambda: circuit_breaker.call(lambda: db.execute(text("SELECT 1"))))
            yield db
        finally:
            db.close()


# ── Convenience helpers for ingestion modules ──────────────────────────


def get_db_safe():
    """Get a plain SQLAlchemy session, returning None if unavailable.

    Use this for modules that manage their own commit/rollback/close lifecycle.
    The caller is responsible for calling db.close() when done.
    """
    try:
        return SessionLocal()
    except Exception as exc:
        logger.warning("db_session_unavailable", error=str(exc))
        return None


def get_db_session():
    """FastAPI dependency that yields a session with commit/rollback/close.

    Usage: db = Depends(get_db_session)
    """
    try:
        db = SessionLocal()
    except Exception:
        yield None
        return
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
