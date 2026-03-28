# RegEngine API Audit - Remediation Checklist

**Status:** In Progress
**Last Updated:** 2026-03-27
**Target Completion:** 2026-04-17 (3 weeks)

---

## PART A: API Design & Contract Quality

### Finding 1: Inconsistent API Versioning
- [ ] Define versioning standard (all endpoints under /v1/)
- [ ] Create `services/shared/routes.py` with API_PREFIX constant
- [ ] Update admin service v1_router prefix
- [ ] Update ingestion service route prefixes
- [ ] Update graph service routes (add /v1/)
- [ ] Update compliance service routes (add /v1/)
- [ ] Audit all POST/PUT/DELETE endpoints for prefix consistency
- [ ] Test client integration with versioned endpoints
- [ ] Document versioning policy in CONTRIBUTING.md
- **Owner:** Backend Lead | **Target Date:** 2026-03-31

### Finding 2: Pydantic Model Coverage
- [ ] Audit admin service routes - identify endpoints missing response_model
- [ ] Audit ingestion service routes - identify unvalidated responses
- [ ] Audit compliance service routes - identify unvalidated responses
- [ ] Audit graph service routes - identify unvalidated responses
- [ ] Create list[Model] variants for all list endpoints
- [ ] Add request_model validation to POST/PUT endpoints
- [ ] Test Pydantic validation errors return 422 correctly
- [ ] Update OpenAPI docs with model definitions
- [ ] Create models/base.py with reusable base classes
- [ ] Add model tests to ensure schema correctness
- **Owner:** Backend Lead | **Target Date:** 2026-04-07

### Finding 3: Error Handling Standardization (CRITICAL)
- [ ] Create `services/shared/errors.py` with APIError class
- [ ] Create `services/shared/models.py` with APIErrorResponse
- [ ] Update `services/shared/error_handling.py` to format APIError responses
- [ ] Replace HTTPException in admin service (routes.py)
  - [ ] Lines 137-140 (unauthorized)
  - [ ] Lines 364-367 (not found)
  - [ ] All other HTTPException instances
- [ ] Replace HTTPException in ingestion service (all route files)
- [ ] Replace HTTPException in compliance service
- [ ] Replace HTTPException in graph service
- [ ] Add correlation_id to all error responses
- [ ] Test error response format consistency
- [ ] Document error codes in API documentation
- **Owner:** Backend Lead + Team | **Target Date:** 2026-03-31

### Finding 4: Unbounded Pagination (CRITICAL)
- [ ] Audit GET /v1/ingest/discovery/queue (replace 0, -1)
- [ ] Create PaginatedResponse generic model
- [ ] Add skip/limit parameters to /admin/keys endpoint
- [ ] Add skip/limit parameters to /admin/tenants endpoint
- [ ] Add skip/limit parameters to /compliance/requirements endpoint
- [ ] Add skip/limit parameters to /graph/nodes endpoint
- [ ] Add skip/limit to all other list endpoints
- [ ] Implement query parameter validation (limit <= 1000, skip <= 100000)
- [ ] Create validation middleware for pagination bounds
- [ ] Test with large offset/limit values
- [ ] Document pagination in API guide
- **Owner:** Backend Lead + Security | **Target Date:** 2026-04-04

### Finding 5: OpenAPI/Swagger Documentation
- [ ] Add service descriptions to all main.py files
- [ ] Create custom_openapi() function in each service
- [ ] Add X-RegEngine-API-Key security scheme to OpenAPI
- [ ] Add security requirement to all protected endpoints
- [ ] Document error response schemas
- [ ] Add example requests/responses for key endpoints
- [ ] Test /docs and /redoc endpoints
- [ ] Verify OpenAPI schema is valid (openapi-spec-validator)
- [ ] Add OpenAPI schema to CI/CD validation
- **Owner:** DevDocs | **Target Date:** 2026-04-07

### Finding 6: Debug Endpoint ("Show the Mess")
- [ ] Search codebase for existing debug endpoints
- [ ] Create /v1/admin/debug/system-state endpoint
- [ ] Include database, Redis, Kafka health checks
- [ ] Add active tenant count
- [ ] Add recent errors list
- [ ] Restrict to admin_key only
- [ ] Add conditional enable flag (ENABLE_DEBUG_ENDPOINTS)
- [ ] Test access control
- [ ] Document in development guide
- **Owner:** Backend Lead | **Target Date:** 2026-04-07

---

## PART B: Deployment & Infrastructure

### Finding 7: Environment Variable Validation
- [ ] Create `services/shared/config_validation.py` with BaseSettings
- [ ] Define required variables in config classes
- [ ] Define optional variables with defaults
- [ ] Test startup failure when required vars missing
- [ ] Audit .env.example for completeness
- [ ] Add all missing variables to .env.example
- [ ] Add descriptions and production warnings
- [ ] Create .env.docker template
- [ ] Document config loading in DEPLOYMENT.md
- [ ] Add config validation to CI/CD
- **Owner:** DevOps + Backend | **Target Date:** 2026-04-07

