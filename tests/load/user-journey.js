/**
 * k6 Load Test: Complete User Journey
 * 
 * Tests the full critical path:
 * 1. Login
 * 2. Dashboard access
 * 3. Create snapshot
 * 4. View snapshots
 * 5. Logout
 * 
 * Run with: k6 run tests/load/user-journey.js
 */

import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');

// Test configuration
export const options = {
    stages: [
        { duration: '30s', target: 10 },   // Warm up
        { duration: '1m', target: 50 },    // Ramp to 50 users
        { duration: '3m', target: 50 },    // Stay at 50
        { duration: '1m', target: 100 },   // Peak load
        { duration: '1m', target: 100 },   // Sustain peak
        { duration: '30s', target: 0 },    // Ramp down
    ],

    thresholds: {
        http_req_duration: ['p(95)<2000'],  // 95% under 2s
        http_req_failed: ['rate<0.01'],     // <1% failure
        errors: ['rate<0.05'],              // <5% errors
    },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';

export default function () {
    // Test data
    const credentials = {
        email: `loadtest${__VU}@example.com`,
        password: 'testpassword123',
    };

    let token;

    // 1. Login
    group('Authentication', () => {
        const loginRes = http.post(`${BASE_URL}/auth/login`, JSON.stringify(credentials), {
            headers: { 'Content-Type': 'application/json' },
        });

        const loginSuccess = check(loginRes, {
            'login status 200': (r) => r.status === 200,
            'has access token': (r) => r.json('access_token') !== undefined,
            'has user data': (r) => r.json('user') !== undefined,
        });

        if (!loginSuccess) {
            errorRate.add(1);
            return;
        }

        token = loginRes.json('access_token');
        errorRate.add(0);
    });

    sleep(1);

    // 2. Dashboard access
    group('Dashboard', () => {
        const headers = {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
        };

        const statusRes = http.get(`${BASE_URL}/v1/system/status`, { headers });

        const statusSuccess = check(statusRes, {
            'status 200': (r) => r.status === 200,
            'has services': (r) => r.json('services') !== undefined,
        });

        errorRate.add(statusSuccess ? 0 : 1);

        const metricsRes = http.get(`${BASE_URL}/v1/system/metrics`, { headers });

        const metricsSuccess = check(metricsRes, {
            'metrics 200': (r) => r.status === 200,
            'has tenant count': (r) => r.json('total_tenants') !== undefined,
        });

        errorRate.add(metricsSuccess ? 0 : 1);
    });

    sleep(2);

    // 3. Create snapshot (Energy service)
    group('Snapshot Creation', () => {
        const snapshot = {
            substation_id: `SUB-${__VU}-${Date.now()}`,
            voltage_kv: 138,
            firmware_versions: {
                pmu: '2.1.0',
                rtu: '3.0.1',
            },
            compliance_data: {
                cip_013: {
                    patch_management: true,
                    access_controls: true,
                },
            },
        };

        const createRes = http.post(
            'http://localhost:8001/energy/snapshots',
            JSON.stringify(snapshot),
            {
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json',
                },
            }
        );

        const createSuccess = check(createRes, {
            'snapshot created': (r) => r.status === 201,
            'has snapshot_id': (r) => r.json('snapshot_id') !== undefined,
        });

        errorRate.add(createSuccess ? 0 : 1);
    });

    sleep(1);

    // 4. List snapshots
    group('Snapshot List', () => {
        const listRes = http.get(
            'http://localhost:8001/energy/snapshots?limit=10',
            {
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
            }
        );

        const listSuccess = check(listRes, {
            'list 200': (r) => r.status === 200,
            'has snapshots': (r) => r.json('snapshots') !== undefined,
        });

        errorRate.add(listSuccess ? 0 : 1);
    });

    sleep(1);

    // 5. Opportunity service
    group('Opportunities', () => {
        const oppRes = http.get(
            'http://localhost:8002/opportunities/arbitrage?limit=5',
            {
                headers: {
                    'Authorization': `Bearer ${token}`,
                },
            }
        );

        const oppSuccess = check(oppRes, {
            'opportunities 200': (r) => r.status === 200,
            'has items': (r) => r.json('items') !== undefined,
        });

        errorRate.add(oppSuccess ? 0 : 1);
    });

    sleep(2);
}

// Setup function (runs once per VU)
export function setup() {
    console.log('Starting load test...');
    console.log(`Target: ${BASE_URL}`);
    return {};
}

// Teardown function
export function teardown(data) {
    console.log('Load test complete');
}
