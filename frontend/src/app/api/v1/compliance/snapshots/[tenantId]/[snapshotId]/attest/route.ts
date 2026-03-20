import { NextRequest, NextResponse } from 'next/server';

const COMPLIANCE_URL = process.env.COMPLIANCE_SERVICE_URL || 'http://localhost:8500';

export const dynamic = 'force-dynamic';

interface Props {
    params: Promise<{ tenantId: string; snapshotId: string }>;
}

export async function POST(
    request: NextRequest,
    { params }: Props
) {
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