### Finding 8: Vercel Configuration Expansion
- [ ] Review and update frontend/vercel.json
- [ ] Increase ingestion maxDuration from 60 to 120 seconds
- [ ] Add memory configuration per function
- [ ] Add graph API function configuration
- [ ] Add nlp API function configuration
- [ ] Add environment variable overrides
- [ ] Test function timeout behavior
- [ ] Monitor Vercel logs for timeout errors
- [ ] Document Vercel-specific settings
- **Owner:** DevOps | **Target Date:** 2026-04-04

### Finding 9: Railway Configuration (NEW)
- [ ] Create railway.toml with service definitions
- [ ] Define admin service configuration
- [ ] Define ingestion service configuration
- [ ] Define compliance service configuration
- [ ] Define graph service configuration
- [ ] Define nlp service configuration
- [ ] Create Procfile for Heroku compatibility
- [ ] Test Railway build process
- [ ] Document Railway deployment steps
- [ ] Create DEPLOYMENT_RAILWAY.md guide
- **Owner:** DevOps | **Target Date:** 2026-04-04

### Finding 10: Health Check Standardization
- [ ] Create `services/shared/health.py` with HealthResponse model
- [ ] Implement consistent health() endpoint in all services
- [ ] Implement readiness() endpoint in all services
- [ ] Add dependency health checks (PostgreSQL, Redis, Kafka)
- [ ] Return structured dependency status
- [ ] Test health endpoints return correct status codes
- [ ] Add latency_ms to dependency checks
- [ ] Document health endpoint behavior
- [ ] Create Kubernetes probe YAML examples
- [ ] Add health check monitoring to observability stack
- **Owner:** DevOps + Observability | **Target Date:** 2026-04-07

### Finding 11: Dependency Pinning & Lock Files
- [ ] Install pip-tools in dev environment
- [ ] Create requirements.in with high-level dependencies
- [ ] Run pip-compile to generate requirements.lock
- [ ] Audit and replace floating constraints with exact pins
- [ ] Fix setuptools constraint (>=75.0,<76)
- [ ] Test installation from lock file
- [ ] Commit requirements.lock to git
- [ ] Update CI/CD to use `pip install -r requirements.lock`
- [ ] Add lock file update job (quarterly security audit)
- [ ] Verify package-lock.json is committed (frontend)
- [ ] Document lock file strategy in CONTRIBUTING.md
- [ ] Create dependency update policy
- **Owner:** DevOps + Backend | **Target Date:** 2026-04-04

### Finding 12: CI/CD Enforcement
- [ ] Remove --exit-zero flag from flake8 linting
- [ ] Add mypy type checking to CI pipeline
- [ ] Add --cov-fail-under=70 to pytest commands
- [ ] Create .pre-commit-config.yaml
- [ ] Install pre-commit hooks in development environment
- [ ] Add pre-commit to CONTRIBUTING.md onboarding
- [ ] Test CI pipeline blocks on coverage failure
- [ ] Test CI pipeline blocks on type errors
- [ ] Test CI pipeline blocks on linting failures
- [ ] Document CI/CD requirements in CONTRIBUTING.md
- [ ] Set up GitHub branch protection rules
- **Owner:** DevOps + QA | **Target Date:** 2026-04-07

---

## Implementation Timeline

### Week 1 (Mar 27 - Mar 31)
**Sprint Focus:** Critical security issues
- [x] Finding 3: Error handling (Complete by Mar 31)
- [x] Finding 4: Pagination (Complete by Mar 31)
- [x] Finding 1: Versioning standard (Complete by Mar 31)

### Week 2 (Apr 1 - Apr 7)
**Sprint Focus:** API quality & documentation
- [x] Finding 2: Pydantic models (Complete by Apr 7)
- [x] Finding 7: Env validation (Complete by Apr 7)
- [x] Finding 5: OpenAPI docs (Complete by Apr 7)
- [x] Finding 10: Health checks (Complete by Apr 7)
- [x] Finding 6: Debug endpoint (Complete by Apr 7)

### Week 3 (Apr 8 - Apr 14)
**Sprint Focus:** Deployment & infrastructure
- [x] Finding 8: Vercel config (Complete by Apr 10)
- [x] Finding 9: Railway config (Complete by Apr 11)
- [x] Finding 11: Lock files (Complete by Apr 12)
- [x] Finding 12: CI/CD (Complete by Apr 12)

### Week 4 (Apr 15 - Apr 17)
**Sprint Focus:** Testing & validation
- [x] Regression testing across all services
- [x] Full E2E test suite runs
- [x] Performance testing (no regressions)
- [x] Documentation complete & reviewed

---

## Sign-Off

| Role | Name | Status | Date |
|------|------|--------|------|
| Backend Lead | TBD | Pending | - |
| DevOps | TBD | Pending | - |
| QA Lead | TBD | Pending | - |
| Project Manager | TBD | Pending | - |

---

## Notes

- Mark items complete as they're implemented
- Update status weekly
- Escalate blockers immediately
- Document any deviations from checklist
- Maintain this file as source of truth for remediation progress