import { NextResponse } from 'next/server';

/**
 * Finance API - Compliance Snapshot Endpoint Proxy
 * 
 * Proxies requests to the Finance API backend service.
 * Returns real-time compliance snapshot with bias, drift, and regulatory scores.
 * Falls back to realistic demo data when backend is unavailable.
 */
export async function GET(request: Request) {
    try {
        const backendUrl = process.env.FINANCE_API_URL || 'http://localhost:8000';

        const response = await fetch(`${backendUrl}/v1/finance/snapshot`, {
            method: 'GET',
            headers: { 'Content-Type': 'application/json' },
            signal: AbortSignal.timeout(5000),
        });

        if (!response.ok) {
            throw new Error(`Backend returned ${response.status}`);
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        console.error('Finance snapshot proxy error:', error);

        // Demo data — realistic fintech compliance snapshot
        return NextResponse.json({
            snapshot_id: 'demo-snapshot-001',
            timestamp: new Date().toISOString(),
            vertical: 'finance',
            bias_score: 92,
            drift_score: 88,
            documentation_score: 95,
            regulatory_mapping_score: 91,
            obligation_coverage_percent: 95.2,
            total_compliance_score: 91.5,
            risk_level: 'low',
            num_open_violations: 2,
            models_evaluated: 3,
            last_bias_check: new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString(),
            last_drift_check: new Date(Date.now() - 4 * 60 * 60 * 1000).toISOString(),
            breakdown: {
                ecoa_compliance: 94,
                tila_compliance: 91,
                fcra_compliance: 89,
                udaap_compliance: 93,
                sr_11_7_compliance: 88,
            },
        }, { status: 200 });
    }
}
