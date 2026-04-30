# RegEngine -- Technical Data Room

> Organized reference for engineering due diligence. Core product documents are current as of April 30, 2026.

---

## 1. Technical Architecture

- [Architecture Overview](ARCHITECTURE.md) -- Service topology, data flow, deployment routing (includes Mermaid diagram)
- [Database Topology](DATABASE_TOPOLOGY.md) -- Archived; points to current FSMA-first sources
- [C4 Context Diagram](architecture/c4-context.md) -- Level 1 system context with users and external systems
- [C4 Container Diagram](architecture/c4-containers.md) -- Level 2 container view of services and data stores
- [C4 Component Diagram](architecture/c4-components.md) -- Level 3 component breakdown
- [Architecture Decisions](architecture/decisions/ADR-template.md) -- ADR template for recording decisions
- [ADR-001: Security Hardening](ADR-001-security-hardening-architecture.md) -- Security hardening architecture decision record
- [RFC: Microservice Consolidation](rfc_microservice_consolidation.md) -- Proposal to evaluate service consolidation (Q2 2026)
- [Cross-Database Dependencies](cross_database_dependencies.md) -- PostgreSQL/Neo4j/Redis dependency mapping
- [Database Optimization](database-optimization.md) -- Query performance and indexing strategy
- [Performance Baseline](performance-baseline.md) -- Latency and throughput benchmarks

## 2. FSMA 204 Compliance

- [FSMA 204 MVP Spec](specs/FSMA_204_MVP_SPEC.md) -- Glass-box spec: CTE types, KDE capture, FDA export
- [Canonical Model Spec](CANONICAL_MODEL_SPEC.md) -- Authoritative data model with EPCIS 2.0 mapping
- [Canonical Event Model](CANONICAL_MODEL.md) -- TraceabilityEvent schema generated from code
- [Requirements Traceability Matrix](compliance/RTM.md) -- FSMA 204 section-by-section requirement mapping to code
- [Trust Framework](TRUST_FRAMEWORK.md) -- SHA-256 hash chains, 21 CFR Part 11 alignment, tamper-evident persistence
- [FSMA Phase 1 Implementation](FSMA_204_PHASE_1_IMPLEMENTATION.md) -- Critical fixes roadmap for FDA production use
- [FSMA Railway Deployment](FSMA_RAILWAY_DEPLOYMENT.md) -- P0 deployment runbook for FSMA backend services
- [Compliance Ingestion Library](compliance/ingestion_library/food_agriculture_compliance.md) -- Food and agriculture regulatory framework extractors
- [Audit Events](AUDIT_EVENTS.md) -- Kafka audit event integration for compliance tracking

## 3. Security & Access Control

- [Security Policy](../SECURITY.md) -- Vulnerability disclosure and supported versions
- [SOC 2 Control Matrix](SOC2_CONTROL_MATRIX.md) -- Trust Services Criteria mapping (preparation phase)
- [SOC 2 Preparation Checklist](soc2_preparation.md) -- Evidence collection checklist for SOC 2 Type I
- [Incident Response Plan](security/INCIDENT_RESPONSE.md) -- Identification, containment, and resolution procedures
- [Vulnerability Disclosure Policy](security/VDP.md) -- External reporting process (security@regengine.co)
- [Penetration Test Scope](security/PENTEST_SCOPE.md) -- Internal pentest scope template
- [Security Code Review Findings](security/CODE_REVIEW_FINDINGS.md) -- Security-focused code review results
- [Security Roadmap](security/ROADMAP.md) -- Security improvement plan
- [Authentication](Authentication.md) -- API-key auth with SHA-256 hashing, no plaintext storage
- [Service Accounts](SERVICE_ACCOUNTS.md) -- Programmatic access for CI/CD and backend-to-backend
- [Credential Rotation Runbook](CREDENTIAL_ROTATION_RUNBOOK.md) -- Rotation procedures for exposed credentials
- [Schema Change Policy](SCHEMA_CHANGE_POLICY.md) -- Append-only, versioned schema governance

