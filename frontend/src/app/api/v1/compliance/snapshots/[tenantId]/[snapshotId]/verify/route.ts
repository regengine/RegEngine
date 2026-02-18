import { NextRequest, NextResponse } from 'next/server';
import pg from 'pg';

const { Client } = pg;

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [{ tenantId: 'tenant_static', snapshotId: 'verify_static' }];
};

interface Props {
    params: Promise<{ tenantId: string; snapshotId: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: Props
) {
    // Guard against static export execution
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
        return NextResponse.json({ is_valid: true, message: 'Dynamic check not available during static build' });
    }

    const { tenantId, snapshotId } = await params;
    const searchParams = request.nextUrl.searchParams;
    const verifiedBy = searchParams.get('verified_by');

    // Return mock verification result
    return NextResponse.json({
        is_valid: true,
        stored_hash: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2',
        computed_hash: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2',
        hash_match: true,
        verified_by: verifiedBy || 'System',
        verified_at: new Date().toISOString()
    });
}
