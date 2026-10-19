"""v111 — runtime role grants and pre-tenant API-key lookup.

The migration runs as ``MIGRATIONS_DATABASE_URL``'s schema owner. It is the
single production/CI artifact for the ``regengine`` and
``regengine_sysadmin`` cutover: no test-only grant block is required.

Revision ID: b71d9e4c2a60
Revises: 6f4c2a9d8b17
Create Date: 2026-08-03
"""

from __future__ import annotations

import os
from urllib.parse import unquote, urlsplit

from alembic import op

# revision identifiers, used by Alembic.
revision = "b71d9e4c2a60"  # pragma: allowlist secret
down_revision = "6f4c2a9d8b17"  # pragma: allowlist secret
branch_labels = None
depends_on = None


_TRUE_VALUES = frozenset({"1", "true", "yes", "on"})
_DEPLOYED_ENVIRONMENT_NAMES = frozenset({"production", "staging"})
_CLOUD_ENV_VARS = (
    "RAILWAY_ENVIRONMENT",
    "RAILWAY_ENVIRONMENT_NAME",
    "RAILWAY_ENVIRONMENT_ID",
    "RAILWAY_PROJECT_NAME",
    "RAILWAY_PROJECT_ID",
    "RAILWAY_SERVICE_NAME",
    "RAILWAY_SERVICE_ID",
    "VERCEL_ENV",
    "VERCEL_URL",
    "RENDER",
    "FLY_APP_NAME",
    "KUBERNETES_SERVICE_HOST",
)


def _migration_owner_enforcement_required() -> bool:
    """Return whether v111 must prove the dedicated migration owner.

    Legacy local scratch suites may still invoke Alembic as their disposable
    container superuser. Every supported deployment path is fail-closed:
    production/staging and any recognized cloud marker force this check, and
    the migration runner and cutover repair helper set the explicit flag.
    There is deliberately no environment variable that disables enforcement.
    """

    environment = (
        os.getenv("REGENGINE_ENV", "").strip().lower()
        or os.getenv("ENVIRONMENT", "").strip().lower()
        or os.getenv("ENV", "").strip().lower()
    )
    return (
        os.getenv("REGENGINE_ENFORCE_MIGRATION_ROLE", "").strip().lower() in _TRUE_VALUES
        or environment in _DEPLOYED_ENVIRONMENT_NAMES
        or any(os.getenv(marker, "").strip() for marker in _CLOUD_ENV_VARS)
    )


def _migration_url_role() -> str:
    migration_url = os.getenv("MIGRATIONS_DATABASE_URL", "").strip()
    if not migration_url:
        return ""
    try:
        return unquote(urlsplit(migration_url).username or "").strip()
    except ValueError as exc:
        raise RuntimeError(
            "MIGRATIONS_DATABASE_URL is not a parseable PostgreSQL URL; cannot prove the migration role"
        ) from exc


def _expected_migration_role(url_role: str) -> str:
    configured_role = os.getenv("REGENGINE_MIGRATIONS_ROLE", "").strip()
    if configured_role and url_role and configured_role != url_role:
        raise RuntimeError("REGENGINE_MIGRATIONS_ROLE must match the login identity in MIGRATIONS_DATABASE_URL")
    return configured_role or url_role


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


MIGRATION_OWNER_ENFORCEMENT_REQUIRED = _migration_owner_enforcement_required()
MIGRATION_URL_ROLE = _migration_url_role()
EXPECTED_MIGRATION_ROLE = _expected_migration_role(MIGRATION_URL_ROLE)
if MIGRATION_OWNER_ENFORCEMENT_REQUIRED and not MIGRATION_URL_ROLE:
    raise RuntimeError(
        "cannot determine the required migration role: "
        "MIGRATIONS_DATABASE_URL must contain the login identity "
        "(REGENGINE_MIGRATIONS_ROLE may additionally pin the same identity)"
    )


def _build_migration_owner_posture() -> str:
    if not MIGRATION_OWNER_ENFORCEMENT_REQUIRED:
        return ""

    expected_role = _sql_literal(EXPECTED_MIGRATION_ROLE)
    return f"""
DO $migration_owner$
DECLARE
    expected_owner constant text := {expected_role};
    migration_role record;
    membership_row record;
    schema_name text;
    schema_owner text;
    object_row record;
BEGIN
    IF session_user <> expected_owner OR current_user <> expected_owner THEN
        RAISE EXCEPTION
            'v111 expected session login and effective role %, connected as session_user=% current_user=%',
            expected_owner,
            session_user,
            current_user;
    END IF;

    SELECT rolname, rolcanlogin, rolsuper, rolbypassrls, rolcreatedb,
           rolcreaterole, rolreplication
      INTO migration_role
      FROM pg_roles
     WHERE rolname = current_user;

    IF NOT FOUND OR NOT migration_role.rolcanlogin THEN
        RAISE EXCEPTION
            'migration role % must be a dedicated LOGIN role', current_user;
    END IF;
    IF migration_role.rolsuper
       OR migration_role.rolbypassrls
       OR migration_role.rolcreatedb
       OR migration_role.rolcreaterole
       OR migration_role.rolreplication THEN
        RAISE EXCEPTION
            'migration role % has forbidden elevated attributes', current_user;
    END IF;

    -- Either direction is unsafe: inherited authority enlarges the migration
    -- credential, while granting the owner role to another principal leaks
    -- schema-owner authority outside the audited pre-deploy job.
    SELECT member_role.rolname AS member_name,
           granted_role.rolname AS granted_name
      INTO membership_row
      FROM pg_auth_members AS membership
      JOIN pg_roles AS member_role ON member_role.oid = membership.member
      JOIN pg_roles AS granted_role ON granted_role.oid = membership.roleid
     WHERE member_role.rolname = current_user
        OR granted_role.rolname = current_user
     ORDER BY member_role.rolname, granted_role.rolname
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'migration role % must have no incoming or outgoing memberships: % inherits %',
            current_user,
            membership_row.member_name,
            membership_row.granted_name;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_database
         WHERE datname = current_database()
           AND datdba = (SELECT oid FROM pg_roles WHERE rolname = current_user)
    ) THEN
        RAISE EXCEPTION
            'migration role % must own database %',
            current_user,
            current_database();
    END IF;

    FOREACH schema_name IN ARRAY ARRAY['public', 'fsma', 'audit', 'dlq', 'ingestion'] LOOP
        SELECT pg_get_userbyid(nspowner)
          INTO schema_owner
          FROM pg_namespace
         WHERE nspname = schema_name;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'required protected schema % is missing', schema_name;
        END IF;
        IF schema_owner <> current_user
           AND NOT (
               schema_name = 'public'
               AND schema_owner = 'pg_database_owner'
           ) THEN
            RAISE EXCEPTION
                'protected schema % is owned by %, expected migration owner %',
                schema_name,
                schema_owner,
                current_user;
        END IF;
    END LOOP;

    -- Include indexes as well as ACL-bearing relations: an unexpected owner
    -- can ALTER or DROP an object even when no grant is visible in an ACL.
    SELECT CASE
               WHEN c.relkind = 'S' THEN 'sequence'
               WHEN c.relkind IN ('i', 'I') THEN 'index'
               ELSE 'relation'
           END AS object_kind,
           format('%I.%I', n.nspname, c.relname) AS object_name,
           pg_get_userbyid(c.relowner) AS owner_name
      INTO object_row
      FROM pg_class AS c
      JOIN pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
       AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f', 'i', 'I')
       AND c.relowner <> (SELECT oid FROM pg_roles WHERE rolname = current_user)
     ORDER BY n.nspname, c.relname
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'protected % % is owned by %, expected migration owner %',
            object_row.object_kind,
            object_row.object_name,
            object_row.owner_name,
            current_user;
    END IF;

    -- Trusted PostgreSQL extensions can leave member functions owned by the
    -- bootstrap provider even when the extension itself belongs to the DB
    -- owner. Treat that extension as the authority boundary; every ordinary
    -- application function/procedure must be owned directly by the migrator.
    SELECT 'extension'::text AS object_kind,
           e.extname::text AS object_name,
           pg_get_userbyid(e.extowner) AS owner_name
      INTO object_row
      FROM pg_extension AS e
      JOIN pg_namespace AS n ON n.oid = e.extnamespace
     WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
       AND e.extowner <> (SELECT oid FROM pg_roles WHERE rolname = current_user)
     ORDER BY e.extname
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'protected extension % is owned by %, expected migration owner %',
            object_row.object_name,
            object_row.owner_name,
            current_user;
    END IF;

    SELECT 'function'::text AS object_kind,
           format(
               '%I.%I(%s)',
               n.nspname,
               p.proname,
               pg_get_function_identity_arguments(p.oid)
           ) AS object_name,
           pg_get_userbyid(p.proowner) AS owner_name
      INTO object_row
      FROM pg_proc AS p
      JOIN pg_namespace AS n ON n.oid = p.pronamespace
     WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
       AND p.proowner <> (SELECT oid FROM pg_roles WHERE rolname = current_user)
       AND NOT EXISTS (
           SELECT 1
             FROM pg_depend AS dependency
             JOIN pg_extension AS extension
               ON extension.oid = dependency.refobjid
            WHERE dependency.classid = 'pg_proc'::regclass
              AND dependency.objid = p.oid
              AND dependency.deptype = 'e'
              AND extension.extowner = (
                  SELECT oid FROM pg_roles WHERE rolname = current_user
              )
       )
     ORDER BY n.nspname, p.proname, p.oid
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'protected function % is owned by %, expected migration owner %',
            object_row.object_name,
            object_row.owner_name,
            current_user;
    END IF;
END
$migration_owner$;
"""


