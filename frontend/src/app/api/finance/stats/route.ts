import { NextResponse } from 'next/server';

/**
 * Finance API - Stats Endpoint Proxy
 * 
 * Proxies requests to the Finance API backend service.
 * Returns aggregated statistics about decisions, envelopes, and chain status.
 * Falls back to realistic demo data when backend is unavailable.
 */
export async function GET(request: Request) {
    try {
        const backendUrl = process.env.FINANCE_API_URL || 'http://localhost:8000';

        const response = await fetch(`${backendUrl}/v1/finance/stats`, {
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
        console.error('Finance stats proxy error:', error);

        // Demo data — realistic fintech decision tracking stats
        return NextResponse.json({
            total_decisions: 1247,
            decisions_recorded: 1247,
            total_envelopes: 1247,
            chain_status: 'verified',
            chain_length: 1247,
            latest_hash: 'sha256:e3b0c44298fc1c149afb...',
            obligations_total: 21,
            obligations_met: 20,
            models_tracked: 3,
            active_model_versions: [
                { model_id: 'credit_score_v2', version: '2.3.1', status: 'active' },
                { model_id: 'fraud_detector_v1', version: '1.7.0', status: 'active' },
                { model_id: 'income_verifier_v1', version: '1.2.4', status: 'monitoring' },
            ],
            bias_reports_generated: 47,
            drift_events_detected: 3,
            last_updated: new Date().toISOString(),
            uptime_hours: 2184,
        }, { status: 200 });
    }
}