## 4. Operations & Reliability

- [Operations Runbook](OPERATIONS.md) -- Service start/stop, health checks, log viewing
- [Production Deployment Guide](PRODUCTION_DEPLOYMENT.md) -- Full deployment process and infrastructure setup
- [Production Readiness Checklist](PRODUCTION_READINESS_CHECKLIST.md) -- Pre-production verification status
- [AWS Deployment Guide](DEPLOYMENT.md) -- Terraform + ECS/Fargate deployment walkthrough
- [Disaster Recovery](DISASTER_RECOVERY.md) -- Recovery objectives, procedures, and business continuity
- [Non-Functional Requirements](NFR_REQUIREMENTS.md) -- Availability, latency, and scalability targets
- [Environment Setup Checklist](ENV_SETUP_CHECKLIST.md) -- Beginner-friendly env var setup with dashboard links
- [Local Setup Guide](LOCAL_SETUP_GUIDE.md) -- Step-by-step local development environment
- [Deploy Security Hardening Checklist](DEPLOY_CHECKLIST_SECURITY_HARDENING.md) -- Pre-deploy security verification

### Runbooks

- [Deploy Security Hardening](../runbooks/deploy-security-hardening.md) -- Deployment with security hardening steps
- [Incident Response](../runbooks/incident-response.md) -- Operational incident response procedures
- [Monitoring & Alerts](../runbooks/monitoring-alerts.md) -- Alert routing and escalation
- [Neo4j Disaster Recovery](../runbooks/neo4j-disaster-recovery.md) -- Neo4j backup and restore procedures
- [Rollback Procedure](../runbooks/rollback-procedure.md) -- Service rollback steps
- [Scaling Guide](../runbooks/scaling-guide.md) -- Horizontal and vertical scaling procedures
- [Design Partner Funnel](docs/runbooks/design_partner_funnel_operating_rhythm.md) -- Operating rhythm for design partner pipeline
- [Disaster Recovery Runbook](runbooks/disaster-recovery.md) -- DR procedures (docs-level runbook)
- [FDA Audit Checklist](runbooks/fda-audit-checklist.md) -- FDA audit preparation checklist
- [Incident Response Runbook](runbooks/incident-response.md) -- Incident response (docs-level runbook)
- [RLS Deployment Runbook](rls_deployment_runbook.md) -- Row-level security deployment procedures

## 5. Product & Market

- [Product Overview](PRODUCT_OVERVIEW.md) -- What RegEngine is, core value, target market
- [Product Roadmap](PRODUCT_ROADMAP.md) -- FSMA-first 90-day roadmap (March-June 2026)
- [Honest Valuation Update](HONEST_VALUATION_UPDATE_2026-04-30.md) -- April 30 Inflow Workbench de-risking assessment
- [Roadmap (Extended)](ROADMAP.md) -- Longer-term product direction
- [Competitive Landscape Research](COMPETITIVE_LANDSCAPE_RESEARCH_2026-03-28.md) -- Market positioning across FSMA, RegTech, and rules-as-code
- [Competitive Benchmark](COMPETITIVE_BENCHMARK.md) -- Feature-by-feature comparison vs. FSMA 204 incumbents
- [Positioning & Messaging](POSITIONING.md) -- Product positioning statement and messaging framework
- [Pricing & Packaging](PRICING.md) -- Usage-based tiers: Developer, Professional, Enterprise
- [Pitch Deck](PITCH_DECK.md) -- Investor and partnership presentation content
- [Website Copy](WEBSITE_COPY.md) -- Marketing page copy for regengine.co
- [Multi-Industry Expansion](MULTI_INDUSTRY_EXPANSION.md) -- Archived; redirects to FSMA-first docs
- [Content: The Handoff Problem](content/the-handoff-problem.md) -- Thought leadership content

## 6. Engineering & Quality