_MIGRATION_OWNER_POSTURE = _build_migration_owner_posture()


_ROLE_POSTURE = """
DO $cutover$
DECLARE
    role_name text;
    role_row record;
    membership_row record;
    owned_object record;
BEGIN
    IF current_user IN ('regengine', 'regengine_sysadmin') THEN
        RAISE EXCEPTION
            'v111 must run as the migration/schema owner, not runtime role %',
            current_user;
    END IF;

    FOREACH role_name IN ARRAY ARRAY['regengine', 'regengine_sysadmin'] LOOP
        SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole,
               rolreplication
          INTO role_row
          FROM pg_roles
         WHERE rolname = role_name;

        IF NOT FOUND THEN
            RAISE EXCEPTION 'required runtime role % does not exist', role_name;
        END IF;
        IF role_row.rolsuper
           OR role_row.rolbypassrls
           OR role_row.rolcreatedb
           OR role_row.rolcreaterole
           OR role_row.rolreplication THEN
            RAISE EXCEPTION
                'runtime role % has forbidden elevated attributes', role_name;
        END IF;
    END LOOP;

    -- Provider administration must provision the roles, CONNECT grants, and
    -- ownership before Alembic runs. A schema owner does not necessarily have
    -- database GRANT OPTION, CREATEROLE, or ADMIN OPTION, so this migration
    -- validates the topology but never repairs it with elevated authority.
    SELECT member_role.rolname AS member_name,
           granted_role.rolname AS granted_name
      INTO membership_row
      FROM pg_auth_members AS membership
      JOIN pg_roles AS member_role ON member_role.oid = membership.member
      JOIN pg_roles AS granted_role ON granted_role.oid = membership.roleid
     WHERE member_role.rolname IN ('regengine', 'regengine_sysadmin')
        OR granted_role.rolname IN ('regengine', 'regengine_sysadmin')
     ORDER BY member_role.rolname, granted_role.rolname
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'runtime roles must have no incoming or outgoing memberships: % inherits %',
            membership_row.member_name,
            membership_row.granted_name;
    END IF;

    -- Ownership is an implicit privilege that REVOKE cannot remove. Reject a
    -- stale runtime-owned schema, relation/sequence, function, or database so
    -- the closed ACL inventory is the whole authority surface rather than a
    -- misleading subset of it.
    SELECT object_kind, object_name
      INTO owned_object
      FROM (
          SELECT 'database'::text AS object_kind,
                 datname::text AS object_name
            FROM pg_database
           WHERE datname = current_database()
             AND pg_get_userbyid(datdba) IN ('regengine', 'regengine_sysadmin')
          UNION ALL
          SELECT 'schema', nspname
            FROM pg_namespace
           WHERE nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
             AND pg_get_userbyid(nspowner) IN ('regengine', 'regengine_sysadmin')
          UNION ALL
          SELECT CASE WHEN c.relkind = 'S' THEN 'sequence' ELSE 'relation' END,
                 format('%I.%I', n.nspname, c.relname)
            FROM pg_class AS c
            JOIN pg_namespace AS n ON n.oid = c.relnamespace
           WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
             AND c.relkind IN ('r', 'p', 'S', 'v', 'm', 'f')
             AND pg_get_userbyid(c.relowner) IN ('regengine', 'regengine_sysadmin')
          UNION ALL
          SELECT 'function',
                 format(
                     '%I.%I(%s)',
                     n.nspname,
                     p.proname,
                     pg_get_function_identity_arguments(p.oid)
                 )
            FROM pg_proc AS p
            JOIN pg_namespace AS n ON n.oid = p.pronamespace
           WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
             AND pg_get_userbyid(p.proowner) IN ('regengine', 'regengine_sysadmin')
      ) AS runtime_owned
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'runtime roles must not own protected database objects: % %',
            owned_object.object_kind,
            owned_object.object_name;
    END IF;
END
$cutover$;
"""


TARGET_SCHEMAS = ("public", "fsma", "audit", "dlq", "ingestion")

# This is intentionally a closed inventory, not a schema wildcard.  A new
# table receives no runtime access until a migration adds an explicit grant
# and the direct-role CI matrix classifies it.  ``alembic_version`` (and a
# legacy ``schema_migrations`` table, if drift created one) are deployment
# metadata and are always denied to both runtime roles.
#
# scripts/run-migrations.sh reapplies CUTOVER_STATEMENTS after EVERY deploy
# (scripts/apply_runtime_role_cutover.py), which revokes every runtime table,
# column, sequence and function privilege in TARGET_SCHEMAS and rebuilds only
# what these inventories and _FUNCTION_GRANTS list. A later migration's GRANT
# on an object in these schemas therefore lasts until the next deploy unless
# it is also registered here (see v121 label_charges, v126).
APPLICATION_TABLES = {
    "audit": (
        "rls_policy_restoration_log",
        "sysadmin_access_log",
    ),
    "dlq": ("webhook_failures",),
    "fsma": (
        "agent_artifact_reviews",
        "agent_artifacts",
        "audit_log",
        "canonical_entities",
        "chain_verification_log",
        "compliance_alerts",
        "compliance_evidence_snapshots",
        "compliance_snapshots",
        "correction_patches",
        "critical_tracking_events",
        "cte_events",
        "cte_kdes",
        "cte_kdes_backfill_log_v059",
        "entity_aliases",
        "entity_merge_history",
        "evidence_attachments",
        "exception_attachments",
        "exception_cases",
        "exception_comments",
        "exception_signoffs",
        "exchange_packages",
        "fda_export_log",
        "fda_sla_requests",
        "fsma_audit_trail",
        "hash_chain",
        "identity_review_queue",
        "incidents",
        "inflow_workbench_commit_decisions",
        "inflow_workbench_fix_items",
        "inflow_workbench_runs",
        "inflow_workbench_scenarios",
        "ingestion_run_receipts",
        "ingestion_runs",
        "key_data_elements",
        "locations",
        "manifest_blobs",
        "manifest_records",
        "mock_audit_drills",
        "notification_outbox",
        "organizations",
        "products",
        "recall_assessments",
        "remediation_cases",
        "remediation_tokens",
        "request_cases",
        "request_signoffs",
        "response_packages",
        "rule_audit_log",
        "rule_definitions",
        "rule_evaluation_deadletter",
        "rule_evaluations",
        "rule_rejections",
        "submission_log",
        "supplier_integration_profiles",
        "suppliers",
        "task_queue",
        "tenant_data",
        "tenant_exchanges",
        "tenant_notification_prefs",
        "tenant_onboarding",
        "tenant_portal_links",
        "tenant_products",
        "tenant_seed_state",
        "tenant_settings",
        "tenant_suppliers",
        "tenant_team_members",
        "traceability_events",
        "transformation_links",
    ),
    "ingestion": (
        "audit_log",
        "documents",
        "jobs",
    ),
    "public": (
        "admin_mfa_recovery_codes",
        "api_keys",
        "audit_log_buffer",
        "audit_logs",
        "auth_challenges",
        "compliance_alerts",
        "compliance_notifications",
        "compliance_status_log",
        "controls",
        "food_traceability_list",
        "funnel_events",
        "graph_outbox",
        "invites",
        "memberships",
        "obligation_cte_rules",
        "obligations",
        "organization_memberships",
        "organizations",
        "pcos_authority_documents",
        "pcos_extracted_facts",
        "pcos_fact_citations",
        "regulations",
        "review_items",
        "roles",
        "sandbox_shares",
        "scheduler_job_runs",
        "scheduler_seen_items",
        "sessions",
        "supplier_cte_events",
        "supplier_facilities",
        "supplier_facility_ftl_categories",
        "supplier_funnel_events",
        "supplier_traceability_lots",
        "tenant_compliance_status",
        "tenant_product_profile",
        "tenants",
        "tool_leads",
        "user_emails",
        "users",
        "webauthn_challenges",
        "webauthn_credentials",
        "webhook_outbox",
    ),
}

APPLICATION_SEQUENCES = {
    "audit": (
        "rls_policy_restoration_log_id_seq",
        "sysadmin_access_log_id_seq",
    ),
    "fsma": (
        "fsma_audit_trail_id_seq",
        "hash_chain_id_seq",
        "task_queue_id_seq",
    ),
    "ingestion": ("audit_log_id_seq",),
    "public": (
        "api_keys_id_seq",
        "audit_logs_id_seq",
        "funnel_events_id_seq",
        "graph_outbox_id_seq",
        "webhook_outbox_id_seq",
    ),
}

# Ordinary service credentials deliberately omit every identity and control-
# plane table (users, email identities, organizations/memberships, sessions,
# WebAuthn/challenges, roles/reviews, admin recovery codes, and lead intake).
# The admin service uses its independently pooled ``regengine_sysadmin``
# credential for those surfaces.
REGENGINE_TABLE_GRANTS = {
    "ingestion.audit_log": ("SELECT", "INSERT"),
    "ingestion.documents": ("SELECT", "INSERT"),
    "ingestion.jobs": ("SELECT", "INSERT", "UPDATE"),
    "public.api_keys": ("SELECT",),
    "public.audit_logs": ("SELECT", "INSERT"),
    "public.compliance_alerts": ("SELECT", "INSERT"),
    "public.controls": ("SELECT",),
    "public.food_traceability_list": ("SELECT",),
    "public.funnel_events": ("SELECT", "INSERT"),
    "public.obligation_cte_rules": ("SELECT",),
    "public.obligations": ("SELECT",),
    "public.regulations": ("SELECT",),
    "public.scheduler_job_runs": ("SELECT", "INSERT", "UPDATE"),
    "public.scheduler_seen_items": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "public.tenant_compliance_status": ("SELECT", "INSERT", "UPDATE"),
    "public.tenant_product_profile": ("SELECT",),
}

