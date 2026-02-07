#!/usr/bin/env node
/**
 * End-to-End Integration Tests for RegEngine
 * 
 * This script tests the complete flow of the RegEngine application
 * against a running Docker Compose environment.
 * 
 * Prerequisites:
 *   - Docker Compose services running (docker-compose up -d)
 *   - Admin API at http://localhost:8400
 *   - Ingestion Service at http://localhost:8000
 *   - Compliance API at http://localhost:8500
 *   - Opportunity API at http://localhost:8300
 *   - Frontend at http://localhost:3000
 * 
 * Usage:
 *   node scripts/e2e_tests.js
 */

const fs = require('fs');
const path = require('path');

// Load admin key from .env
function getAdminKey() {
    const envPath = path.resolve(__dirname, '..', '.env');
    if (!fs.existsSync(envPath)) {
        console.error('ERROR: .env file not found');
        process.exit(1);
    }
    const envContent = fs.readFileSync(envPath, 'utf8');
    const match = envContent.match(/ADMIN_MASTER_KEY=(.*)$/m);
    if (!match || !match[1]) {
        console.error('ERROR: ADMIN_MASTER_KEY not found in .env');
        process.exit(1);
    }
    let key = match[1].trim();
    if ((key.startsWith('"') && key.endsWith('"')) || (key.startsWith("'") && key.endsWith("'"))) {
        key = key.slice(1, -1);
    }
    return key;
}

const ADMIN_URL = 'http://localhost:8400';
const INGESTION_URL = 'http://localhost:8000';
const COMPLIANCE_URL = 'http://localhost:8500';
const OPPORTUNITY_URL = 'http://localhost:8300';
const FRONTEND_URL = 'http://localhost:3000';

let passed = 0;
let failed = 0;
const results = [];

async function test(name, fn) {
    try {
        await fn();
        console.log(`✓ ${name}`);
        passed++;
        results.push({ name, status: 'passed' });
    } catch (err) {
        console.log(`✗ ${name}`);
        console.log(`  Error: ${err.message}`);
        failed++;
        results.push({ name, status: 'failed', error: err.message });
    }
}

function assert(condition, message) {
    if (!condition) {
        throw new Error(message || 'Assertion failed');
    }
}