- [AI Engineering Standards](AI_ENGINEERING_STANDARDS.md) -- How we build, what we ship, coding standards
- [Model Governance](MODEL_GOVERNANCE.md) -- ML/AI model risk management per SR 11-7
- [Testing Requirements](TESTING_REQUIREMENTS.md) -- Test coverage matrix across services
- [Engineering Handoff](ENGINEERING_HANDOFF.md) -- Authority and fact lineage system handoff
- [Mobile Capture Architecture](specs/MOBILE_CAPTURE_ARCHITECTURE.md) -- Hybrid barcode + AI field capture spec
- [Label Inception Spec](specs/SPEC_004_LABEL_INCEPTION_IMPLEMENTATION.md) -- Label inception module end-to-end spec
- [Content Ingestion Guide](CONTENT_INGESTION.md) -- Regulatory document ingestion and extraction
- [Sprint Plan](SPRINT_PLAN.md) -- Current sprint objectives and tasks
- [Execution Plan](EXECUTION_PLAN.md) -- Archived; redirects to PRODUCT_ROADMAP.md
- [Advanced Enhancements](ADVANCED_ENHANCEMENTS.md) -- Completed platform enhancements (Jan 2026)
- [Agents](AGENTS.md) -- AI agent capabilities and configuration

### Code Quality & Audits

- [Codebase Review (Mar 27)](COMPREHENSIVE_CODEBASE_REVIEW_v2_2026-03-27.md) -- Full codebase review with findings
- [Codebase Review Summary (Mar 27)](CODEBASE_REVIEW_2026-03-27.md) -- Condensed review findings
- [Codebase Issues](CODEBASE_ISSUES.md) -- Known issues tracker
- [Code Review Findings](CODE_REVIEW_FINDINGS.md) -- Code review results and recommendations
- [RegEngine Evaluation (Mar 27)](REGENGINE_EVALUATION_2026-03-27.md) -- Overall system evaluation
- [Debug Report (Mar 27)](DEBUG_REPORT_ALL_FEATURES_2026-03-27.md) -- Feature debug scan results
- [Dead Code Audit](audits/DEAD_CODE_AUDIT.md) -- Unused code identification
- [Codebase Audit (Mar 9)](audits/CODEBASE_AUDIT_2026-03-09.md) -- Earlier audit snapshot
- [Comprehensive Audit (Mar 9)](audits/COMPREHENSIVE_AUDIT_2026_03_09.md) -- Detailed audit findings
- [Security Scan Results](audits/SECURITY_SCAN_RESULTS.md) -- Automated security scan output
- [UI Audit (Mar 9)](audits/UI-AUDIT-2026-03-09.md) -- Frontend UI audit findings
- [Agent Compatibility Audit](audits/AGENT_COMPATIBILITY_AUDIT.md) -- AI agent compatibility assessment
- [Frontend Line-by-Line Analysis](FRONTEND_LINE_BY_LINE_ANALYSIS.md) -- Detailed frontend code analysis
- [Frontend Usability Analysis](FRONTEND_USABILITY_ANALYSIS.md) -- UX review and recommendations
- [Tracked Issues](TRACKED_ISSUES.md) -- Issue tracking summary
- [Upgrade Plan](UPGRADE_PLAN.md) -- Dependency and framework upgrade plan

### Internal