# Explicit mutable data-plane inventory for the enabled ingestion/workflow
# routers.  Disabled/administrative surfaces (incidents, exchange packages,
# mock drills, tenant exchanges, compliance snapshots, and legacy tables) are
# intentionally absent and therefore receive no ordinary runtime ACL.
REGENGINE_FSMA_MUTABLE_TABLES = (
    "exception_cases",
    "inflow_workbench_fix_items",
    "request_cases",
    "rule_evaluation_deadletter",
    "tenant_onboarding",
    "tenant_portal_links",
    "tenant_data",
)
for _table_name in REGENGINE_FSMA_MUTABLE_TABLES:
    REGENGINE_TABLE_GRANTS[f"fsma.{_table_name}"] = (
        "SELECT",
        "INSERT",
        "UPDATE",
    )
REGENGINE_TABLE_GRANTS.update(
    {
        "fsma.agent_artifacts": ("INSERT",),
        "fsma.canonical_entities": ("SELECT",),
        "fsma.chain_verification_log": ("SELECT", "INSERT"),
        "fsma.compliance_alerts": ("SELECT", "INSERT"),
        "fsma.compliance_evidence_snapshots": ("SELECT", "INSERT", "UPDATE"),
        "fsma.cte_events": ("SELECT", "INSERT", "DELETE"),
        "fsma.cte_kdes": ("SELECT", "INSERT"),
        "fsma.entity_aliases": ("SELECT",),
        "fsma.evidence_attachments": ("SELECT",),
        "fsma.exception_comments": ("SELECT", "INSERT"),
        "fsma.exception_signoffs": ("SELECT", "INSERT"),
        "fsma.fda_export_log": ("SELECT", "INSERT"),
        "fsma.fda_sla_requests": ("SELECT", "INSERT", "UPDATE"),
        "fsma.fsma_audit_trail": ("SELECT", "INSERT"),
        "fsma.hash_chain": ("SELECT", "INSERT"),
        "fsma.identity_review_queue": ("SELECT",),
        "fsma.inflow_workbench_commit_decisions": ("SELECT", "INSERT"),
        "fsma.inflow_workbench_runs": ("SELECT", "INSERT"),
        "fsma.inflow_workbench_scenarios": ("SELECT", "INSERT"),
        "fsma.ingestion_run_receipts": ("INSERT",),
        "fsma.ingestion_runs": ("SELECT", "INSERT", "UPDATE"),
        # v121 -- per-label FSMA 204 billing. Claimed via INSERT ... ON
        # CONFLICT DO NOTHING (SELECT to read back an existing claim,
        # UPDATE to record the Stripe outcome); never deleted.
        "fsma.label_charges": ("SELECT", "INSERT", "UPDATE"),
        "fsma.notification_outbox": ("SELECT", "UPDATE"),
        "fsma.products": ("SELECT", "INSERT", "UPDATE"),
        "fsma.remediation_tokens": ("SELECT", "INSERT", "UPDATE"),
        "fsma.request_signoffs": ("SELECT", "INSERT"),
        "fsma.response_packages": ("SELECT", "INSERT"),
        "fsma.rule_definitions": ("SELECT",),
        "fsma.rule_evaluations": ("SELECT", "INSERT"),
        "fsma.rule_rejections": ("INSERT",),
        "fsma.submission_log": ("SELECT", "INSERT"),
        "fsma.supplier_integration_profiles": ("SELECT",),
        "fsma.task_queue": ("SELECT", "INSERT"),
        "fsma.tenant_suppliers": ("SELECT",),
        "fsma.tenant_seed_state": ("SELECT",),
        "fsma.traceability_events": ("SELECT", "INSERT", "UPDATE"),
        "fsma.transformation_links": ("SELECT", "INSERT"),
    }
)

REGENGINE_COLUMN_GRANTS = {
    # Successful pre-authentication may maintain only usage telemetry.  It
    # cannot change identity, tenant, scopes, status, expiry, limits, or hash.
    "public.api_keys": {"UPDATE": ("last_used_at", "total_requests")},
    # Runtime validation/background work may test one credential-bound UUID,
    # but tenant names, settings, and webhook configuration remain control-
    # plane data.
    "public.tenants": {"SELECT": ("id",)},
    # v126 -- POST /api/v1/ingest/csv (#3122) retains each upload verbatim
    # in the ingest transaction (webhook_compat._open_ingestion_run). INSERT
    # is limited to the columns that statement writes, so storage_url and
    # created_at cannot be forged; reads, updates and deletes stay denied
    # (the disabled remediation surface keeps its contract). The composite
    # (ingestion_run_id, tenant_id) foreign key pins a blob to its own
    # tenant's run.
    "fsma.manifest_blobs": {
        "INSERT": (
            "ingestion_run_id",
            "tenant_id",
            "raw_bytes",
            "sha256",
            "original_filename",
            "content_type",
            "uploaded_by",
        )
    },
    # v126 -- the agent-artifact worker (shared.agent_task_bridge) reads only
    # what its statements need: the ON CONFLICT (artifact_id, tenant_id)
    # arbiter plus RETURNING artifact_id, and the receipt trigger's
    # chain-head lookup plus the bridge's RETURNING. Both tables stay
    # append-only for this role (no UPDATE/DELETE).
    "fsma.agent_artifacts": {"SELECT": ("artifact_id", "tenant_id")},
    "fsma.ingestion_run_receipts": {
        "SELECT": (
            "receipt_id",
            "tenant_id",
            "ingestion_run_id",
            "sequence_num",
            "receipt_hash",
        )
    },
}

REGENGINE_SEQUENCE_GRANTS = {
    "fsma.fsma_audit_trail_id_seq": ("USAGE", "SELECT"),
    "fsma.hash_chain_id_seq": ("USAGE", "SELECT"),
    "fsma.task_queue_id_seq": ("USAGE", "SELECT"),
    "ingestion.audit_log_id_seq": ("USAGE", "SELECT"),
    "public.audit_logs_id_seq": ("USAGE", "SELECT"),
    "public.funnel_events_id_seq": ("USAGE", "SELECT"),
}

# The control-plane credential has its own closed caller-derived inventory.
# In particular it cannot mutate or delete append-only evidence, optional
# data-plane tables, migration metadata, or any future object.  Column grants
# below intentionally narrow high-impact UPDATE operations.
REGENGINE_SYSADMIN_TABLE_GRANTS = {
    "dlq.webhook_failures": ("SELECT",),
    "fsma.agent_artifact_reviews": ("SELECT", "INSERT", "UPDATE"),
    "fsma.agent_artifacts": ("SELECT",),
    "fsma.compliance_alerts": ("SELECT",),
    "fsma.fsma_audit_trail": ("SELECT",),
    "fsma.ingestion_run_receipts": ("SELECT",),
    "fsma.ingestion_runs": ("SELECT",),
    # Global queue coordination is a control-plane operation.  DELETE is
    # restricted to the 30-day terminal-row retention job by application
    # logic; the role has no INSERT privilege, so producers remain tenant
    # scoped through DATABASE_URL.
    "fsma.task_queue": ("SELECT", "DELETE"),
    "public.admin_mfa_recovery_codes": ("SELECT", "DELETE"),
    "public.api_keys": ("SELECT", "INSERT"),
    "public.audit_log_buffer": ("SELECT",),
    "public.audit_logs": ("SELECT", "INSERT"),
    "public.auth_challenges": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "public.compliance_alerts": ("SELECT", "INSERT", "UPDATE"),
    "public.funnel_events": ("SELECT",),
    "public.graph_outbox": ("SELECT", "INSERT", "UPDATE"),
    "public.invites": ("SELECT", "INSERT", "UPDATE"),
    "public.memberships": ("SELECT", "INSERT", "UPDATE"),
    "public.organization_memberships": ("SELECT", "INSERT", "DELETE"),
    "public.organizations": ("SELECT", "INSERT", "UPDATE"),
    "public.review_items": ("SELECT", "INSERT", "UPDATE"),
    "public.roles": ("SELECT",),
    "public.sessions": ("SELECT", "INSERT", "UPDATE"),
    "public.supplier_cte_events": ("SELECT", "INSERT", "DELETE"),
    "public.supplier_facilities": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "public.supplier_facility_ftl_categories": (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    ),
    "public.supplier_funnel_events": ("SELECT", "INSERT", "DELETE"),
    "public.supplier_traceability_lots": (
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    ),
    "public.tenant_compliance_status": ("SELECT", "INSERT", "UPDATE"),
    "public.tenant_product_profile": ("SELECT", "INSERT", "UPDATE"),
    "public.tenants": ("SELECT", "INSERT"),
    "public.tool_leads": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "public.user_emails": ("SELECT", "INSERT", "UPDATE"),
    "public.users": ("SELECT", "INSERT", "UPDATE"),
    "public.webauthn_challenges": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "public.webauthn_credentials": ("SELECT", "INSERT", "UPDATE", "DELETE"),
    "public.webhook_outbox": ("SELECT", "INSERT", "UPDATE"),
}

