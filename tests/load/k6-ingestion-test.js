/**
 * k6 Load Test: Ingestion Service MVP Flow
 *
 * Tests the critical ingestion path:
 * 1. CSV file upload (simulated multipart)
 * 2. Status polling (check processing status)
 * 3. Data export (retrieve processed data)
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
 *   k6 run tests/load/k6-ingestion-test.js
 *
 * Run with custom BASE_URL:
 *   BASE_URL=https://api.regengine.co k6 run tests/load/k6-ingestion-test.js
 *
 * Run with custom API key:
 *   BASE_URL=https://api.regengine.co API_KEY=your-key k6 run tests/load/k6-ingestion-test.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Counter, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const uploadTrend = new Trend('ingestion_upload_duration');
const statusTrend = new Trend('ingestion_status_duration');
const exportTrend = new Trend('ingestion_export_duration');
const uploadCounter = new Counter('ingestion_uploads_total');
const statusCounter = new Counter('ingestion_status_checks_total');
const exportCounter = new Counter('ingestion_exports_total');

// Configuration
export const options = {
  stages: [
    { duration: '2m', target: 50 },   // Ramp up from 1 to 50 VUs
    { duration: '5m', target: 50 },   // Sustain 50 VUs
    { duration: '1m', target: 0 },    // Ramp down to 0
  ],

  thresholds: {
    http_req_duration: ['p(95)<2000'],   // 95% of requests under 2s
    http_req_failed: ['rate<0.01'],      // Less than 1% failure
    errors: ['rate<0.01'],               // Custom error rate < 1%
    'ingestion_uploads_total': ['rate>100'],  // > 100 uploads/min
  },
};

// Environment variables
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8100';
const API_KEY = __ENV.API_KEY || 'test-api-key-12345';

export default function () {
  const headers = {
    'Authorization': `Bearer ${API_KEY}`,
    'Content-Type': 'application/json',
  };

  // Generate test data per VU
  const csvData = generateTestCSV();
  const uploadId = `load-test-${__VU}-${Date.now()}`;

  // Phase 1: CSV Upload
  group('Phase 1: CSV Upload', () => {
    const uploadPayload = {
      filename: `test-${__VU}-${Date.now()}.csv`,
      data: csvData,
      metadata: {
        organization_id: `org-${__VU}`,
        document_type: 'FSMA_compliance',
      },
    };

    const uploadRes = http.post(
      `${BASE_URL}/v1/ingest/upload`,
      JSON.stringify(uploadPayload),
      { headers }
    );

    const uploadSuccess = check(uploadRes, {
      'upload status 202 or 200': (r) => r.status === 202 || r.status === 200,
      'has upload_id': (r) => r.json('upload_id') !== undefined || r.json('id') !== undefined,
      'response time < 2s': (r) => r.timings.duration < 2000,
    });

    uploadTrend.add(uploadRes.timings.duration);
    uploadCounter.add(1);
    errorRate.add(uploadSuccess ? 0 : 1);

    if (!uploadSuccess) {
      console.error(`Upload failed: ${uploadRes.status} ${uploadRes.body}`);
      return; // Skip status check if upload failed
    }

    const returnedUploadId = uploadRes.json('upload_id') || uploadRes.json('id');
    if (!returnedUploadId) {
      console.error('No upload_id in response');
      return;
    }

    sleep(1);

    // Phase 2: Status Polling (poll up to 10 times with 1s delay)
    group('Phase 2: Status Polling', () => {
      let statusSuccess = false;
      let attempts = 0;
      const maxAttempts = 10;

      while (attempts < maxAttempts && !statusSuccess) {
        const statusRes = http.get(
          `${BASE_URL}/v1/ingest/status/${returnedUploadId}`,
          { headers }
        );

        statusTrend.add(statusRes.timings.duration);
        statusCounter.add(1);

        const statusCheck = check(statusRes, {
          'status 200': (r) => r.status === 200,
          'has processing_status': (r) => r.json('status') !== undefined,
          'response time < 1s': (r) => r.timings.duration < 1000,
        });

        errorRate.add(statusCheck ? 0 : 1);

        const currentStatus = statusRes.json('status');
        if (currentStatus === 'completed' || currentStatus === 'success') {
          statusSuccess = true;
          break;
        }

        attempts++;
        if (attempts < maxAttempts) {
          sleep(1); // Wait before next poll
        }
      }

      if (!statusSuccess && attempts >= maxAttempts) {
        console.warn(`Upload ${returnedUploadId} did not complete after ${maxAttempts} attempts`);
      }
    });

    sleep(1);

    // Phase 3: Export Data
    group('Phase 3: Export Data', () => {
      const exportRes = http.get(
        `${BASE_URL}/v1/ingest/export/${returnedUploadId}`,
        { headers }
      );

      exportTrend.add(exportRes.timings.duration);
      exportCounter.add(1);

      const exportSuccess = check(exportRes, {
        'export status 200 or 404': (r) => r.status === 200 || r.status === 404, // 404 if not ready is OK
        'response time < 2s': (r) => r.timings.duration < 2000,
      });

      errorRate.add(exportSuccess ? 0 : 1);

      if (exportRes.status === 200) {
        const dataCheck = check(exportRes, {
          'has data': (r) => r.json('data') !== undefined || r.body.length > 0,
        });
        errorRate.add(dataCheck ? 0 : 1);
      }
    });
  });

  // Think time between iterations
  sleep(2);
}

/**
 * Generate mock CSV data for ingestion
 * Simulates a compliance document with various fields
 */
function generateTestCSV() {
  const rows = [
    'Document ID,Facility Name,Hazard Analysis,Preventive Controls,Monitoring',
    `DOC-${Date.now()},Test Facility ${__VU},Yes,Yes,Yes`,
    `DOC-${Date.now() + 1},Facility 2,No,Yes,Yes`,
    `DOC-${Date.now() + 2},Facility 3,Yes,No,Yes`,
  ];

  return rows.join('\n');
}

// Setup function (runs once at the beginning)
export function setup() {
  console.log('Starting k6 ingestion load test...');
  console.log(`Target URL: ${BASE_URL}`);
  console.log(`Stages: Ramp 2m → 50 VU, Sustain 5m, Ramp down 1m`);
  console.log(`Thresholds: p95 < 2000ms, error rate < 1%`);
  return {};
}

// Teardown function (runs once at the end)
export function teardown(data) {
  console.log('Load test complete');
  console.log(`Summary: Check k6 stdout for aggregate results`);
}
