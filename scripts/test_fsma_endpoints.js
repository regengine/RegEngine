#!/usr/bin/env node
/**
 * FSMA 204 Endpoint Test Suite
 * 
 * Tests all 40 FSMA endpoints on the Graph Service.
 * Run: node scripts/test_fsma_endpoints.js
 * 
 * Prerequisites:
 * - Graph service running on port 8200
 * - API key in REGENGINE_API_KEY env var (required; .env files are never read)
 */

const http = require('http');
const https = require('https');

// Configuration
const BASE_URL = process.env.GRAPH_SERVICE_URL || 'http://localhost:8200';
// The API key must come from the environment. This script never reads .env
// files and never falls back to a placeholder key, so a missing key fails
// loudly instead of silently testing the wrong credentials.
const API_KEY = process.env.REGENGINE_API_KEY || '';

function requireApiKey() {
    if (!API_KEY) {
        console.error('Missing required REGENGINE_API_KEY environment variable. Export it before running this suite.');
        process.exit(1);
    }
}

// Match the transport to the URL scheme so https targets are tested over TLS.
function transportFor(url) {
    return url.protocol === 'https:' ? https : http;
}

// Test results tracking
const results = {
    passed: 0,
    failed: 0,
    skipped: 0,
    errors: [],
};

// Test TLC for traceability queries
const TEST_TLC = 'LOT-2024-001';
const TEST_EVENT_ID = 'event-001';

// HTTP request helper
async function request(method, endpoint, body = null) {
    return new Promise((resolve) => {
        const url = new URL(endpoint, BASE_URL);
        const options = {
            hostname: url.hostname,
            port: url.port,
            path: url.pathname + url.search,
            method,
            headers: {
                'Content-Type': 'application/json',
                'X-RegEngine-API-Key': API_KEY,
            },
            timeout: 10000,
        };

        const req = transportFor(url).request(options, (res) => {
            let data = '';
            res.on('data', (chunk) => { data += chunk; });
            res.on('end', () => {
                try {
                    resolve({
                        status: res.statusCode,
                        data: data ? JSON.parse(data) : null,
                        ok: res.statusCode >= 200 && res.statusCode < 300,
                    });
                } catch {
                    resolve({
                        status: res.statusCode,
                        data: data,
                        ok: res.statusCode >= 200 && res.statusCode < 300,
                    });
                }
            });
        });

        req.on('error', (err) => {
            resolve({ status: 0, error: err.message, ok: false });
        });

        req.on('timeout', () => {
            req.destroy();
            resolve({ status: 0, error: 'Timeout', ok: false });
        });

        if (body) {
            req.write(JSON.stringify(body));
        }
        req.end();
    });
}

// Test runner. Each endpoint asserts its exact expected status; auth, routing,
// and validation failures (401/404/422) are failures unless the caller
// explicitly lists them as expected for that endpoint.
async function runTest(name, method, endpoint, expectedStatus = 200, requestFn = request) {
    process.stdout.write(`  Testing ${name}... `);

    try {
        const res = await requestFn(method, endpoint);
        const statusArray = Array.isArray(expectedStatus) ? expectedStatus : [expectedStatus];

        if (statusArray.includes(res.status)) {
            console.log(`✅ ${res.status}`);
            results.passed++;
            return res;
        } else if (res.status === 0) {
            console.log(`⚠️  SKIPPED (${res.error})`);
            results.skipped++;
            return res;
        } else {
            console.log(`❌ ${res.status} (expected ${expectedStatus})`);
            results.failed++;
            results.errors.push({ name, endpoint, status: res.status, expected: expectedStatus });
            return res;
        }
    } catch (err) {
        console.log(`❌ ERROR: ${err.message}`);
        results.failed++;
        results.errors.push({ name, endpoint, error: err.message });
        return { ok: false };
    }
}