REGENGINE_SYSADMIN_COLUMN_GRANTS = {
    "dlq.webhook_failures": {
        "UPDATE": (
            "status",
            "retry_count",
            "next_retry_at",
            "updated_at",
            "replayed_at",
            "replay_attempts",
        )
    },
    "fsma.task_queue": {
        "UPDATE": (
            "status",
            "attempts",
            "last_error",
            "locked_by",
            "locked_until",
            "started_at",
            "completed_at",
            "scheduled_at",
        )
    },
    "public.admin_mfa_recovery_codes": {"UPDATE": ("used_at",)},
    "public.api_keys": {
        "UPDATE": (
            "enabled",
            "revoked_at",
            "revoked_by",
            "revoke_reason",
            "updated_at",
        )
    },
    "public.audit_log_buffer": {"UPDATE": ("replayed_at", "replay_attempts")},
    # ``name`` lets PATCH /admin/organizations/{org_id} rename the tenant that
    # shares the organization's ID. v133 applies the same grant to databases
    # already past v111; this inventory keeps it across the cutover rerun.
    "public.tenants": {"UPDATE": ("name", "settings", "updated_at")},
}

REGENGINE_SYSADMIN_SEQUENCE_GRANTS = {
    "public.api_keys_id_seq": ("USAGE", "SELECT"),
    "public.audit_logs_id_seq": ("USAGE", "SELECT"),
    "public.graph_outbox_id_seq": ("USAGE", "SELECT"),
    "public.webhook_outbox_id_seq": ("USAGE", "SELECT"),
}


def _grant_sql(role: str, object_name: str, privileges: tuple[str, ...], kind: str) -> str:
    grant = f"GRANT {', '.join(privileges)} ON {kind} {object_name} TO {role};"
    # Guarded so a table/sequence can be registered here ahead of the later
    # migration that actually creates it (v121 registers fsma.label_charges
    # this way -- see REGENGINE_TABLE_GRANTS below -- so the post-deploy
    # cutover script, scripts/apply_runtime_role_cutover.py, which re-imports
    # and re-executes this exact module against an already-fully-migrated
    # DB, grants it correctly there). Without the guard, replaying the FULL
    # migration chain from scratch runs THIS revision's own upgrade() at its
    # own chain position -- before the later revision has created the
    # object yet -- and a bare GRANT aborts the whole run with
    # UndefinedTable/UndefinedObject. to_regclass resolves both tables and
    # sequences, so one guard covers both; it is a no-op for every entry
    # here that predates v111, since all of those objects already exist by
    # the time this revision runs.
    return f"""
DO $$
BEGIN
    IF to_regclass('{object_name}') IS NOT NULL THEN
        EXECUTE '{grant}';
    END IF;
END
$$;
"""


def _build_object_grants() -> str:
    statements = [_OBJECT_GRANT_BASE]
    for object_name, privileges in sorted(REGENGINE_TABLE_GRANTS.items()):
        statements.append(_grant_sql("regengine", object_name, privileges, "TABLE"))
    for object_name, privilege_map in sorted(REGENGINE_COLUMN_GRANTS.items()):
        for privilege, columns in sorted(privilege_map.items()):
            statements.append(f"GRANT {privilege} ({', '.join(columns)}) ON TABLE {object_name} TO regengine;")
    for object_name, privileges in sorted(REGENGINE_SEQUENCE_GRANTS.items()):
        statements.append(_grant_sql("regengine", object_name, privileges, "SEQUENCE"))

    for object_name, privileges in sorted(REGENGINE_SYSADMIN_TABLE_GRANTS.items()):
        statements.append(_grant_sql("regengine_sysadmin", object_name, privileges, "TABLE"))
    for object_name, privilege_map in sorted(REGENGINE_SYSADMIN_COLUMN_GRANTS.items()):
        for privilege, columns in sorted(privilege_map.items()):
            statements.append(f"GRANT {privilege} ({', '.join(columns)}) ON TABLE {object_name} TO regengine_sysadmin;")
    for object_name, privileges in sorted(REGENGINE_SYSADMIN_SEQUENCE_GRANTS.items()):
        statements.append(_grant_sql("regengine_sysadmin", object_name, privileges, "SEQUENCE"))
    return "\n".join(statements)


_OBJECT_GRANT_BASE = """
DO $cutover$
DECLARE
    schema_name text;
    object_row record;
BEGIN
    FOREACH schema_name IN ARRAY ARRAY['public', 'fsma', 'audit', 'dlq', 'ingestion'] LOOP
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = schema_name) THEN
            -- Start from zero.  This also removes grants left by the retired
            -- wildcard runbook before the closed allowlist below is applied.
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON SCHEMA %I FROM PUBLIC, regengine, regengine_sysadmin',
                schema_name
            );
            EXECUTE format(
                'GRANT USAGE ON SCHEMA %I TO regengine, regengine_sysadmin',
                schema_name
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA %I '
                'FROM PUBLIC, regengine, regengine_sysadmin',
                schema_name
            );
            EXECUTE format(
                'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA %I '
                'FROM PUBLIC, regengine, regengine_sysadmin',
                schema_name
            );

            -- Table-level REVOKE does not clear attacl entries created by a
            -- historical column GRANT. Remove every current per-column ACL
            -- before rebuilding the two explicit column allowlists.
            FOR object_row IN
                SELECT c.relname, a.attname
                  FROM pg_class AS c
                  JOIN pg_namespace AS n ON n.oid = c.relnamespace
                  JOIN pg_attribute AS a ON a.attrelid = c.oid
                 WHERE n.nspname = schema_name
                   AND c.relkind IN ('r', 'p')
                   AND a.attnum > 0
                   AND NOT a.attisdropped
            LOOP
                EXECUTE format(
                    'REVOKE ALL PRIVILEGES (%I) ON TABLE %I.%I '
                    'FROM PUBLIC, regengine, regengine_sysadmin',
                    object_row.attname,
                    schema_name,
                    object_row.relname
                );
            END LOOP;

            -- New objects are inaccessible until an audited migration names
            -- them.  Never restore automatic future-table or sequence CRUD.
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA %I '
                'REVOKE ALL PRIVILEGES ON TABLES '
                'FROM PUBLIC, regengine, regengine_sysadmin',
                schema_name
            );
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA %I '
                'REVOKE ALL PRIVILEGES ON SEQUENCES '
                'FROM PUBLIC, regengine, regengine_sysadmin',
                schema_name
            );

            -- PostgreSQL grants PUBLIC function execution by default. Future
            -- application-callable helpers must opt in explicitly in their
            -- migration; no runtime role receives a blanket function grant.
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA %I '
                'REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC',
                schema_name
            );
            EXECUTE format(
                'ALTER DEFAULT PRIVILEGES IN SCHEMA %I '
                'REVOKE EXECUTE ON FUNCTIONS FROM regengine, regengine_sysadmin',
                schema_name
            );
        END IF;
    END LOOP;

    -- Every migrated object is schema-owner controlled.  An unexpected owner
    -- could retain or re-grant privileges outside this cutover's authority.
    FOR object_row IN
        SELECT n.nspname, c.relname, pg_get_userbyid(c.relowner) AS owner_name
          FROM pg_class AS c
          JOIN pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
           AND c.relkind IN ('r', 'p', 'S')
           AND pg_get_userbyid(c.relowner) <> current_user
    LOOP
        RAISE EXCEPTION 'object %.% is owned by %, expected migration owner %',
            object_row.nspname, object_row.relname,
            object_row.owner_name, current_user;
    END LOOP;
END
$cutover$;
"""

_OBJECT_GRANTS = _build_object_grants()


