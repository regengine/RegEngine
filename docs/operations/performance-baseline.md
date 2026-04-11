# Performance Baseline & SLA Documentation

**Date:** January 27, 2026  
**Version:** 1.0.0

---

## Performance SLAs

### Response Time Targets

| Endpoint Category | p50 | p95 | p99 | Timeout |
|------------------|-----|-----|-----|---------|
| Health Checks | 50ms | 100ms | 200ms | 5s |
| Read Operations | 200ms | 500ms | 1000ms | 10s |
| Write Operations | 300ms | 1000ms | 2000ms | 15s |
| Complex Queries | 500ms | 2000ms | 5000ms | 30s |
| Exports | 1s | 5s | 10s | 60s |

### Throughput Targets

- **Sustained Load:** 50 concurrent users
- **Peak Load:** 100 concurrent users  
- **Requests/sec:** 100-500 RPS
- **Error Rate:** < 1%

---

## Load Test Configuration

### Test Stages

```javascript
stages: [
  { duration: '30s', target: 10 },   // Warm up
  { duration: '1m', target: 50 },    // Ramp to sustained
  { duration: '3m', target: 50 },    // Hold sustained
  { duration: '1m', target: 100 },   // Peak load
  { duration: '1m', target: 100 },   // Hold peak
  { duration: '30s', target: 0 },    // Ramp down
]
```

**Total Duration:** ~7 minutes  
**Max Users:** 100 concurrent

### Thresholds

```javascript
thresholds: {
  http_req_duration: ['p(95)<2000'],  // 95% under 2s
  http_req_failed: ['rate<0.01'],     // <1% failure
  errors: ['rate<0.05'],              // <5% errors
}
```

---

## Baseline Metrics (To Be Captured)

### Run Instructions

```bash
# Start all services
docker-compose up -d

# Wait for health
sleep 10

# Run baseline test
./scripts/run-performance-baseline.sh

# View results
cat test-results/load/summary-*.json
```

### Expected Results

**Response Times (ms):**
| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| p50 | < 300 | TBD | ⏳ |
| p95 | < 2000 | TBD | ⏳ |
| p99 | < 5000 | TBD | ⏳ |

**Error Rates:**
| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| HTTP Errors | < 1% | TBD | ⏳ |
| App Errors | < 5% | TBD | ⏳ |

**Throughput:**
| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Requests/sec | 100-500 | TBD | ⏳ |
| Success Rate | > 99% | TBD | ⏳ |

---

## Performance Monitoring

### Real-time Metrics (Sentry)

```typescript
// Already configured in sentry.client.config.ts
{
  tracesSampleRate: 0.1,  // 10% of transactions
}
```

**Tracked Metrics:**
- Page load times
- API request duration
- Error rates by endpoint
- User experience metrics (LCP, FID, CLS)

### Database Metrics (To Be Added)

See: `docs/database-optimization.md`

- Query execution time
- Connection pool usage
- Slow query log
- Index usage statistics

---

## Performance Regression Testing

### CI Integration (Future)

```yaml
# .github/workflows/performance.yml
name: Performance Tests

on:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2am
  workflow_dispatch:

jobs:
  performance:
    runs-on: ubuntu-latest
    steps:
      - name: Run k6 tests
        run: ./scripts/run-performance-baseline.sh
      
      - name: Compare with baseline
        run: ./scripts/compare-performance.sh
      
      - name: Fail if regression
        run: |
          # Fail if p95 > 2500ms (25% regression)
          # Fail if error rate > 2%
```

---

## Benchmark History

### Baseline Run (Planned)

**Date:** TBD  
**Commit:** TBD  
**Results:** Pending first run

Future baselines will be added here for comparison.

---

## Quick Reference

### Run Performance Test
```bash
./scripts/run-performance-baseline.sh
```

### View Latest Results
```bash
cat test-results/load/summary-*.json | tail -1
```

### Check Service Health
```bash
curl http://localhost:8000/health
curl http://localhost:8001/health  # Energy
```

---

**Status:** Framework ready, baseline pending ⏳  
**Next Step:** Execute baseline run when services are stable
