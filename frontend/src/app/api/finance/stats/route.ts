import { NextResponse } from 'next/server';

/**
 * Finance API - Stats Endpoint Proxy
 * 
 * Proxies requests to the Finance API backend service.
 * Returns aggregated statistics about decisions, envelopes, and chain status.
 */
export async function GET(request: Request) {
    try {
        // Get backend URL from environment or default to localhost
        const backendUrl = process.env.FINANCE_API_URL || 'http://localhost:8000';

        const response = await fetch(`${backendUrl}/v1/finance/stats`, {
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
        console.error('Finance stats proxy error:', error);

        // Return fallback data if backend is unavailable
        return NextResponse.json({
            total_decisions: 0,
            total_envelopes: 0,
            chain_status: 'empty',
            last_updated: new Date().toISOString(),
        }, { status: 200 });
    }
}