_SEED_FUNCTION = """
-- Onboarding needs to copy a fixed, migration-owned demo template while the
-- caller remains scoped to the new tenant.  SECURITY DEFINER is deliberately
-- narrow: exact login-role check, fail-hard tenant equality, fixed trusted
-- search_path, no dynamic SQL, and one immutable source tenant.
--
-- Keep the function owned by the schema/migration owner.  Transferring it to
-- a runtime role makes a later owner-run migration unable to replace it.  The
-- owner-only RLS policies below do not enlarge the migration credential's
-- authority (it already owns the schema); they only let this narrow definer
-- execute when that owner is itself a NOSUPERUSER/NOBYPASSRLS role.
DROP FUNCTION IF EXISTS public.seed_obligations_for_tenant(uuid);
CREATE OR REPLACE FUNCTION public.seed_obligations_for_tenant(p_tenant_id uuid)
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public, fsma, pg_temp
AS $function$
DECLARE
    demo_tenant constant uuid := '5946c58f-ddf9-4db0-9baa-acb11c6fce91';
    reg_count integer;
BEGIN
    IF session_user <> 'regengine' THEN
        RAISE EXCEPTION 'seed_obligations_for_tenant is restricted to regengine';
    END IF;
    IF p_tenant_id IS NULL OR p_tenant_id <> public.get_tenant_context() THEN
        RAISE EXCEPTION 'seed tenant must equal the active tenant context';
    END IF;

    SELECT pg_catalog.count(*)
      INTO reg_count
      FROM public.regulations
     WHERE tenant_id = p_tenant_id;

    IF reg_count = 0 THEN
        INSERT INTO public.regulations (
            id, tenant_id, source_name, citation, section, text, effective_date
        )
        SELECT pg_catalog.gen_random_uuid(), p_tenant_id,
               source_name, citation, section, text, effective_date
          FROM public.regulations
         WHERE tenant_id = demo_tenant;

        INSERT INTO public.obligations (
            id, tenant_id, regulation_id, title, description,
            risk_category, status, due_date, created_at
        )
        SELECT pg_catalog.gen_random_uuid(), p_tenant_id,
               (
                   SELECT nr.id
                     FROM public.regulations AS nr
                     JOIN public.regulations AS dr ON dr.id = source_obligation.regulation_id
                    WHERE nr.tenant_id = p_tenant_id
                      AND nr.citation = dr.citation
                    LIMIT 1
               ),
               source_obligation.title,
               source_obligation.description,
               source_obligation.risk_category,
               source_obligation.status,
               source_obligation.due_date,
               pg_catalog.now()
          FROM public.obligations AS source_obligation
         WHERE source_obligation.tenant_id = demo_tenant;

        INSERT INTO public.controls (
            id, tenant_id, obligation_id, title, description,
            control_type, frequency, status, created_at
        )
        SELECT pg_catalog.gen_random_uuid(), p_tenant_id,
               (
                   SELECT target_obligation.id
                     FROM public.obligations AS target_obligation
                     JOIN public.obligations AS source_obligation
                       ON source_obligation.id = source_control.obligation_id
                    WHERE target_obligation.tenant_id = p_tenant_id
                      AND target_obligation.title = source_obligation.title
                    LIMIT 1
               ),
               source_control.title,
               source_control.description,
               source_control.control_type,
               source_control.frequency,
               source_control.status,
               pg_catalog.now()
          FROM public.controls AS source_control
         WHERE source_control.tenant_id = demo_tenant;
    END IF;

    INSERT INTO fsma.tenant_seed_state (
        tenant_id, obligations_seeded_at, obligation_count
    )
    VALUES (
        p_tenant_id,
        pg_catalog.now(),
        (
            SELECT pg_catalog.count(*)
              FROM public.obligations
             WHERE tenant_id = p_tenant_id
        )
    )
    ON CONFLICT (tenant_id) DO UPDATE
        SET obligations_seeded_at = EXCLUDED.obligations_seeded_at,
            obligation_count = EXCLUDED.obligation_count;
END;
$function$;
REVOKE ALL ON FUNCTION public.seed_obligations_for_tenant(uuid) FROM PUBLIC;

DO $seed_policy$
DECLARE
    owner_role text := current_user;
BEGIN
    DROP POLICY IF EXISTS seed_definer_regulations
        ON public.regulations;
    DROP POLICY IF EXISTS seed_definer_obligations
        ON public.obligations;
    DROP POLICY IF EXISTS seed_definer_controls
        ON public.controls;
    DROP POLICY IF EXISTS seed_definer_tenant_seed_state
        ON fsma.tenant_seed_state;

    EXECUTE format(
        'CREATE POLICY seed_definer_regulations ON public.regulations '
        'FOR ALL TO %I USING (current_user = %L) '
        'WITH CHECK (current_user = %L)',
        owner_role, owner_role, owner_role
    );
    EXECUTE format(
        'CREATE POLICY seed_definer_obligations ON public.obligations '
        'FOR ALL TO %I USING (current_user = %L) '
        'WITH CHECK (current_user = %L)',
        owner_role, owner_role, owner_role
    );
    EXECUTE format(
        'CREATE POLICY seed_definer_controls ON public.controls '
        'FOR ALL TO %I USING (current_user = %L) '
        'WITH CHECK (current_user = %L)',
        owner_role, owner_role, owner_role
    );
    EXECUTE format(
        'CREATE POLICY seed_definer_tenant_seed_state ON fsma.tenant_seed_state '
        'FOR ALL TO %I USING (current_user = %L) '
        'WITH CHECK (current_user = %L)',
        owner_role, owner_role, owner_role
    );
END
$seed_policy$;
"""


_HASH_HELPER_REPAIR = """
-- These three helpers are the only application code that calls pgcrypto.
-- v079/v080 created them with an unqualified digest(), resolved from the
-- caller's search_path, and production keeps pgcrypto in a provider-owned
-- ``extensions`` schema that the runtime roles cannot use. Reapplied on every
-- deploy, this repair (1) resolves the extension's catalog-owned namespace,
-- so a relocated pgcrypto heals on the next deploy, and (2) runs each helper
-- as its migration-owned definer with search_path pinned to pg_catalog then
-- pg_temp. The helpers read no table and have no side effects; definer
-- rights only let them reach digest() without granting the runtime roles
-- USAGE on the extension schema, which would expose every other function
-- installed there. Hash inputs and outputs are unchanged, so existing
-- artifacts and receipts still verify.
DO $repair$
DECLARE
    pgcrypto_schema name;
BEGIN
    SELECT n.nspname
      INTO STRICT pgcrypto_schema
      FROM pg_extension AS e
      JOIN pg_namespace AS n ON n.oid = e.extnamespace
     WHERE e.extname = 'pgcrypto';

    EXECUTE format(
        $ddl$
        CREATE OR REPLACE FUNCTION fsma.compute_agent_artifact_hash(
            p_artifact jsonb
        ) RETURNS text
        LANGUAGE sql
        IMMUTABLE
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $function$
            SELECT pg_catalog.encode(
                %I.digest(
                    COALESCE(p_artifact, '{}'::jsonb)::text,
                    'sha256'::text
                ),
                'hex'::text
            )
        $function$
        $ddl$,
        pgcrypto_schema
    );

    EXECUTE format(
        $ddl$
        CREATE OR REPLACE FUNCTION fsma.compute_ingestion_run_receipt_payload_hash(
            p_metadata jsonb
        ) RETURNS text
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $function$
            SELECT pg_catalog.encode(
                %I.digest(
                    COALESCE(p_metadata, '{}'::jsonb)::text,
                    'sha256'::text
                ),
                'hex'::text
            )
        $function$
        $ddl$,
        pgcrypto_schema
    );

    EXECUTE format(
        $ddl$
        CREATE OR REPLACE FUNCTION fsma.compute_ingestion_run_receipt_hash(
            p_tenant_id uuid,
            p_ingestion_run_id uuid,
            p_sequence_num bigint,
            p_state text,
            p_occurred_at timestamptz,
            p_actor text,
            p_request_id text,
            p_canonical_event_id uuid,
            p_evidence_attachment_id uuid,
            p_rule_evaluation_id uuid,
            p_export_log_id uuid,
            p_payload_hash text,
            p_previous_receipt_hash text
        ) RETURNS text
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = pg_catalog, pg_temp
        AS $function$
            SELECT pg_catalog.encode(
                %I.digest(
                    pg_catalog.jsonb_build_object(
                        'tenant_id', p_tenant_id::text,
                        'ingestion_run_id', p_ingestion_run_id::text,
                        'sequence_num', p_sequence_num,
                        'state', p_state,
                        'occurred_at_utc',
                            pg_catalog.to_char(
                                p_occurred_at AT TIME ZONE 'UTC',
                                'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                            ),
                        'actor', p_actor,
                        'request_id', p_request_id,
                        'canonical_event_id', p_canonical_event_id::text,
                        'evidence_attachment_id', p_evidence_attachment_id::text,
                        'rule_evaluation_id', p_rule_evaluation_id::text,
                        'export_log_id', p_export_log_id::text,
                        'payload_hash', p_payload_hash,
                        'previous_receipt_hash', p_previous_receipt_hash
                    )::text,
                    'sha256'::text
                ),
                'hex'::text
            )
        $function$
        $ddl$,
        pgcrypto_schema
    );
END
$repair$;
"""


