"""Router registration for the consolidated monolith (tech-debt WI-14, 2026-11-04).

Split out of ``server/main.py`` so app composition stays readable. The
mounting order below is the first-match order Starlette resolves routes in;
it is unchanged from the pre-split file, and
``tests/test_server_route_snapshot_wi14.py`` pins the production route set.
``scripts/check_docs_counts.py`` counts the ``include_owned_router`` calls
here against ``docs/CODEBASE_MAP.md``.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import FastAPI

from server.route_ownership import include_owned_router, owned_api_route


def mount_routers(app: FastAPI, _router_enabled: Callable[[str], bool]) -> None:
    """Mount every domain router on ``app``; ``_router_enabled`` is the RouterPolicy gate."""
    # =====================================================================
    # DOMAIN: INGESTION — CTE events, document processing, webhooks
    # =====================================================================
    # services/ingestion/app/routes.py is a leftover aggregator with no APIRoute
    # objects. Do not mount it: an empty always-on owner is an ungated place for
    # new production routes to land without ENABLED_ROUTERS or a security policy.

    # Ingest endpoints (extracted from routes.py — /v1/ingest, /v1/ingest/file,
    # /v1/ingest/url, /v1/ingest/regulation). Mirrors services/ingestion/main.py.
    from services.ingestion.app.routes_ingest import router as ingest_router

    include_owned_router(app, ingest_router, owner="core_ingest", tags=["Document Ingestion"])

    from services.ingestion.app.routes_health_metrics import router as health_metrics_router

    include_owned_router(app, health_metrics_router, owner="health", tags=["Health & Metrics"])

    from services.ingestion.app.routes_status import router as status_router

    include_owned_router(app, status_router, owner="status")

    from services.ingestion.app.webhook_router_v2 import router as webhook_router

    include_owned_router(app, webhook_router, owner="webhook", tags=["Webhooks"])

    if _router_enabled("scraping"):
        from services.ingestion.app.routes_scraping import router as scraping_router

        include_owned_router(app, scraping_router, owner="scraping", tags=["Web Scraping"])

    if _router_enabled("discovery"):
        from services.ingestion.app.routes_discovery import router as discovery_router

        include_owned_router(app, discovery_router, owner="discovery", tags=["Discovery"])

    if _router_enabled("sources"):
        from services.ingestion.app.routes_sources import router as sources_router

        include_owned_router(app, sources_router, owner="sources")

    if _router_enabled("sandbox"):
        from services.ingestion.app.sandbox.router import router as sandbox_router

        include_owned_router(app, sandbox_router, owner="sandbox")

    if _router_enabled("inflow_workbench"):
        from services.ingestion.app.inflow_workbench import router as inflow_workbench_router

        include_owned_router(app, inflow_workbench_router, owner="inflow_workbench")

    if _router_enabled("fda_export"):
        from services.ingestion.app.fda_export.router import router as fda_export_router

        include_owned_router(app, fda_export_router, owner="fda_export", tags=["FDA Exports"])

    if _router_enabled("proof_verify"):
        # Public hash-chain verifier. Tenantless, no auth, rate-limited.
        # Production-surface justification documented in the router docstring.
        from services.ingestion.app.proof_verify_router import router as proof_verify_router

        include_owned_router(app, proof_verify_router, owner="proof_verify", tags=["Public Proof"])

    if _router_enabled("csv"):
        from services.ingestion.app.csv_templates import router as csv_router

        include_owned_router(app, csv_router, owner="csv", tags=["CSV Import"])

    if _router_enabled("sensitech"):
        from services.ingestion.app.sensitech_parser import router as sensitech_router

        include_owned_router(app, sensitech_router, owner="sensitech", tags=["IoT Ingestion"])

    if _router_enabled("edi"):
        from services.ingestion.app.edi_ingestion import router as edi_router

        include_owned_router(app, edi_router, owner="edi", tags=["EDI Ingestion"])

    if _router_enabled("score"):
        from services.ingestion.app.compliance_score import router as score_router

        include_owned_router(app, score_router, owner="score", tags=["Compliance Scoring"])

    if _router_enabled("portal"):
        from services.ingestion.app.supplier_portal import router as portal_router

        include_owned_router(app, portal_router, owner="portal", tags=["Supplier Portal"])

    if _router_enabled("audit"):
        from services.ingestion.app.mock_audit import router as audit_router

        include_owned_router(app, audit_router, owner="audit", tags=["Audit"])

    if _router_enabled("sop"):
        from services.ingestion.app.sop_generator import router as sop_router

        include_owned_router(app, sop_router, owner="sop", tags=["SOP Generation"])

    if _router_enabled("export"):
        from services.ingestion.app.epcis_export import router as export_router

        include_owned_router(app, export_router, owner="export", tags=["Data Export"])

    if _router_enabled("epcis_ingestion"):
        from services.ingestion.app.epcis.router import router as epcis_ingestion_router

        include_owned_router(app, epcis_ingestion_router, owner="epcis_ingestion", tags=["EPCIS"])

    if _router_enabled("qr_decoder"):
        from services.ingestion.app.qr_decoder import router as qr_decoder_router

        include_owned_router(app, qr_decoder_router, owner="qr_decoder", tags=["QR & GS1 Decoding"])

    if _router_enabled("label_vision"):
        from services.ingestion.app.label_vision import router as label_vision_router

        include_owned_router(app, label_vision_router, owner="label_vision", tags=["Computer Vision"])

    if _router_enabled("exchange"):
        from services.ingestion.app.exchange_api import router as exchange_router

        include_owned_router(app, exchange_router, owner="exchange", tags=["B2B Exchange"])

    if _router_enabled("billing"):
        from services.ingestion.app.stripe_billing import router as billing_router
        from services.ingestion.app.stripe_billing.routes import list_plans as _list_billing_plans

        include_owned_router(app, billing_router, owner="billing", tags=["Billing"])

        @owned_api_route(
            app,
            owner="billing",
            path="/billing/plans",
            methods=["GET"],
            tags=["Billing"],
            include_in_schema=False,
        )
        async def list_billing_plans_compat():
            return await _list_billing_plans()


    if _router_enabled("alerts"):
        from services.ingestion.app.alerts import router as alerts_router

        include_owned_router(app, alerts_router, owner="alerts", tags=["Alerts"])

    if _router_enabled("onboarding"):
        from services.ingestion.app.onboarding import router as onboarding_router

        include_owned_router(app, onboarding_router, owner="onboarding", tags=["Onboarding"])

    if _router_enabled("recall"):
        from services.ingestion.app.recall_report import router as recall_router

        include_owned_router(app, recall_router, owner="recall", tags=["Recall Reporting"])

    if _router_enabled("recall_simulations"):
        from services.ingestion.app.recall_simulations import router as recall_simulations_router

        include_owned_router(app, recall_simulations_router, owner="recall_simulations", tags=["Recall Simulations"])

    if _router_enabled("proof_recall"):
        from services.ingestion.app.proof_recall_router import router as proof_recall_router

        include_owned_router(app, proof_recall_router, owner="proof_recall", tags=["Public Proof"])

    if _router_enabled("supplier_mgmt"):
        from services.ingestion.app.supplier_mgmt import router as supplier_mgmt_router

        include_owned_router(app, supplier_mgmt_router, owner="supplier_mgmt", tags=["Supplier Management"])

    if _router_enabled("audit_log"):
        from services.ingestion.app.audit_log import router as audit_log_router

        include_owned_router(app, audit_log_router, owner="audit_log", tags=["Audit Logs"])

    if _router_enabled("product_catalog"):
        from services.ingestion.app.product_catalog import router as product_catalog_router

        include_owned_router(app, product_catalog_router, owner="product_catalog", tags=["Product Catalog"])

    if _router_enabled("notification_prefs"):
        from services.ingestion.app.notification_prefs import router as notification_prefs_router

        include_owned_router(app, notification_prefs_router, owner="notification_prefs", tags=["Notifications"])

    if _router_enabled("team_mgmt"):
        from services.ingestion.app.team_mgmt import router as team_mgmt_router

        include_owned_router(app, team_mgmt_router, owner="team_mgmt", tags=["Team Management"])

    if _router_enabled("settings"):
        from services.ingestion.app.settings import router as settings_router

        include_owned_router(app, settings_router, owner="settings", tags=["Settings"])

    if _router_enabled("integration"):
        from services.ingestion.app.integration_router import router as integration_router

        include_owned_router(app, integration_router, owner="integration", tags=["Integration Connectors"])


    # =====================================================================
    # DOMAIN: COMPLIANCE CONTROL PLANE — rules, exceptions, workflow
    # =====================================================================
    if _router_enabled("canonical_records"):
        from services.ingestion.app.canonical_router import router as canonical_records_router

        include_owned_router(app, canonical_records_router, owner="canonical_records")

    if _router_enabled("rules"):
        from services.ingestion.app.rules_router import router as rules_engine_router

        include_owned_router(app, rules_engine_router, owner="rules")

    if _router_enabled("exceptions"):
        from services.ingestion.app.exception_router import router as exception_queue_router

        include_owned_router(app, exception_queue_router, owner="exceptions")

    if _router_enabled("remediation"):
        from services.ingestion.app.remediation.router import router as remediation_router
        from services.ingestion.app.remediation.supplier_router import (
            router as remediation_supplier_router,
        )

        include_owned_router(app, remediation_router, owner="remediation")
        include_owned_router(app, remediation_supplier_router, owner="remediation")

    if _router_enabled("request_workflow"):
        from services.ingestion.app.request_workflow_router import router as request_workflow_router

        include_owned_router(app, request_workflow_router, owner="request_workflow")

    if _router_enabled("identity"):
        from services.ingestion.app.identity_router import router as identity_resolution_router

        include_owned_router(app, identity_resolution_router, owner="identity")

    if _router_enabled("auditor"):
        from services.ingestion.app.auditor_router import router as auditor_review_router

        include_owned_router(app, auditor_review_router, owner="auditor")

    if _router_enabled("compliance_metrics"):
        from services.ingestion.app.metrics_router import router as compliance_metrics_router

        include_owned_router(app, compliance_metrics_router, owner="compliance_metrics")

    if _router_enabled("readiness"):
        from services.ingestion.app.readiness_router import router as readiness_wizard_router

        include_owned_router(app, readiness_wizard_router, owner="readiness")

        # The compatibility readiness views belong to the approved readiness
        # surface; they must disappear with that owner instead of bypassing the
        # production allowlist as an unconditional mount.
        from services.ingestion.app.fsma_readiness_compat import router as fsma_readiness_compat_router

        include_owned_router(app, fsma_readiness_compat_router, owner="readiness")

    if _router_enabled("incidents"):
        from services.ingestion.app.incident_router import router as incident_command_router

        include_owned_router(app, incident_command_router, owner="incidents")

    if _router_enabled("chain_verification"):
        from services.ingestion.app.chain_verification_job import router as chain_verification_router

        include_owned_router(app, chain_verification_router, owner="chain_verification")

    if _router_enabled("audit_export_log"):
        from services.ingestion.app.audit_export_log import router as audit_export_log_router

        include_owned_router(app, audit_export_log_router, owner="audit_export_log")

    if _router_enabled("sla_tracking"):
        from services.ingestion.app.sla_tracking import router as sla_tracking_router

        include_owned_router(app, sla_tracking_router, owner="sla_tracking")

    if _router_enabled("export_monitoring"):
        from services.ingestion.app.export_monitoring import router as export_monitoring_router

        include_owned_router(app, export_monitoring_router, owner="export_monitoring")

    if _router_enabled("supplier_validation"):
        from services.ingestion.app.supplier_validation import router as supplier_validation_router

        include_owned_router(app, supplier_validation_router, owner="supplier_validation")

    if _router_enabled("disaster_recovery"):
        from services.ingestion.app.disaster_recovery import router as disaster_recovery_router

        include_owned_router(app, disaster_recovery_router, owner="disaster_recovery")

    # Inbound Email Ingestion (Postmark inbound-parse webhook). Not in
    # COMPLIANCE_ROUTERS: unlike remediation/fda_export, disabling this cannot
    # corrupt or hide already-ingested compliance data — it only stops accepting
    # a new input channel. Not yet in PRODUCTION_ENABLED_ROUTERS — promoting it
    # there is a deliberate release-gate decision, same as disaster_recovery/
    # supplier_validation above.
    if _router_enabled("email_ingest"):
        from services.ingestion.app.email_ingest.router import router as email_ingest_router

        include_owned_router(app, email_ingest_router, owner="email_ingest")


    # =====================================================================
    # DOMAIN: AGENT ORGANIZATION — pods, agent identities, inboxes, scoped keys
    # =====================================================================
    if _router_enabled("agent_org"):
        from shared.agent_org.router import router as agent_org_router

        include_owned_router(app, agent_org_router, owner="agent_org", tags=["Agent Organization"])


    # =====================================================================
    # DOMAIN: ADMIN — tenant management, auth, supplier onboarding
    # =====================================================================
    if _router_enabled("admin"):
        from services.admin.app.agent_review_routes import router as agent_review_router
        from services.admin.app.compliance_routes import router as admin_compliance_router
        from services.admin.app.routes import router as admin_router, v1_router as admin_v1_router

        # The service-local /health and /metrics compatibility handlers collide
        # with the consolidated app's canonical always-mounted endpoints. They
        # were unreachable (FastAPI dispatches the earlier route) and are excluded
        # explicitly so the production table has one owner per method/path.
        include_owned_router(
            app,
            admin_router,
            owner="admin",
            tags=["Admin"],
            excluded_operations={("GET", "/health"), ("GET", "/metrics")},
        )
        include_owned_router(app, admin_v1_router, owner="admin", tags=["Admin V1"])
        include_owned_router(app, admin_compliance_router, owner="admin", tags=["Admin Compliance"])
        include_owned_router(app, agent_review_router, owner="admin", prefix="/v1", tags=["Agent Reviews"])

        from services.admin.app.system_routes import router as system_router

        include_owned_router(app, system_router, owner="admin", prefix="/v1", tags=["System"])

        from services.admin.app.auth_routes import router as auth_router

        include_owned_router(app, auth_router, owner="admin", tags=["Auth"])

        from services.admin.app.admin.organizations_router import router as admin_organizations_router

        include_owned_router(app, admin_organizations_router, owner="admin")

        from services.admin.app.invite_routes import router as invite_router

        include_owned_router(app, invite_router, owner="admin", prefix="/v1", tags=["Invites"])

        from services.admin.app.user_routes import router as user_router

        include_owned_router(app, user_router, owner="admin", prefix="/v1", tags=["Users"])

        from services.admin.app.supplier_onboarding_routes import router as supplier_onboarding_router

        include_owned_router(app, supplier_onboarding_router, owner="admin", prefix="/v1", tags=["Supplier Onboarding"])

        from services.admin.app.supplier_facilities_routes import router as supplier_facilities_router

        include_owned_router(app, supplier_facilities_router, owner="admin", prefix="/v1", tags=["Supplier Facilities"])

        from services.admin.app.supplier_compliance_routes import router as supplier_compliance_router

        include_owned_router(app, supplier_compliance_router, owner="admin", prefix="/v1", tags=["Supplier Compliance"])

        from services.admin.app.supplier_funnel_routes import router as supplier_funnel_router

        include_owned_router(app, supplier_funnel_router, owner="admin", prefix="/v1", tags=["Supplier Funnel"])

        from services.admin.app.tenant_settings_routes import router as tenant_settings_router

        include_owned_router(app, tenant_settings_router, owner="admin", prefix="/v1", tags=["Tenant Settings"])

        from services.admin.app.bulk_upload.routes import router as bulk_upload_router

        include_owned_router(
            app,
            bulk_upload_router,
            owner="admin",
            prefix="/v1/supplier/bulk-upload",
            tags=["Supplier Bulk Upload"],
        )

        from services.admin.app.review_routes import router as review_router

        include_owned_router(app, review_router, owner="admin", tags=["Review Queue"])

        from services.admin.app.audit_routes import router as admin_audit_router

        include_owned_router(app, admin_audit_router, owner="admin", tags=["Admin Audit"])

        from services.admin.app.tool_verification_routes import router as tool_verification_router

        include_owned_router(app, tool_verification_router, owner="admin", tags=["Tool Verification"])

        from services.admin.app.erasure_routes import router as erasure_router

        include_owned_router(app, erasure_router, owner="admin", tags=["Account"])

        from services.admin.app.data_export_routes import router as data_export_router

        include_owned_router(app, data_export_router, owner="admin", tags=["Account"])


    # =====================================================================
    # DOMAIN: GRAPH — knowledge graph, traceability, lot tracing
    # =====================================================================
    if _router_enabled("graph"):
        from services.admin.app.api_overlay import router as overlay_router
        from services.graph.app.routes import router as graph_router

        include_owned_router(app, graph_router, owner="graph", prefix="/api/v1", tags=["Graph Operations"])
        # Overlay data lives in the same Neo4j boundary. It must remain absent
        # from production until graph is promoted with the required two-tenant
        # Neo4j matrix and functional route adapters.
        include_owned_router(app, overlay_router, owner="graph", tags=["Compliance Overlay"])


    # =====================================================================
    # DOMAIN: NLP — text analysis, entity extraction
    # =====================================================================
    if _router_enabled("nlp"):
        from services.nlp.app.routes import router as nlp_router

        # These service-local diagnostics collide with graph's earlier
        # compatibility paths in the broad development app and were therefore
        # unreachable. The consolidated /health and /metrics routes are canonical.
        include_owned_router(
            app,
            nlp_router,
            owner="nlp",
            prefix="/api/v1",
            tags=["Text Analysis"],
            excluded_operations={("GET", "/api/v1/health"), ("GET", "/api/v1/metrics")},
        )


    # =====================================================================
    # DOMAIN: FSMA COMPLIANCE — checklists, industries, validation
    # =====================================================================
    if _router_enabled("fsma_compliance"):
        from services.compliance.app.routes import router as fsma_router
        from services.compliance.app.snapshots import router as snapshots_router

        include_owned_router(app, fsma_router, owner="fsma_compliance", tags=["FSMA Compliance"])
        include_owned_router(app, snapshots_router, owner="fsma_compliance")


    # ── Root endpoint ────────────────────────────────────────────────