async function runTests() {
    console.log('Running E2E Integration Tests...\n');
    console.log('='.repeat(50));

    const adminKey = getAdminKey();

    // ========================================
    // Health Check Tests
    // ========================================
    console.log('\n📋 Health Checks\n');

    await test('Admin API health', async () => {
        const res = await fetch(`${ADMIN_URL}/health`);
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert(data.status === 'ok', 'Expected status=ok');
    });

    await test('Ingestion Service health', async () => {
        const res = await fetch(`${INGESTION_URL}/health`);
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert(data.status === 'ok', 'Expected status=ok');
    });

    await test('Compliance API health', async () => {
        const res = await fetch(`${COMPLIANCE_URL}/health`);
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert(data.status === 'healthy', 'Expected status=healthy');
    });

    await test('Opportunity API health', async () => {
        const res = await fetch(`${OPPORTUNITY_URL}/health`);
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert(data.status === 'ok', 'Expected status=ok');
    });

    // ========================================
    // Admin API Tests
    // ========================================
    console.log('\n📋 Admin API\n');

    let tenantId;
    await test('Create tenant', async () => {
        const res = await fetch(`${ADMIN_URL}/v1/admin/tenants`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-Key': adminKey,
            },
            body: JSON.stringify({ name: 'E2E Test Tenant' }),
        });
        const text = await res.text();
        assert(res.ok, `Expected 200, got ${res.status}: ${text}`);
        const data = JSON.parse(text);
        assert(data.tenant_id, 'Expected tenant_id in response');
        tenantId = data.tenant_id;
    });

    let apiKey;
    await test('Create API key', async () => {
        const res = await fetch(`${ADMIN_URL}/v1/admin/keys`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-Key': adminKey,
            },
            body: JSON.stringify({
                name: 'E2E Test Key',
                tenant_id: tenantId,
            }),
        });
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert(data.api_key, 'Expected api_key in response');
        apiKey = data.api_key;
    });

    await test('List API keys', async () => {
        const res = await fetch(`${ADMIN_URL}/v1/admin/keys`, {
            headers: { 'X-Admin-Key': adminKey },
        });
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert(Array.isArray(data), 'Expected array of keys');
    });

    await test('Get review queue', async () => {
        const res = await fetch(`${ADMIN_URL}/v1/admin/review/hallucinations`, {
            headers: { 'X-Admin-Key': adminKey },
        });
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert('items' in data, 'Expected items in response');
    });

    // ========================================
    // Ingestion Service Tests
    // ========================================
    console.log('\n📋 Ingestion Service\n');

    await test('Ingest URL requires auth', async () => {
        const res = await fetch(`${INGESTION_URL}/ingest/url`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                url: 'https://example.com/doc.pdf',
                source_system: 'test',
            }),
        });
        assert(res.status === 401 || res.status === 403, `Expected 401/403, got ${res.status}`);
    });

    await test('Ingest URL validates source_system (after auth)', async () => {
        const res = await fetch(`${INGESTION_URL}/ingest/url`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-RegEngine-API-Key': apiKey,
            },
            body: JSON.stringify({ url: 'https://example.com/doc.pdf' }),
        });
        // Auth check happens first, then validation
        assert(res.status === 422 || res.status === 401, `Expected 422 or 401, got ${res.status}`);
    });

    // ========================================
    // Opportunity API Tests
    // ========================================
    console.log('\n📋 Opportunity API\n');

    await test('Arbitrage endpoint returns items', async () => {
        const res = await fetch(`${OPPORTUNITY_URL}/opportunities/arbitrage?j1=EU&j2=US-NY`);
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert('items' in data, 'Expected items in response');
    });

    await test('Gaps endpoint returns items', async () => {
        const res = await fetch(`${OPPORTUNITY_URL}/opportunities/gaps?j1=EU&j2=US-CA`);
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert('items' in data, 'Expected items in response');
    });

    await test('Gaps endpoint requires jurisdictions', async () => {
        const res = await fetch(`${OPPORTUNITY_URL}/opportunities/gaps`);
        assert(res.status === 422, `Expected 422, got ${res.status}`);
    });

    // ========================================
    // Compliance API Tests
    // ========================================
    console.log('\n📋 Compliance API\n');

    await test('List checklists requires auth', async () => {
        const res = await fetch(`${COMPLIANCE_URL}/checklists`);
        assert(res.status === 401 || res.status === 403, `Expected 401/403, got ${res.status}`);
    });

    await test('Checklists loaded count > 0', async () => {
        const res = await fetch(`${COMPLIANCE_URL}/health`);
        const data = await res.json();
        assert(data.checklists_loaded > 0, `Expected checklists_loaded > 0, got ${data.checklists_loaded}`);
    });

    // ========================================
    // Frontend API Tests
    // ========================================
    console.log('\n📋 Frontend API\n');

    await test('Frontend setup-demo returns credentials', async () => {
        const res = await fetch(`${FRONTEND_URL}/api/setup-demo`, { method: 'POST' });
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert(data.apiKey, 'Expected apiKey in response');
        assert(data.tenantId, 'Expected tenantId in response');
    });

    await test('Frontend review items returns array', async () => {
        const res = await fetch(`${FRONTEND_URL}/api/review/items`);
        assert(res.ok, `Expected 200, got ${res.status}`);
        const data = await res.json();
        assert(Array.isArray(data), 'Expected array response');
    });

    // ========================================
    // Summary
    // ========================================
    console.log('\n' + '='.repeat(50));
    console.log(`\n📊 Results: ${passed} passed, ${failed} failed\n`);

    if (failed > 0) {
        console.log('Failed tests:');
        results.filter(r => r.status === 'failed').forEach(r => {
            console.log(`  - ${r.name}: ${r.error}`);
        });
        process.exit(1);
    }
}

runTests().catch(err => {
    console.error('Test runner failed:', err);
    process.exit(1);
});