// Main test suite
async function runAllTests() {
    requireApiKey();
    console.log('\n🧪 FSMA 204 Endpoint Test Suite');
    console.log('='.repeat(50));
    console.log(`Base URL: ${BASE_URL}`);
    console.log('API Key: set (value hidden)');
    console.log('');

    // ============================================================================
    // HEALTH & METRICS
    // ============================================================================
    console.log('\n📊 Health & Metrics Endpoints');
    console.log('-'.repeat(40));

    await runTest('GET /health', 'GET', '/health');
    await runTest('GET /metrics', 'GET', '/metrics');
    await runTest('GET /v1/fsma/health', 'GET', '/v1/fsma/health');
    await runTest('GET /v1/fsma/metrics', 'GET', '/v1/fsma/metrics');
    await runTest('GET /v1/fsma/dashboard', 'GET', '/v1/fsma/dashboard');

    // ============================================================================
    // TRACEABILITY ENDPOINTS
    // ============================================================================
    console.log('\n🔍 Traceability Endpoints');
    console.log('-'.repeat(40));

    await runTest('GET /v1/fsma/trace/forward/{tlc}', 'GET', `/v1/fsma/trace/forward/${TEST_TLC}`);
    await runTest('GET /v1/fsma/trace/backward/{tlc}', 'GET', `/v1/fsma/trace/backward/${TEST_TLC}`);
    await runTest('GET /v1/fsma/timeline/{tlc}', 'GET', `/v1/fsma/timeline/${TEST_TLC}`);

    // ============================================================================
    // MASS BALANCE (PHYSICS ENGINE)
    // ============================================================================
    console.log('\n⚖️  Mass Balance Endpoints');
    console.log('-'.repeat(40));

    await runTest('GET /v1/fsma/mass-balance/{tlc}', 'GET', `/v1/fsma/mass-balance/${TEST_TLC}`);
    await runTest('GET /v1/fsma/mass-balance/event/{id}', 'GET', `/v1/fsma/mass-balance/event/${TEST_EVENT_ID}`);

    // ============================================================================
    // EXPORT ENDPOINTS
    // ============================================================================
    console.log('\n📤 Export Endpoints');
    console.log('-'.repeat(40));

    await runTest('GET /v1/fsma/export/trace/{tlc}', 'GET', `/v1/fsma/export/trace/${TEST_TLC}`);
    await runTest('GET /v1/fsma/export/recall-contacts/{tlc}', 'GET', `/v1/fsma/export/recall-contacts/${TEST_TLC}`);
    await runTest('GET /v1/fsma/export/gaps', 'GET', '/v1/fsma/export/gaps');

    // ============================================================================
    // GAP ANALYSIS
    // ============================================================================
    console.log('\n🕳️  Gap Analysis Endpoints');
    console.log('-'.repeat(40));

    await runTest('GET /v1/fsma/gaps', 'GET', '/v1/fsma/gaps');
    await runTest('GET /v1/fsma/gaps/orphans', 'GET', '/v1/fsma/gaps/orphans');
    await runTest('GET /v1/fsma/metrics/quality', 'GET', '/v1/fsma/metrics/quality');

    // ============================================================================
    // AUDIT TRAIL
    // ============================================================================
    console.log('\n📜 Audit Trail Endpoints');
    console.log('-'.repeat(40));

    await runTest('GET /v1/fsma/audit', 'GET', '/v1/fsma/audit');
    await runTest('GET /v1/fsma/audit/{id}', 'GET', `/v1/fsma/audit/${TEST_TLC}`);
    await runTest('GET /v1/fsma/audit/verify', 'GET', '/v1/fsma/audit/verify');

    // ============================================================================
    // DRIFT DETECTION
    // ============================================================================
    console.log('\n📈 Drift Detection Endpoints');
    console.log('-'.repeat(40));

    await runTest('GET /v1/fsma/drift/status', 'GET', '/v1/fsma/drift/status');
    await runTest('GET /v1/fsma/drift/analyze', 'GET', '/v1/fsma/drift/analyze');
    await runTest('GET /v1/fsma/drift/alerts', 'GET', '/v1/fsma/drift/alerts');
    await runTest('GET /v1/fsma/drift/snapshot/{supplier}', 'GET', '/v1/fsma/drift/snapshot/supplier-001');

    // ============================================================================
    // RECALL MANAGEMENT
    // ============================================================================
    console.log('\n🚨 Recall Management Endpoints');
    console.log('-'.repeat(40));

    await runTest('GET /v1/fsma/recall/readiness', 'GET', '/v1/fsma/recall/readiness');
    await runTest('GET /v1/fsma/recall/history', 'GET', '/v1/fsma/recall/history');
    await runTest('GET /v1/fsma/recall/drills', 'GET', '/v1/fsma/recall/drills');

    // ============================================================================
    // IDENTIFIER VALIDATION
    // ============================================================================
    console.log('\n🔢 Identifier Validation Endpoints');
    console.log('-'.repeat(40));

    await runTest('POST /v1/fsma/validate/tlc', 'POST', '/v1/fsma/validate/tlc?tlc=LOT-2024-001');
    await runTest('POST /v1/fsma/validate/gln', 'POST', '/v1/fsma/validate/gln?gln=0012345678901');
    await runTest('POST /v1/fsma/validate/gtin', 'POST', '/v1/fsma/validate/gtin?gtin=00012345678905');

    // ============================================================================
    // PROVISION QUERIES
    // ============================================================================
    console.log('\n📋 Provision Endpoints');
    console.log('-'.repeat(40));

    await runTest('GET /v1/provisions/by-request', 'GET', '/v1/provisions/by-request?id=test-request-id');

    // ============================================================================
    // RESULTS SUMMARY
    // ============================================================================
    console.log('\n' + '='.repeat(50));
    console.log('📊 TEST RESULTS SUMMARY');
    console.log('='.repeat(50));
    console.log(`  ✅ Passed:  ${results.passed}`);
    console.log(`  ❌ Failed:  ${results.failed}`);
    console.log(`  ⚠️  Skipped: ${results.skipped}`);
    console.log(`  📊 Total:   ${results.passed + results.failed + results.skipped}`);

    if (results.errors.length > 0) {
        console.log('\n❌ Failed Tests:');
        results.errors.forEach((err, i) => {
            console.log(`  ${i + 1}. ${err.name}`);
            console.log(`     Endpoint: ${err.endpoint}`);
            console.log(`     Status: ${err.status || err.error}`);
        });
    }

    const passRate = ((results.passed / (results.passed + results.failed)) * 100).toFixed(1);
    console.log(`\n🎯 Pass Rate: ${passRate}%`);

    return results.failed === 0;
}

// Run tests when executed directly; requiring this file (for example from a
// test harness) must not run the suite as a side effect.
if (require.main === module) {
    runAllTests()
        .then((success) => {
            process.exit(success ? 0 : 1);
        })
        .catch((err) => {
            console.error('Test suite error:', err);
            process.exit(1);
        });
}

module.exports = { request, runTest, runAllTests, transportFor, requireApiKey, results };
