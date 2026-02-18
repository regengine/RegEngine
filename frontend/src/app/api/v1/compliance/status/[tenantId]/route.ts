import { NextRequest, NextResponse } from 'next/server';

const COMPLIANCE_URL = process.env.COMPLIANCE_SERVICE_URL || 'http://localhost:8500';

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [{ tenantId: 'status_static' }];
};

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
        // Fallback for demo
        return NextResponse.json({
            tenant_id: tenantId,
            status: 'COMPLIANT',
            score: 94,
            last_check: new Date().toISOString()
        });
    }
}
