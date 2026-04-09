import { NextRequest, NextResponse } from 'next/server';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
    if (url) return url;
    if (process.env.VERCEL) {
        console.error('[api/attest] COMPLIANCE_SERVICE_URL not configured — localhost is unreachable from Vercel');
        return '';
    }
    return 'http://localhost:8500';
}

const COMPLIANCE_URL = getComplianceUrl();

export const dynamic = 'force-dynamic';

interface Props {
    params: Promise<{ tenantId: string; snapshotId: string }>;
}

export async function POST(
    request: NextRequest,
    { params }: Props
) {
    if (!COMPLIANCE_URL) {
        return NextResponse.json(
            { error: 'COMPLIANCE_SERVICE_URL not configured' },
            { status: 503 },
        );
    }

    const { tenantId, snapshotId } = await params;
    const body = await request.json();

    try {
        const response = await fetch(
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/${snapshotId}/attest`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-RegEngine-API-Key': process.env.ADMIN_MASTER_KEY || 'admin',
                },
                body: JSON.stringify(body),
            }
        );

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            console.error('Attestation failed:', response.status, error);
            return NextResponse.json(
                { error: error.detail || 'Attestation failed' },
                { status: response.status }
            );
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Attestation request failed';
        console.error('Attestation proxy error:', message);
        return NextResponse.json(
            { error: message },
            { status: 502 }
        );
    }
}