- [Phase Status](internal/PHASE_STATUS.md) -- Implementation phase tracking
- [Recent Changes and Fixes](internal/RECENT_CHANGES_AND_FIXES.md) -- Latest changes log
- [Bulk Upload Gap Bridge](internal/BULK_UPLOAD_GAP_BRIDGE_DELIVERABLES_MAR2026.md) -- Bulk upload feature deliverables
- [Launch Orchestrator Bundle](internal/LAUNCH_ORCHESTRATOR_BUNDLE_IMPLEMENTED.md) -- Launch orchestration implementation
- [Internal Tools Audit](internal/INTERNAL_TOOLS_AUDIT_SUMMARY.md) -- Internal tooling review
- [404 Errors Analysis](internal/404_ERRORS_ANALYSIS.md) -- Route error investigation
- [404 Fix Summary](internal/404_FIX_SUMMARY.md) -- Route error remediation
- [Python Failures Investigation](internal/PYTHON_FAILURES_INVESTIGATION.md) -- Backend failure analysis
- [URL Ingestion Fix](internal/URL_INGESTION_FIX.md) -- URL ingestion bug fix
- [Webhook Consolidation Plan](internal/WEBHOOK_V1_V2_CONSOLIDATION_PLAN_2026-03-09.md) -- V1/V2 webhook migration plan
- [Portfolio Case Study](internal/portfolio_case_study.md) -- Internal case study
- [Secrets Reference](internal/SECRETS.md) -- Secret management reference

## 7. Tenant & Onboarding

- [Tenant Onboarding Guide](tenant/ONBOARDING_GUIDE.md) -- New tenant setup and configuration
- [Tenant API Examples](tenant/API_EXAMPLES.md) -- API usage examples for tenants
- [Tenant Overview](tenant/README.md) -- Multi-tenancy architecture overview
- [Beta Tester Guide](BETA_TESTER_GUIDE.md) -- Beta program onboarding and platform walkthrough

## 8. IP & Licensing

- [License](../LICENSE) -- Proprietary, RegEngine Inc.
- [Contributing](../CONTRIBUTING.md) -- Contribution guidelines
- [Changelog](../CHANGELOG.md) -- Version history and release notes

## 9. Root-Level Reference

- [README](../README.md) -- Project overview, setup, and quickstart
- [Architecture Review (Mar 27)](../ARCHITECTURE_REVIEW_2026-03-27.md) -- Architecture review findings
- [Security Review Critical (Mar 27)](../SECURITY_REVIEW_CRITICAL_2026-03-27.md) -- Critical security review findings
- [Tier 2-3 Review (Mar 27)](../TIER_2_3_REVIEW_2026-03-27.md) -- Lower-tier review findings
- [Debug Scan Report (Mar 27)](../DEBUG_SCAN_REPORT_2026-03-27.md) -- Debug scan results
- [Dead Code Report](../DEAD_CODE_REPORT.md) -- Dead code analysis
- [Deliverables Summary](../DELIVERABLES_SUMMARY.md) -- Summary of all delivered work
- [Remediation Plan](../REMEDIATION_PLAN.md) -- Issue remediation roadmap
- [Remediation Checklist](../REMEDIATION_CHECKLIST.md) -- Remediation task tracking
- [Production Env Checklist](../PRODUCTION_ENV_CHECKLIST.md) -- Production environment verification
- [Migration README](../MIGRATION_README.md) -- Database migration instructions
- [X-Request-ID Implementation](../X_REQUEST_ID_IMPLEMENTATION_SUMMARY.md) -- Request tracing implementation
- [Agents](../AGENTS.md) -- AI agent configuration (root)
- [Partner Outreach Emails](../partner_outreach_emails.md) -- Design partner outreach templates

---

## Quick-Start for Reviewers

1. **Start here:** [README](../README.md) and [Architecture Overview](ARCHITECTURE.md)
2. **Compliance depth:** [FSMA 204 MVP Spec](specs/FSMA_204_MVP_SPEC.md), [RTM](compliance/RTM.md), [Trust Framework](TRUST_FRAMEWORK.md)
3. **Security posture:** [SOC 2 Control Matrix](SOC2_CONTROL_MATRIX.md), [Incident Response](security/INCIDENT_RESPONSE.md), [Security Policy](../SECURITY.md)
4. **Operational maturity:** [Disaster Recovery](DISASTER_RECOVERY.md), [Runbooks](#runbooks), [Operations](OPERATIONS.md)
5. **Market context:** [Competitive Landscape](COMPETITIVE_LANDSCAPE_RESEARCH_2026-03-28.md), [Pricing](PRICING.md), [Product Roadmap](PRODUCT_ROADMAP.md)
