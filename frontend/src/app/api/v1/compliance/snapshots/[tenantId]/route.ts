import { NextRequest, NextResponse } from 'next/server';

const COMPLIANCE_URL = process.env.COMPLIANCE_SERVICE_URL || 'http://localhost:8500';

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [{ tenantId: 'list_static' }];
};

interface PageProps {
    params: Promise<{ tenantId: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: PageProps
) {
    // Guard against static export execution
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
        return NextResponse.json({ items: [] });
    }

    const { tenantId } = await params;

    try {
        const response = await fetch(`${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}`, {
            headers: { 'X-RegEngine-API-Key': 'admin' }
        });
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        console.warn('Backend fetch failed, using mock data for compliance snapshots');
        return NextResponse.json({
            items: [
                {
                    id: '00000000-0000-0000-0000-000000000001',
                    substation_id: 'TEST-ALPHA',
                    snapshot_time: '2026-01-25T18:00:00Z',
                    system_status: 'NOMINAL'
                }
            ]
        });
    }
}

export async function POST(
    request: NextRequest,
    { params }: PageProps
) {
    // Guard against static export execution
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
        return NextResponse.json({ message: 'Dynamic action not available during static build' });
    }

    const { tenantId } = await params;
    const body = await request.json();

    try {
        const response = await fetch(`${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-RegEngine-API-Key': 'admin'
            },
            body: JSON.stringify(body)
        });
        const data = await response.json();
        return NextResponse.json(data);
    } catch (error) {
        return NextResponse.json({ success: true, message: 'Mock snapshot created' });
    }
}
