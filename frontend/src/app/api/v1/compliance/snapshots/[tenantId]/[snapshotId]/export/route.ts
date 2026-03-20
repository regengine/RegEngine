import { NextRequest, NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

interface Props {
    params: Promise<{ tenantId: string; snapshotId: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: Props
) {
    // Guard against static export execution
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
        return NextResponse.json({ message: 'Dynamic data not available during static build' });
    }

    const { tenantId, snapshotId } = await params;

    // Fallback export endpoint returning JSON
    return NextResponse.json({
        snapshot_id: snapshotId,
        tenant_id: tenantId,
        export_date: new Date().toISOString(),
        content: "Detailed snapshot content..."
    });
}