_FUNCTION_GRANTS = """
DO $cutover$
DECLARE
    function_signature text;
BEGIN
    -- Remove the implicit PUBLIC grant and any historical blanket grants from
    -- application-authored functions. Extension-owned functions are left to
    -- their extension because operators/index support can require them.
    FOR function_signature IN
        SELECT format(
                   '%I.%I(%s)',
                   n.nspname,
                   p.proname,
                   pg_get_function_identity_arguments(p.oid)
               )
          FROM pg_proc AS p
          JOIN pg_namespace AS n ON n.oid = p.pronamespace
         WHERE n.nspname IN ('public', 'fsma', 'audit', 'dlq', 'ingestion')
           AND p.prokind = 'f'
           AND NOT EXISTS (
               SELECT 1
                 FROM pg_depend AS d
                WHERE d.classid = 'pg_proc'::regclass
                  AND d.objid = p.oid
                  AND d.deptype = 'e'
           )
    LOOP
        EXECUTE format(
            'REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC, regengine, regengine_sysadmin',
            function_signature
        );
    END LOOP;

    -- Every RLS policy caller must be able to evaluate the canonical
    -- fail-hard predicate. It only reads the caller's own tenant GUC and
    -- raises when unset; it cannot arm or broaden access. This is the sole
    -- application-authored function intentionally executable by PUBLIC.
    GRANT EXECUTE ON FUNCTION public.get_tenant_context() TO PUBLIC;

    -- Tenant-runtime helpers. None can arm global/sysadmin access.
    GRANT EXECUTE ON FUNCTION public.get_tenant_context() TO regengine;
    GRANT EXECUTE ON FUNCTION public.set_tenant_context(text) TO regengine;
    GRANT EXECUTE ON FUNCTION public.seed_obligations_for_tenant(uuid) TO regengine;
    GRANT EXECUTE ON FUNCTION fsma.get_active_portal_link_by_token(text) TO regengine;
    GRANT EXECUTE ON FUNCTION fsma.get_team_roster(uuid) TO regengine;
    -- v126: pure hash/validation helpers called by the SECURITY INVOKER
    -- agent-artifact and receipt triggers and by the agent_artifacts
    -- source_hashes CHECK, so the inserting role needs EXECUTE. They read no
    -- table and cannot arm tenant or admin context; the three digest()
    -- helpers are pinned definers (_HASH_HELPER_REPAIR).
    GRANT EXECUTE ON FUNCTION fsma.compute_agent_artifact_hash(jsonb) TO regengine;
    GRANT EXECUTE ON FUNCTION fsma.sha256_text_array_is_valid(text[]) TO regengine;
    GRANT EXECUTE ON FUNCTION fsma.compute_ingestion_run_receipt_payload_hash(jsonb)
        TO regengine;
    GRANT EXECUTE ON FUNCTION fsma.compute_ingestion_run_receipt_hash(
        uuid, uuid, bigint, text, timestamptz, text, text,
        uuid, uuid, uuid, uuid, text, text
    ) TO regengine;

    -- email_ingest (v121 ccaa01e4fd7c / v122 d14f8a2b9c31) SECURITY DEFINER
    -- boundary. Absent on the first pass, present when the supported runner
    -- reapplies this cutover at head. Only the v122 sender-allowlisted lookup
    -- is granted: the recipient-only get_tenant_by_inbound_address(text)
    -- overload and fsma.tenant_inbound_email_addresses (8301f3cad96a, used
    -- by the inbound_email router) stay denied, because resolving a tenant
    -- from the recipient address alone is the cross-tenant write v122 closed.
    FOREACH function_signature IN ARRAY ARRAY[
        'fsma.get_tenant_by_inbound_address(text, text)',
        'fsma.get_inbound_email_audit_by_message_id(text)',
        'fsma.claim_inbound_email_audit(uuid, text, text, text, text, integer)',
        'fsma.finalize_inbound_email_audit(text, uuid, text, text, integer, integer, integer, jsonb)'
    ] LOOP
        IF to_regprocedure(function_signature) IS NOT NULL THEN
            EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO regengine', function_signature);
        END IF;
    END LOOP;

    -- Admin sessions still use tenant context for tenant-scoped operations,
    -- but only the exact sysadmin role may arm the global policy branch.
    GRANT EXECUTE ON FUNCTION public.get_tenant_context() TO regengine_sysadmin;
    GRANT EXECUTE ON FUNCTION public.set_tenant_context(text) TO regengine_sysadmin;
    GRANT EXECUTE ON FUNCTION public.set_admin_context(boolean) TO regengine_sysadmin;
    -- v113 is absent on the first pass, but present when the supported
    -- runner reapplies this cutover at head. Preserve the admin route's
    -- narrow pre-tenant helper without granting ordinary runtime access.
    IF to_regprocedure('public.get_invite_tenant_by_token_hash(text)') IS NOT NULL THEN
        GRANT EXECUTE ON FUNCTION public.get_invite_tenant_by_token_hash(text)
            TO regengine_sysadmin;
    END IF;
    REVOKE EXECUTE ON FUNCTION public.set_admin_context(boolean)
        FROM PUBLIC, regengine;

    IF position(
        'current_user' IN lower(pg_get_functiondef(
            'public.set_admin_context(boolean)'::regprocedure
        ))
    ) = 0 OR position(
        'regengine_sysadmin' IN lower(pg_get_functiondef(
            'public.set_admin_context(boolean)'::regprocedure
        ))
    ) = 0 THEN
        RAISE EXCEPTION
            'public.set_admin_context(boolean) lacks its current_user guard';
    END IF;
END
$cutover$;
"""


_API_KEY_RLS = """
ALTER TABLE public.api_keys ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.api_keys FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_api_keys ON public.api_keys;
DROP POLICY IF EXISTS api_keys_runtime_select ON public.api_keys;
DROP POLICY IF EXISTS api_keys_runtime_usage_update ON public.api_keys;
DROP POLICY IF EXISTS api_keys_sysadmin_all ON public.api_keys;

-- Pre-tenant proof is a SELECT capability only.  The ordinary runtime role
-- gets column-level UPDATE grants solely for the two usage counters, and the
-- matching UPDATE policy below cannot authorize any other column mutation.
CREATE POLICY api_keys_runtime_select ON public.api_keys
    FOR SELECT TO regengine
    USING (
        current_user = 'regengine'
        AND key_id = NULLIF(
            current_setting('regengine.api_key_lookup_id', true),
            ''
        )
        AND (
            key_hash = NULLIF(
                current_setting('regengine.api_key_lookup_hash_current', true),
                ''
            )
            OR key_hash = NULLIF(
                current_setting('regengine.api_key_lookup_hash_legacy', true),
                ''
            )
        )
    );

CREATE POLICY api_keys_runtime_usage_update ON public.api_keys
    FOR UPDATE TO regengine
    USING (
        current_user = 'regengine'
        AND key_id = NULLIF(
            current_setting('regengine.api_key_lookup_id', true),
            ''
        )
        AND (
            key_hash = NULLIF(
                current_setting('regengine.api_key_lookup_hash_current', true),
                ''
            )
            OR key_hash = NULLIF(
                current_setting('regengine.api_key_lookup_hash_legacy', true),
                ''
            )
        )
    )
    WITH CHECK (
        current_user = 'regengine'
        AND key_id = NULLIF(
            current_setting('regengine.api_key_lookup_id', true),
            ''
        )
        AND (
            key_hash = NULLIF(
                current_setting('regengine.api_key_lookup_hash_current', true),
                ''
            )
            OR key_hash = NULLIF(
                current_setting('regengine.api_key_lookup_hash_legacy', true),
                ''
            )
        )
    );

CREATE POLICY api_keys_sysadmin_all ON public.api_keys
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );
"""


_CONTROL_PLANE_RLS = """
-- Identity and authentication tables run on ADMIN_DATABASE_URL.  The raw
-- control-plane role is baseline-denied: pre-tenant auth explicitly arms a
-- transaction, while an already-authenticated user may access only rows bound
-- to the transaction-local regengine.user_id.
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.users FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_self_isolation ON public.users;
DROP POLICY IF EXISTS users_self_or_admin ON public.users;
CREATE POLICY users_self_or_admin ON public.users
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND (
            id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND (
            id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    );

ALTER TABLE public.sessions ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.sessions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS sessions_user_isolation ON public.sessions;
DROP POLICY IF EXISTS sessions_self_or_admin ON public.sessions;
CREATE POLICY sessions_self_or_admin ON public.sessions
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    );

ALTER TABLE public.user_emails ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_emails FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS user_emails_self_or_admin ON public.user_emails;
CREATE POLICY user_emails_self_or_admin ON public.user_emails
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    );

ALTER TABLE public.organization_memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organization_memberships FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS organization_memberships_self_or_admin
    ON public.organization_memberships;
CREATE POLICY organization_memberships_self_or_admin
    ON public.organization_memberships
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    );

ALTER TABLE public.webauthn_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webauthn_credentials FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS webauthn_credentials_self_or_admin
    ON public.webauthn_credentials;
CREATE POLICY webauthn_credentials_self_or_admin
    ON public.webauthn_credentials
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    );

ALTER TABLE public.webauthn_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.webauthn_challenges FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS webauthn_challenges_self_or_admin
    ON public.webauthn_challenges;
CREATE POLICY webauthn_challenges_self_or_admin
    ON public.webauthn_challenges
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    );

ALTER TABLE public.admin_mfa_recovery_codes ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.admin_mfa_recovery_codes FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_only_admin_mfa_recovery_codes
    ON public.admin_mfa_recovery_codes;
DROP POLICY IF EXISTS admin_mfa_recovery_codes_self_or_admin
    ON public.admin_mfa_recovery_codes;
CREATE POLICY admin_mfa_recovery_codes_self_or_admin
    ON public.admin_mfa_recovery_codes
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND (
            user_id = NULLIF(current_setting('regengine.user_id', true), '')::uuid
            OR current_setting('regengine.is_sysadmin', true) = 'true'
        )
    );

ALTER TABLE public.auth_challenges ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.auth_challenges FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS auth_challenges_admin_bootstrap
    ON public.auth_challenges;
CREATE POLICY auth_challenges_admin_bootstrap ON public.auth_challenges
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );

ALTER TABLE public.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.organizations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS organizations_admin_bootstrap ON public.organizations;
CREATE POLICY organizations_admin_bootstrap ON public.organizations
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );

-- v100 temporarily admitted every sysadmin-role membership read with
-- USING(true).  The role is now the baseline-denied control-plane credential,
-- so even pre-tenant authentication must explicitly arm its transaction.
ALTER TABLE public.memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memberships FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_memberships ON public.memberships;
DROP POLICY IF EXISTS memberships_sysadmin_read ON public.memberships;
DROP POLICY IF EXISTS memberships_self_select ON public.memberships;
DROP POLICY IF EXISTS memberships_tenant_insert ON public.memberships;
DROP POLICY IF EXISTS memberships_tenant_update ON public.memberships;
DROP POLICY IF EXISTS memberships_tenant_delete ON public.memberships;

-- Keep SELECT in one CASE-lazy policy. Multiple permissive SELECT policies
-- are ORed by PostgreSQL, but the planner may still evaluate a tenant branch
-- that raises when app.tenant_id is unset. Pre-tenant authentication must be
-- able to arm the global branch without touching that tenant expression.
CREATE POLICY memberships_sysadmin_read ON public.memberships
    FOR SELECT TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND CASE
            WHEN current_setting('regengine.is_sysadmin', true) = 'true'
                THEN true
            WHEN user_id = NULLIF(
                current_setting('regengine.user_id', true),
                ''
            )::uuid
                THEN true
            ELSE tenant_id::text = NULLIF(
                current_setting('app.tenant_id', true),
                ''
            )
        END
    );

CREATE POLICY memberships_tenant_insert ON public.memberships
    FOR INSERT TO regengine_sysadmin
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND CASE
            WHEN current_setting('regengine.is_sysadmin', true) = 'true'
                THEN true
            ELSE tenant_id::text = NULLIF(
                current_setting('app.tenant_id', true),
                ''
            )
        END
    );

CREATE POLICY memberships_tenant_update ON public.memberships
    FOR UPDATE TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND CASE
            WHEN current_setting('regengine.is_sysadmin', true) = 'true'
                THEN true
            ELSE tenant_id::text = NULLIF(
                current_setting('app.tenant_id', true),
                ''
            )
        END
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND CASE
            WHEN current_setting('regengine.is_sysadmin', true) = 'true'
                THEN true
            ELSE tenant_id::text = NULLIF(
                current_setting('app.tenant_id', true),
                ''
            )
        END
    );

CREATE POLICY memberships_tenant_delete ON public.memberships
    FOR DELETE TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND CASE
            WHEN current_setting('regengine.is_sysadmin', true) = 'true'
                THEN true
            ELSE tenant_id::text = NULLIF(
                current_setting('app.tenant_id', true),
                ''
            )
        END
    );

-- Canonical global roles must remain visible to an authenticated admin while
-- custom roles remain bound to the selected tenant.  Ordinary runtime
-- credentials have neither a policy nor a table grant on this identity
-- surface.
ALTER TABLE public.roles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.roles FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_roles ON public.roles;
DROP POLICY IF EXISTS roles_tenant_select ON public.roles;
DROP POLICY IF EXISTS roles_sysadmin_scoped ON public.roles;
CREATE POLICY roles_tenant_select ON public.roles
    FOR SELECT TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND (
            tenant_id IS NULL
            OR tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
        )
    );
CREATE POLICY roles_sysadmin_scoped ON public.roles
    FOR ALL TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );

-- Tenant creation is a global control-plane operation.  Existing tenant
-- reads/updates are split by database role; no delete policy is introduced.
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.tenants FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenants_read_all ON public.tenants;
DROP POLICY IF EXISTS tenants_write_own ON public.tenants;
DROP POLICY IF EXISTS tenants_runtime_own ON public.tenants;
DROP POLICY IF EXISTS tenants_sysadmin_select ON public.tenants;
DROP POLICY IF EXISTS tenants_sysadmin_tenant_select ON public.tenants;
DROP POLICY IF EXISTS tenants_sysadmin_insert ON public.tenants;

CREATE POLICY tenants_runtime_own ON public.tenants
    FOR SELECT TO regengine
    USING (
        id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );

CREATE POLICY tenants_sysadmin_select ON public.tenants
    FOR SELECT TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );

CREATE POLICY tenants_sysadmin_tenant_select ON public.tenants
    FOR SELECT TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );

CREATE POLICY tenants_sysadmin_insert ON public.tenants
    FOR INSERT TO regengine_sysadmin
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );

DROP POLICY IF EXISTS tenants_sysadmin_update ON public.tenants;
CREATE POLICY tenants_sysadmin_update ON public.tenants
    FOR UPDATE TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );
"""


