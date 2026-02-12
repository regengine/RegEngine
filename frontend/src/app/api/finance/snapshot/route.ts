import { NextResponse } from 'next/server';

/**
 * Finance API - Compliance Snapshot Endpoint Proxy
 * 
 * Proxies requests to the Finance API backend service.
 * Returns real-time compliance snapshot with bias, drift, and regulatory scores.
 */
export async function GET(request: Request) {
    try {
        // Get backend URL from environment or default to localhost
        const backendUrl = process.env.FINANCE_API_URL || 'http://localhost:8000';

        const response = await fetch(`${backendUrl}/v1/finance/snapshot`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
            // Add timeout
            signal: AbortSignal.timeout(5000),
        });

        if (!response.ok) {
            throw new Error(`Backend returned ${response.status}`);
        }

        const data = await response.json();

        return NextResponse.json(data);
    } catch (error) {
        console.error('Finance snapshot proxy error:', error);

        // Return fallback data if backend is unavailable
        return NextResponse.json({
            snapshot_id: 'fallback',
            timestamp: new Date().toISOString(),
            vertical: 'finance',
            bias_score: 0,
            drift_score: 0,
            documentation_score: 0,
            regulatory_mapping_score: 0,
            obligation_coverage_percent: 0,
            total_compliance_score: 0,
            risk_level: 'unknown',
            num_open_violations: 0,
        }, { status: 200 });
    }
}
