import { NextRequest, NextResponse } from 'next/server';

// Compliance status API endpoint - returns tenant compliance status
// In production: this would proxy to the compliance service backend
// For demo: returns mock COMPLIANT status

// Required for static export
export function generateStaticParams() {
    return [];
}

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ tenantId: string }> }
) {
    const { tenantId } = await params;

    // Try to fetch from compliance service first
    try {
        const complianceUrl = process.env.COMPLIANCE_SERVICE_URL || 'http://localhost:8500';
        const response = await fetch(`${complianceUrl}/v1/compliance/status/${tenantId}`, {
            headers: {
                'X-RegEngine-API-Key': 'admin',
            },
        });

        if (response.ok) {
            const data = await response.json();
            return NextResponse.json(data);
        }
    } catch (e) {
        console.log('Compliance service not available, using demo mode');
    }

    // Demo response - COMPLIANT status with no active alerts
    const demoStatus = {
        tenant_id: tenantId,
        status: "COMPLIANT" as const,
        status_emoji: "✅",
        status_label: "Compliant",
        active_alert_count: 0,
        critical_alert_count: 0,
        countdown_seconds: null,
        countdown_display: null,
        next_deadline_description: null,
        active_alerts: [],
        last_checked: new Date().toISOString(),
        message: "All compliance requirements met. Your FSMA 204 traceability is up to date."
    };

    return NextResponse.json(demoStatus);
}