_TENANT_SURFACE_RLS = """
-- v092's app-only funnel policy blocked browser clients but admitted every
-- tenant to the shared runtime role.  Bind both service roles to the exact
-- transaction-local tenant context instead.
ALTER TABLE public.funnel_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.funnel_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_only_funnel_events ON public.funnel_events;
DROP POLICY IF EXISTS tenant_isolation_funnel_events ON public.funnel_events;
CREATE POLICY tenant_isolation_funnel_events ON public.funnel_events
    FOR ALL TO regengine, regengine_sysadmin
    USING (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );

-- The only buffer producer belongs to the release-disabled graph service, so
-- DATABASE_URL receives no policy or ACL.  Reconciliation remains a narrow
-- control-plane SELECT plus replay-column UPDATE on ADMIN_DATABASE_URL.
ALTER TABLE public.audit_log_buffer ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.audit_log_buffer FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_only_audit_log_buffer ON public.audit_log_buffer;
DROP POLICY IF EXISTS audit_log_buffer_runtime_insert ON public.audit_log_buffer;
DROP POLICY IF EXISTS audit_log_buffer_sysadmin_reconcile ON public.audit_log_buffer;
DROP POLICY IF EXISTS audit_log_buffer_sysadmin_update ON public.audit_log_buffer;
CREATE POLICY audit_log_buffer_sysadmin_reconcile ON public.audit_log_buffer
    FOR SELECT TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );
CREATE POLICY audit_log_buffer_sysadmin_update ON public.audit_log_buffer
    FOR UPDATE TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );

-- Review traffic runs on ADMIN_DATABASE_URL.  It gets the same tenant
-- predicate as the ingestion writer, never the global sysadmin branch.
DROP POLICY IF EXISTS tenant_isolation_agent_artifacts_sysadmin
    ON fsma.agent_artifacts;
CREATE POLICY tenant_isolation_agent_artifacts_sysadmin
    ON fsma.agent_artifacts
    FOR ALL TO regengine_sysadmin
    USING (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );

DROP POLICY IF EXISTS tenant_isolation_agent_artifact_reviews_sysadmin
    ON fsma.agent_artifact_reviews;
CREATE POLICY tenant_isolation_agent_artifact_reviews_sysadmin
    ON fsma.agent_artifact_reviews
    FOR ALL TO regengine_sysadmin
    USING (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );

DROP POLICY IF EXISTS tenant_isolation_ingestion_run_receipts_sysadmin
    ON fsma.ingestion_run_receipts;
CREATE POLICY tenant_isolation_ingestion_run_receipts_sysadmin
    ON fsma.ingestion_run_receipts
    FOR ALL TO regengine_sysadmin
    USING (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );

DROP POLICY IF EXISTS tenant_isolation_ingestion_runs_sysadmin
    ON fsma.ingestion_runs;
CREATE POLICY tenant_isolation_ingestion_runs_sysadmin
    ON fsma.ingestion_runs
    FOR ALL TO regengine_sysadmin
    USING (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
"""


