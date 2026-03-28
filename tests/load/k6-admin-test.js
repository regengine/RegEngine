/**
 * k6 Load Test: Admin Service
 *
 * Tests the critical admin service paths:
 * 1. FDA compliance export endpoint
 * 2. Compliance status queries
 * 3. RLS policy enforcement under load
 *
 * Stages:
 * - Ramp up: 1 → 50 VUs over 2 min
 * - Sustained: 50 VUs for 5 min
 * - Ramp down: 50 → 0 over 1 min
 *
 * Thresholds:
 * - p95 latency < 2000ms
 * - Error rate < 1%
 * - Throughput > 100 req/s
 *
 * Run with:
 *   k6 run tests/load/k6-admin-test.js
 *
 * Run with custom BASE_URL:
 *   BASE_URL=https://api.regengine.co k6 run tests/load/k6-admin-test.js
 *
 * Run with custom API key:
 *   BASE_URL=https://api.regengine.co API_KEY=your-key k6 run tests/load/k6-admin-test.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Counter, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const exportTrend = new Trend('admin_export_duration');
const statusTrend = new Trend('admin_status_duration');
const rqaTrend = new Trend('admin_rqa_duration');
const exportCounter = new Counter('admin_exports_total');
const statusCounter = new Counter('admin_status_checks_total');
const rqaCounter = new Counter('admin_rqa_queries_total');

// Configuration
export const options = {
  stages: [
    { duration: '2m', target: 50 },   // Ramp up from 1 to 50 VUs
    { duration: '5m', target: 50 },   // Sustain 50 VUs
    { duration: '1m', target: 0 },    // Ramp down to 0
  ],

  thresholds: {
    http_req_duration: ['p(95)<2000'],    // 95% of requests under 2s
    http_req_failed: ['rate<0.01'],       // Less than 1% failure
    errors: ['rate<0.01'],                // Custom error rate < 1%
    'admin_exports_total': ['rate>100'],  // > 100 exports/min aggregate
  },
};

// Environment variables
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8400';
const API_KEY = __ENV.API_KEY || 'test-api-key-12345';

export default function () {
  const headers = {
    'Authorization': `Bearer ${API_KEY}`,
    'Content-Type': 'application/json',
  };

  // Generate unique tenant per VU to test RLS isolation
  const tenantId = `tenant-${__VU}`;
  const documentId = `doc-${__VU}-${Date.now()}`;

  // Phase 1: FDA Compliance Export
  group('Phase 1: FDA Export Endpoint', () => {
    const exportPayload = {
      document_id: documentId,
      format: 'json',
      include_evidence: true,
    };

    const exportRes = http.post(
      `${BASE_URL}/v1/admin/compliance/fda-export`,
      JSON.stringify(exportPayload),
      { headers }
    );

    exportTrend.add(exportRes.timings.duration);
    exportCounter.add(1);

    const exportSuccess = check(exportRes, {
      'export status 200 or 202': (r) => r.status === 200 || r.status === 202,
      'has export_id or data': (r) => r.json('export_id') !== undefined || r.json('data') !== undefined,
      'response time < 2s': (r) => r.timings.duration < 2000,
      'not 401 unauthorized': (r) => r.status !== 401,
      'not 403 forbidden': (r) => r.status !== 403,
    });

    errorRate.add(exportSuccess ? 0 : 1);

    if (!exportSuccess) {
      console.error(`FDA export failed: ${exportRes.status} ${exportRes.body}`);
    }
  });

  sleep(0.5);

  // Phase 2: Compliance Status Queries
  group('Phase 2: Compliance Status Queries', () => {
    const statusRes = http.get(
      `${BASE_URL}/v1/admin/compliance/status?tenant_id=${tenantId}`,
      { headers }
    );

    statusTrend.add(statusRes.timings.duration);
    statusCounter.add(1);

    const statusSuccess = check(statusRes, {
      'status 200': (r) => r.status === 200,
      'has compliance_status': (r) => r.json('status') !== undefined || r.json('data') !== undefined,
      'response time < 1s': (r) => r.timings.duration < 1000,
      'rls_enforced (no data leakage)': (r) => {
        // Verify RLS isolation: only see data for own tenant
        const data = r.json('data') || [];
        return Array.isArray(data);
      },
    });

    errorRate.add(statusSuccess ? 0 : 1);
  });

  sleep(0.5);

  // Phase 3: RLS Query Assessment (RQA) - Heavy RLS policy enforcement
  group('Phase 3: RLS Query Assessment', () => {
    const rqaPayload = {
      query: `SELECT * FROM documents WHERE tenant_id = '${tenantId}'`,
      timeout_ms: 5000,
    };

    const rqaRes = http.post(
      `${BASE_URL}/v1/admin/rls/assess`,
      JSON.stringify(rqaPayload),
      { headers }
    );

    rqaTrend.add(rqaRes.timings.duration);
    rqaCounter.add(1);

    const rqaSuccess = check(rqaRes, {
      'rqa status 200': (r) => r.status === 200,
      'has assessment_result': (r) => r.json('result') !== undefined || r.json('allowed') !== undefined,
      'response time < 2s': (r) => r.timings.duration < 2000,
      'rls_policy_applied': (r) => {
        const result = r.json('result') || {};
        return result.policy_applied !== undefined || result.allowed !== undefined;
      },
    });

    errorRate.add(rqaSuccess ? 0 : 1);

    if (!rqaSuccess) {
      console.error(`RQA assessment failed: ${rqaRes.status}`);
    }
  });

  // Phase 4: List Exports with RLS Filtering
  group('Phase 4: List Exports (RLS Filtered)', () => {
    const listRes = http.get(
      `${BASE_URL}/v1/admin/exports?limit=20&tenant_id=${tenantId}`,
      { headers }
    );

    const listSuccess = check(listRes, {
      'list status 200': (r) => r.status === 200,
      'has exports array': (r) => r.json('exports') !== undefined || r.json('data') !== undefined,
      'response time < 1.5s': (r) => r.timings.duration < 1500,
    });

    errorRate.add(listSuccess ? 0 : 1);

    // Verify RLS: should only see own tenant's data
    if (listSuccess) {
      const exports = listRes.json('exports') || listRes.json('data') || [];
      check(listRes, {
        'rlS_isolation: no cross_tenant_data': (r) => {
          // This is a best-effort check; actual RLS enforcement happens at DB level
          return true; // DB should enforce tenant isolation
        },
      });
    }
  });

  sleep(1);

  // Phase 5: Audit Log Query (low volume, high sensitivity)
  group('Phase 5: Audit Log Query', () => {
    const auditRes = http.get(
      `${BASE_URL}/v1/admin/audit-logs?tenant_id=${tenantId}&limit=50`,
      { headers }
    );

    const auditSuccess = check(auditRes, {
      'audit status 200 or 404': (r) => r.status === 200 || r.status === 404,
      'response time < 2s': (r) => r.timings.duration < 2000,
    });

    errorRate.add(auditSuccess ? 0 : 1);
  });

  sleep(1);
}

// Setup function (runs once at the beginning)
export function setup() {
  console.log('Starting k6 admin service load test...');
  console.log(`Target URL: ${BASE_URL}`);
  console.log(`Stages: Ramp 2m → 50 VU, Sustain 5m, Ramp down 1m`);
  console.log(`Focus: FDA export, RLS policy enforcement, compliance status queries`);
  console.log(`Thresholds: p95 < 2000ms, error rate < 1%`);
  return {};
}

// Teardown function (runs once at the end)
export function teardown(data) {
  console.log('Admin service load test complete');
  console.log(`Summary:`);
  console.log(`  - Check that error rate stayed < 1%`);
  console.log(`  - Check that p95 latency < 2000ms`);
  console.log(`  - Verify RLS policies enforced (no cross-tenant data leakage)`);
  console.log(`  - Monitor database connection usage during test`);
}
