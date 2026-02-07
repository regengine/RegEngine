# RegEngine Complete Testing Requirements

## Current Test Coverage

| Category | Files | Status |
|----------|-------|--------|
| **Shared/Unit** | 55 | ✅ Comprehensive |
| **Contract** | 2 | ✅ New - 40 passing |
| **Admin** | 3 | ⚠️ Basic |
| **Ingestion** | 2 | ⚠️ Basic |
| **Graph** | 1 | ⚠️ Basic |
| **NLP** | 1 | ⚠️ Basic |
| **Compliance** | 1 | ⚠️ Basic |
| **Opportunity** | 1 | ⚠️ Basic |
| **E2E** | 1 | ⚠️ Has mock fallback |
| **Load** | 2 | ✅ Locust defined |
| **Total** | 75+ | |

---

## What's Needed for Complete Testing

### 1. Prerequisites (Infrastructure)

```bash
# Required services running
docker compose up -d

# Required Python packages
pip install pytest pytest-asyncio httpx locust

# Frontend tests
cd frontend && npm install
```

### 2. Test Execution Commands

```bash
# Unit tests (fast, no services needed)
python3 -m pytest tests/shared/ -v

# Contract tests (requires services)
python3 -m pytest tests/contract/ -v

# Service-specific tests
python3 -m pytest tests/admin/ -v
python3 -m pytest tests/ingestion/ -v

# E2E tests (full integration)
python3 -m pytest tests/e2e/ -v

# Load tests
cd tests/load && locust -f test_load.py

# Frontend tests
cd frontend && npm run test:run
```

---

## Testing Gaps & Recommendations

### 🔴 Critical Gaps

| Gap | Risk | Recommendation |
|-----|------|----------------|
| **Service integration tests** | Services work in isolation but fail together | Add cross-service journey tests |
| **Database migration tests** | Schema changes may break production | Add migration rollback tests |
| **Event consumer tests** | Kafka messages may be lost/malformed | Add consumer integration tests |

### 🟡 Important Gaps

| Gap | Risk | Recommendation |
|-----|------|----------------|
| **Auth boundary tests** | Tenant isolation bypass | Add negative auth tests |
| **Chaos/failure tests** | Unknown failure modes | Add circuit breaker tests |
| **Performance baselines** | Regressions go unnoticed | Add benchmark tests with thresholds |

### 🟢 Nice to Have

| Gap | Benefit | Recommendation |
|-----|---------|----------------|
| **Visual regression tests** | UI consistency | Add Playwright screenshot tests |
| **API snapshot tests** | Catch breaking changes | Add Jest snapshot for responses |
| **Fuzz testing** | Security hardening | Add hypothesis-based property tests |

---

## Recommended Test Structure

```
tests/
├── unit/                    # Fast, no dependencies
│   ├── shared/              # ✅ 55 files exist
│   └── services/            # Add per-service unit tests
│
├── integration/             # Service + dependencies
│   ├── database/            # PostgreSQL, Neo4j
│   ├── events/              # Kafka producers/consumers
│   └── cache/               # Redis
│
├── contract/                # ✅ API contracts
│   ├── test_admin_api.py
│   └── test_service_contracts.py
│
├── e2e/                     # Full user journeys
│   ├── test_ingestion_flow.py
│   ├── test_compliance_flow.py
│   └── test_review_flow.py
│
├── load/                    # ✅ Performance
│   └── test_load.py
│
└── security/                # NEW: Security-focused
    ├── test_tenant_isolation.py
    ├── test_ssrf_protection.py
    └── test_auth_bypass.py
```

---

## Quick Test Validation Script

```bash
#!/bin/bash
# scripts/test-all.sh

set -e

echo "=== 1. Unit Tests ==="
python3 -m pytest tests/shared/ -q --tb=no

echo "=== 2. Contract Tests ==="
python3 -m pytest tests/contract/ -q --tb=no

echo "=== 3. Service Health ==="
for port in 8002 8100 8200 8300 8400 8500; do
  status=$(curl -sf http://localhost:$port/health | jq -r .status 2>/dev/null || echo "DOWN")
  echo "Port $port: $status"
done

echo "=== 4. Frontend Tests ==="
cd frontend && npm run test:run -- --reporter=dot 2>/dev/null || echo "Frontend tests need review"

echo "=== All Checks Complete ==="
```

---

## CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Test Suite

on: [push, pull_request]

jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Unit Tests
        run: python3 -m pytest tests/shared/ -v

  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
      redis:
        image: redis:7
    steps:
      - uses: actions/checkout@v4
      - name: Integration Tests
        run: python3 -m pytest tests/integration/ -v

  e2e:
    runs-on: ubuntu-latest
    needs: [unit, integration]
    steps:
      - uses: actions/checkout@v4
      - name: Start Services
        run: docker compose up -d
      - name: E2E Tests
        run: python3 -m pytest tests/e2e/ -v
```

---

## Test Priority for Beta

| Priority | Test Type | Effort | Impact |
|----------|-----------|--------|--------|
| **P0** | Health checks pass | 5 min | ✅ Done |
| **P0** | Contract tests pass | 30 min | ✅ Done |
| **P1** | E2E ingestion flow | 2 hr | 🔴 Needed |
| **P1** | Tenant isolation tests | 2 hr | 🔴 Needed |
| **P2** | Load test baselines | 1 hr | 🟡 Nice |
| **P3** | Visual regression | 4 hr | 🟢 Future |