_WORKER_AND_SERVICE_RLS = """
-- Cross-tenant queue coordination is performed through the audited admin
-- engine.  The ordinary runtime role can enqueue/read only the active
-- tenant and cannot forge the retired ``regengine.system_context`` flag.
ALTER TABLE fsma.task_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.task_queue FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_tasks ON fsma.task_queue;
DROP POLICY IF EXISTS task_queue_runtime_tenant ON fsma.task_queue;
DROP POLICY IF EXISTS task_queue_runtime_select ON fsma.task_queue;
DROP POLICY IF EXISTS task_queue_runtime_insert ON fsma.task_queue;
DROP POLICY IF EXISTS task_queue_sysadmin_worker ON fsma.task_queue;
DROP POLICY IF EXISTS task_queue_sysadmin_select ON fsma.task_queue;
DROP POLICY IF EXISTS task_queue_sysadmin_update ON fsma.task_queue;
DROP POLICY IF EXISTS task_queue_sysadmin_delete ON fsma.task_queue;
CREATE POLICY task_queue_runtime_select ON fsma.task_queue
    FOR SELECT TO regengine
    USING (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
CREATE POLICY task_queue_runtime_insert ON fsma.task_queue
    FOR INSERT TO regengine
    WITH CHECK (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
CREATE POLICY task_queue_sysadmin_select ON fsma.task_queue
    FOR SELECT TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );
CREATE POLICY task_queue_sysadmin_update ON fsma.task_queue
    FOR UPDATE TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );
CREATE POLICY task_queue_sysadmin_delete ON fsma.task_queue
    FOR DELETE TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );

ALTER TABLE fsma.fsma_audit_trail ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.fsma_audit_trail FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_audit ON fsma.fsma_audit_trail;
DROP POLICY IF EXISTS fsma_audit_trail_runtime_tenant ON fsma.fsma_audit_trail;
DROP POLICY IF EXISTS fsma_audit_trail_runtime_select ON fsma.fsma_audit_trail;
DROP POLICY IF EXISTS fsma_audit_trail_runtime_insert ON fsma.fsma_audit_trail;
DROP POLICY IF EXISTS fsma_audit_trail_sysadmin_read ON fsma.fsma_audit_trail;
CREATE POLICY fsma_audit_trail_runtime_select ON fsma.fsma_audit_trail
    FOR SELECT TO regengine
    USING (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
CREATE POLICY fsma_audit_trail_runtime_insert ON fsma.fsma_audit_trail
    FOR INSERT TO regengine
    WITH CHECK (
        tenant_id IS NOT NULL
        AND tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
CREATE POLICY fsma_audit_trail_sysadmin_read ON fsma.fsma_audit_trail
    FOR SELECT TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );

-- Service-local ingestion/DLQ schemas carry tenant IDs too; schema separation
-- is not an authorization boundary.
ALTER TABLE ingestion.documents ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion.documents FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_ingestion_documents ON ingestion.documents;
DROP POLICY IF EXISTS ingestion_documents_runtime_select ON ingestion.documents;
DROP POLICY IF EXISTS ingestion_documents_runtime_insert ON ingestion.documents;
CREATE POLICY ingestion_documents_runtime_select ON ingestion.documents
    FOR SELECT TO regengine
    USING (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
CREATE POLICY ingestion_documents_runtime_insert ON ingestion.documents
    FOR INSERT TO regengine
    WITH CHECK (
        tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
DROP POLICY IF EXISTS ingestion_documents_sysadmin ON ingestion.documents;

ALTER TABLE ingestion.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion.jobs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_ingestion_jobs ON ingestion.jobs;
DROP POLICY IF EXISTS ingestion_jobs_runtime_select ON ingestion.jobs;
DROP POLICY IF EXISTS ingestion_jobs_runtime_insert ON ingestion.jobs;
DROP POLICY IF EXISTS ingestion_jobs_runtime_update ON ingestion.jobs;
CREATE POLICY ingestion_jobs_runtime_select ON ingestion.jobs
    FOR SELECT TO regengine
    USING (
        tenant_id IS NOT NULL
        AND tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
CREATE POLICY ingestion_jobs_runtime_insert ON ingestion.jobs
    FOR INSERT TO regengine
    WITH CHECK (
        tenant_id IS NOT NULL
        AND tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
CREATE POLICY ingestion_jobs_runtime_update ON ingestion.jobs
    FOR UPDATE TO regengine
    USING (
        tenant_id IS NOT NULL
        AND tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    )
    WITH CHECK (
        tenant_id IS NOT NULL
        AND tenant_id::text = NULLIF(current_setting('app.tenant_id', true), '')
    );
DROP POLICY IF EXISTS ingestion_jobs_sysadmin ON ingestion.jobs;

ALTER TABLE ingestion.audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE ingestion.audit_log FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_ingestion_audit_log ON ingestion.audit_log;
DROP POLICY IF EXISTS ingestion_audit_log_runtime_select ON ingestion.audit_log;
DROP POLICY IF EXISTS ingestion_audit_log_runtime_insert ON ingestion.audit_log;
CREATE POLICY ingestion_audit_log_runtime_select ON ingestion.audit_log
    FOR SELECT TO regengine
    USING (
        EXISTS (
            SELECT 1
              FROM ingestion.jobs AS owning_job
             WHERE owning_job.job_id = audit_log.job_id
               AND owning_job.tenant_id::text = NULLIF(
                   current_setting('app.tenant_id', true),
                   ''
               )
        )
    );
CREATE POLICY ingestion_audit_log_runtime_insert ON ingestion.audit_log
    FOR INSERT TO regengine
    WITH CHECK (
        EXISTS (
            SELECT 1
              FROM ingestion.jobs AS owning_job
             WHERE owning_job.job_id = audit_log.job_id
               AND owning_job.tenant_id::text = NULLIF(
                   current_setting('app.tenant_id', true),
                   ''
               )
        )
    );
DROP POLICY IF EXISTS ingestion_audit_log_sysadmin ON ingestion.audit_log;

ALTER TABLE dlq.webhook_failures ENABLE ROW LEVEL SECURITY;
ALTER TABLE dlq.webhook_failures FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation_webhook_failures ON dlq.webhook_failures;
DROP POLICY IF EXISTS webhook_failures_sysadmin ON dlq.webhook_failures;
DROP POLICY IF EXISTS webhook_failures_sysadmin_select ON dlq.webhook_failures;
DROP POLICY IF EXISTS webhook_failures_sysadmin_update ON dlq.webhook_failures;
CREATE POLICY webhook_failures_sysadmin_select ON dlq.webhook_failures
    FOR SELECT TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );
CREATE POLICY webhook_failures_sysadmin_update ON dlq.webhook_failures
    FOR UPDATE TO regengine_sysadmin
    USING (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    )
    WITH CHECK (
        current_user = 'regengine_sysadmin'
        AND current_setting('regengine.is_sysadmin', true) = 'true'
    );

-- These optional incident/exchange surfaces are release-disabled.  Retire
-- their legacy USING(true) arms and leave both runtime roles with no policy
-- and no ACL. fsma.organizations is likewise explicitly classified NONE.
ALTER TABLE fsma.incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.incidents FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_only_incidents ON fsma.incidents;

ALTER TABLE fsma.exchange_packages ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.exchange_packages FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS app_only_exchange_packages ON fsma.exchange_packages;

ALTER TABLE fsma.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE fsma.organizations FORCE ROW LEVEL SECURITY;

-- Named drops above repair known historical states.  A disabled surface has
-- a stronger closed-world contract: no policy whatsoever may survive a
-- reapplication, including an out-of-band permissive policy with a new name.
DO $disabled_policies$
DECLARE
    policy_row record;
BEGIN
    FOR policy_row IN
        SELECT schemaname, tablename, policyname
          FROM pg_policies
         WHERE (schemaname, tablename) IN (
                   ('fsma', 'incidents'),
                   ('fsma', 'exchange_packages'),
                   ('fsma', 'organizations')
               )
    LOOP
        EXECUTE format(
            'DROP POLICY %I ON %I.%I',
            policy_row.policyname,
            policy_row.schemaname,
            policy_row.tablename
        );
    END LOOP;
END
$disabled_policies$;
"""


_POLICY_POSTURE = """
DO $policy_guard$
DECLARE
    unsafe_policy record;
BEGIN
    SELECT schemaname, tablename, policyname
      INTO unsafe_policy
      FROM pg_policies
     WHERE (
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
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'unsafe spoofable sysadmin GUC policy %.%/%',
            unsafe_policy.schemaname,
            unsafe_policy.tablename,
            unsafe_policy.policyname;
    END IF;

    SELECT schemaname, tablename, policyname
      INTO unsafe_policy
      FROM pg_policies
     WHERE COALESCE(qual, '') LIKE '%regengine.system_context%'
        OR COALESCE(with_check, '') LIKE '%regengine.system_context%'
     LIMIT 1;

    IF FOUND THEN
        RAISE EXCEPTION
            'retired caller-spoofable system-context policy %.%/%',
            unsafe_policy.schemaname,
            unsafe_policy.tablename,
            unsafe_policy.policyname;
    END IF;
END
$policy_guard$;
"""


_SYSADMIN_DML_AUDIT = """
-- Repair the legacy trigger guard: SECURITY DEFINER changes current_user to
-- the function owner, so its old current_user='regengine_sysadmin' predicate
-- could never match. session_user is the authenticated database principal and
-- cannot be forged with a custom GUC.  Endpoint audit remains authoritative
-- for human user/session/request attribution; this immutable table is a
-- supplementary database-role DML trail (SELECTs are not trigger-auditable).
CREATE OR REPLACE FUNCTION audit.log_sysadmin_access()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, audit
AS $function$
BEGIN
    IF session_user = 'regengine_sysadmin'
       AND current_setting('regengine.is_sysadmin', true) = 'true' THEN
        INSERT INTO audit.sysadmin_access_log (
            table_name, operation, connection_info
        )
        VALUES (
            TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME,
            TG_OP,
            pg_catalog.jsonb_build_object(
                'definer_role', current_user,
                'session_user', session_user,
                'client_addr', pg_catalog.inet_client_addr()::text,
                'application_name', current_setting('application_name', true),
                'backend_pid', pg_catalog.pg_backend_pid()
            )
        );
    END IF;
    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$function$;
REVOKE ALL ON FUNCTION audit.log_sysadmin_access()
    FROM PUBLIC, regengine, regengine_sysadmin;

DROP TRIGGER IF EXISTS trg_v111_sysadmin_dml_api_keys ON public.api_keys;
CREATE TRIGGER trg_v111_sysadmin_dml_api_keys
AFTER INSERT OR UPDATE OR DELETE ON public.api_keys
FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();

DROP TRIGGER IF EXISTS trg_v111_sysadmin_dml_tenants ON public.tenants;
CREATE TRIGGER trg_v111_sysadmin_dml_tenants
AFTER INSERT OR UPDATE OR DELETE ON public.tenants
FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();

DROP TRIGGER IF EXISTS trg_v111_sysadmin_dml_agent_reviews
    ON fsma.agent_artifact_reviews;
CREATE TRIGGER trg_v111_sysadmin_dml_agent_reviews
AFTER INSERT OR UPDATE OR DELETE ON fsma.agent_artifact_reviews
FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();

DROP TRIGGER IF EXISTS trg_v111_sysadmin_dml_task_queue ON fsma.task_queue;
CREATE TRIGGER trg_v111_sysadmin_dml_task_queue
AFTER INSERT OR UPDATE OR DELETE ON fsma.task_queue
FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();

DROP TRIGGER IF EXISTS trg_v111_sysadmin_dml_webhook_failures
    ON dlq.webhook_failures;
CREATE TRIGGER trg_v111_sysadmin_dml_webhook_failures
AFTER INSERT OR UPDATE OR DELETE ON dlq.webhook_failures
FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();

DROP TRIGGER IF EXISTS trg_v111_sysadmin_dml_audit_buffer
    ON public.audit_log_buffer;
CREATE TRIGGER trg_v111_sysadmin_dml_audit_buffer
AFTER INSERT OR UPDATE OR DELETE ON public.audit_log_buffer
FOR EACH ROW EXECUTE FUNCTION audit.log_sysadmin_access();
"""

CUTOVER_STATEMENTS = (
    *((_MIGRATION_OWNER_POSTURE,) if _MIGRATION_OWNER_POSTURE else ()),
    _ROLE_POSTURE,
    _OBJECT_GRANTS,
    _SEED_FUNCTION,
    _HASH_HELPER_REPAIR,
    _FUNCTION_GRANTS,
    _API_KEY_RLS,
    _CONTROL_PLANE_RLS,
    _TENANT_SURFACE_RLS,
    _WORKER_AND_SERVICE_RLS,
    _SYSADMIN_DML_AUDIT,
    _POLICY_POSTURE,
)


def upgrade() -> None:
    # Every statement is convergent. Keeping the cutover idempotent lets an
    # owner-run verification reapply it safely after grant drift is repaired.
    for statement in CUTOVER_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Deliberately irreversible: restoring blanket function execution, schema
    # CREATE, or runtime access to Alembic metadata is not a safe rollback.
    pass
