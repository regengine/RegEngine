import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';

const COMPLIANCE_URL = getServerServiceURL('compliance');

export const dynamic = 'force-dynamic';

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ tenantId: string }> }
) {
    // Guard against static export execution
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
        return NextResponse.json({ status: 'PENDING' });
    }

    const { tenantId } = await params;
    const searchParams = request.nextUrl.searchParams;
    const detailed = searchParams.get('detailed') === 'true';

    try {
        const res = await fetch(`${COMPLIANCE_URL}/v1/compliance/status/${tenantId}?detailed=${detailed}`, {
            headers: { 'X-RegEngine-API-Key': 'admin' }
        });
        const data = await res.json();
        return NextResponse.json(data);
    } catch {
        return NextResponse.json(
            { error: 'compliance_service_unavailable', message: 'Unable to reach compliance service' },
            { status: 503 }
        );
    }
}
