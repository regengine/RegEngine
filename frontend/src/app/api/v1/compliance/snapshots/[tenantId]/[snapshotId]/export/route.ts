import { NextRequest, NextResponse } from 'next/server';

interface Props {
    params: Promise<{ tenantId: string; snapshotId: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: Props
) {
    const { tenantId, snapshotId } = await params;

    // Fallback export endpoint returning JSON
    return NextResponse.json({
        snapshot_id: snapshotId,
        tenant_id: tenantId,
        export_date: new Date().toISOString(),
        content: "Detailed snapshot content..."
    });
}
