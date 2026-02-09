#!/bin/bash
# Create batch of Copilot-assignable issues for vertical development
# Each issue is scoped to be completable by Copilot coding agent

REPO="PetrefiedThunder/RegEngine"

create_issue() {
  local title="$1"
  local body="$2"
  local labels="$3"
  
  echo "Creating: $title"
  gh issue create --repo "$REPO" --title "$title" --body "$body" 2>&1 | tail -1
  sleep 2
}

# ═══════════════════════════════════════════════════════════════
# AEROSPACE — Has routes but zero tests
# ═══════════════════════════════════════════════════════════════

create_issue \
  "test: add tenant isolation tests for aerospace service" \
  "## Description
Add tenant isolation tests for the aerospace service, following the energy service pattern.

## Reference Implementation
See \`services/energy/tests/test_tenant_isolation.py\` for the established pattern.

## Tasks
- [ ] Create \`services/aerospace/tests/__init__.py\`
- [ ] Create \`services/aerospace/tests/conftest.py\` with DB fixtures
- [ ] Create \`services/aerospace/tests/test_tenant_isolation.py\` that verifies:
  - All models have \`tenant_id\` column
  - \`tenant_id\` columns are indexed
  - Cross-tenant data queries are prevented
- [ ] Ensure tests pass with \`pytest services/aerospace/tests/ -v\`

## Models to Test
Check \`services/aerospace/app/models.py\` for all SQLAlchemy models and verify each has tenant_id.

## Acceptance Criteria
- At least 5 test cases covering tenant isolation
- Tests pass in CI (no external DB required — use mocks or SQLite)
- Follow existing energy service test patterns"

create_issue \
  "test: add API route tests for aerospace service" \
  "## Description
Add unit tests for all aerospace API routes to ensure endpoints return correct responses.

## Reference
- Routes: \`services/aerospace/app/routes.py\` or \`services/aerospace/app/main.py\`
- Pattern: \`services/automotive/tests/test_ppap_upload_isolation.py\`

## Tasks
- [ ] Create \`services/aerospace/tests/test_routes.py\`
- [ ] Test each API endpoint with mocked DB dependencies
- [ ] Test authentication (require_api_key dependency)
- [ ] Test proper HTTP status codes (200, 201, 404, 422)
- [ ] Test request/response schema validation

## Acceptance Criteria
- Every route has at least one test case
- Tests use FastAPI TestClient with dependency overrides
- No external services required (all mocked)
- Tests pass with \`pytest services/aerospace/tests/ -v\`"

create_issue \
  "feat: add structured logging to aerospace service" \
  "## Description
Add structlog-based structured JSON logging to the aerospace service.

## Reference
See \`services/automotive/app/logging_config.py\` (if it exists after PR #7) or the structlog documentation.

## Tasks
- [ ] Add \`structlog>=23.1.0\` to \`services/aerospace/requirements.txt\`
- [ ] Create \`services/aerospace/app/logging_config.py\` with JSON output config
- [ ] Replace any \`print()\` statements with structured log calls
- [ ] Initialize logging in \`services/aerospace/app/main.py\`
- [ ] Add request_id to log context via middleware

## Acceptance Criteria
- All log output is structured JSON in production mode
- Console-friendly output in development mode
- No print() statements remain"

# ═══════════════════════════════════════════════════════════════
# CONSTRUCTION — Has routes but zero tests
# ═══════════════════════════════════════════════════════════════

create_issue \
  "test: add tenant isolation tests for construction service" \
  "## Description
Add tenant isolation tests for the construction service, following the energy service pattern.

## Reference Implementation
See \`services/energy/tests/test_tenant_isolation.py\` for the established pattern.

## Tasks
- [ ] Create \`services/construction/tests/__init__.py\`
- [ ] Create \`services/construction/tests/conftest.py\` with DB fixtures
- [ ] Create \`services/construction/tests/test_tenant_isolation.py\` that verifies:
  - All models have \`tenant_id\` column
  - \`tenant_id\` columns are indexed
  - Cross-tenant data queries are prevented
- [ ] Ensure tests pass with \`pytest services/construction/tests/ -v\`

## Models to Test
Check \`services/construction/app/models.py\` for all SQLAlchemy models.

## Acceptance Criteria
- At least 5 test cases covering tenant isolation
- Tests pass in CI
- Follow existing energy service test patterns"

create_issue \
  "test: add API route tests for construction service" \
  "## Description
Add unit tests for all construction API routes.

## Reference
- Routes: \`services/construction/app/routes.py\` or check main.py
- Pattern: \`services/automotive/tests/test_ppap_upload_isolation.py\`

## Tasks
- [ ] Create \`services/construction/tests/test_routes.py\`  
- [ ] Test each endpoint with mocked dependencies
- [ ] Test auth, status codes, and schema validation
- [ ] Verify CRUD operations for construction compliance records

## Acceptance Criteria
- Every route has at least one test
- Tests use FastAPI TestClient
- Tests pass with \`pytest services/construction/tests/ -v\`"

create_issue \
  "feat: add structured logging to construction service" \
  "## Description
Add structlog-based structured JSON logging to the construction service.

## Tasks
- [ ] Add \`structlog>=23.1.0\` to \`services/construction/requirements.txt\`
- [ ] Create \`services/construction/app/logging_config.py\`
- [ ] Replace print() with structured logs
- [ ] Initialize in main.py

## Reference
See aerospace or automotive service for the logging pattern."

# ═══════════════════════════════════════════════════════════════
# GAMING — Has routes but zero tests
# ═══════════════════════════════════════════════════════════════

create_issue \
  "test: add tenant isolation tests for gaming service" \
  "## Description
Add tenant isolation tests for the gaming service.

## Reference
See \`services/energy/tests/test_tenant_isolation.py\` for the pattern.

## Tasks
- [ ] Create \`services/gaming/tests/__init__.py\`
- [ ] Create \`services/gaming/tests/conftest.py\`
- [ ] Create \`services/gaming/tests/test_tenant_isolation.py\`
- [ ] Verify all models in \`services/gaming/app/models.py\` have tenant_id

## Acceptance Criteria
- At least 5 test cases
- Tests pass in CI
- Follow energy service patterns"

create_issue \
  "test: add API route tests for gaming service" \
  "## Description
Add unit tests for gaming API routes.

## Reference
- Routes: \`services/gaming/app/\`
- Pattern: \`services/automotive/tests/test_ppap_upload_isolation.py\`

## Tasks
- [ ] Create \`services/gaming/tests/test_routes.py\`
- [ ] Test each endpoint with mocked DB  
- [ ] Test auth and status codes
- [ ] Verify CRUD operations for gaming compliance records

## Acceptance Criteria
- Every route tested
- FastAPI TestClient with dependency overrides
- Tests pass with \`pytest services/gaming/tests/ -v\`"

create_issue \
  "feat: add structured logging to gaming service" \
  "## Description
Add structlog to the gaming service.

## Tasks
- [ ] Add \`structlog>=23.1.0\` to \`services/gaming/requirements.txt\`
- [ ] Create \`services/gaming/app/logging_config.py\`
- [ ] Replace print() with structured logs
- [ ] Initialize in main.py"

# ═══════════════════════════════════════════════════════════════
# MANUFACTURING — Has routes but zero tests
# ═══════════════════════════════════════════════════════════════

create_issue \
  "test: add tenant isolation tests for manufacturing service" \
  "## Description
Add tenant isolation tests for the manufacturing service.

## Reference
See \`services/energy/tests/test_tenant_isolation.py\`.

## Tasks
- [ ] Create \`services/manufacturing/tests/__init__.py\`
- [ ] Create \`services/manufacturing/tests/conftest.py\`
- [ ] Create \`services/manufacturing/tests/test_tenant_isolation.py\`
- [ ] Verify all models in \`services/manufacturing/app/models.py\` have tenant_id

## Acceptance Criteria
- At least 5 test cases
- Tests pass in CI"

create_issue \
  "test: add API route tests for manufacturing service" \
  "## Description
Add unit tests for manufacturing API routes.

## Tasks
- [ ] Create \`services/manufacturing/tests/test_routes.py\`
- [ ] Test each endpoint with mocked DB
- [ ] Test auth and status codes
- [ ] Verify CRUD operations

## Acceptance Criteria
- Every route tested
- Tests pass with \`pytest services/manufacturing/tests/ -v\`"

create_issue \
  "feat: add structured logging to manufacturing service" \
  "## Description
Add structlog to the manufacturing service.

## Tasks
- [ ] Add \`structlog>=23.1.0\` to \`services/manufacturing/requirements.txt\`
- [ ] Create \`services/manufacturing/app/logging_config.py\`
- [ ] Replace print() with structured logs
- [ ] Initialize in main.py"

# ═══════════════════════════════════════════════════════════════
# AUTOMOTIVE — Has 1 test, needs more coverage
# ═══════════════════════════════════════════════════════════════

create_issue \
  "test: add tenant isolation tests for automotive service" \
  "## Description
The automotive service has one test (test_ppap_upload_isolation.py) but needs dedicated tenant isolation tests.

## Reference
See \`services/energy/tests/test_tenant_isolation.py\`.

## Tasks
- [ ] Create \`services/automotive/tests/conftest.py\` if missing
- [ ] Create \`services/automotive/tests/test_tenant_isolation.py\`
- [ ] Test all models in \`services/automotive/app/models.py\` have tenant_id
- [ ] Verify cross-tenant isolation

## Acceptance Criteria
- At least 5 test cases
- Tests pass alongside existing test_ppap_upload_isolation.py"

# ═══════════════════════════════════════════════════════════════
# CROSS-CUTTING: Shared infrastructure improvements
# ═══════════════════════════════════════════════════════════════

create_issue \
  "feat: add health check endpoints to all vertical services" \
  "## Description
Add standardized health check endpoints to all vertical services that lack them.

## Tasks
For each service (aerospace, construction, gaming, manufacturing):
- [ ] Add \`GET /health\` endpoint returning \`{\"status\": \"healthy\", \"service\": \"<name>\", \"version\": \"1.0.0\"}\`
- [ ] Add \`GET /ready\` endpoint that checks DB connectivity
- [ ] Return 503 if DB is unreachable

## Reference
Check if energy or admin service already has health endpoints and follow that pattern.

## Acceptance Criteria
- All 4 services have /health and /ready endpoints
- Health endpoints don't require authentication
- Ready endpoint validates DB connection"

create_issue \
  "docs: add API documentation to all vertical services" \
  "## Description
Ensure all vertical services have proper OpenAPI documentation via FastAPI's built-in support.

## Tasks
For each service (aerospace, automotive, construction, gaming, manufacturing):
- [ ] Add proper \`title\`, \`description\`, and \`version\` to the FastAPI app initialization
- [ ] Add docstrings to all route handlers
- [ ] Add Pydantic model descriptions via \`Field(description=...)\`
- [ ] Add \`tags\` to route groups
- [ ] Verify docs are accessible at \`/docs\` endpoint

## Acceptance Criteria
- Each service has a descriptive OpenAPI spec
- All endpoints have descriptions
- All request/response models are documented"

create_issue \
  "feat: add CORS and rate limiting middleware to vertical services" \
  "## Description
Add standardized CORS configuration and basic rate limiting to all vertical services.

## Tasks
For each service (aerospace, automotive, construction, gaming, manufacturing):
- [ ] Add CORS middleware with configurable origins (env var \`ALLOWED_ORIGINS\`)
- [ ] Add basic rate limiting (100 req/min per API key)
- [ ] Add request ID middleware that generates a UUID per request
- [ ] Log request ID in all structured log output

## Reference
Check if admin or energy service already has CORS/rate limiting and follow that pattern.

## Acceptance Criteria
- CORS headers present in responses
- Rate limit headers (X-RateLimit-Remaining, X-RateLimit-Reset) in responses
- Request ID in response headers and logs"

echo ""
echo "✅ All issues created! Run 'gh issue list --repo $REPO' to see them."
