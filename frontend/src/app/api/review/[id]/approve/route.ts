import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import { requireProxyAuth, validateProxySession, getAdminMasterKey } from '@/lib/api-proxy';

const ADMIN_URL = process.env.ADMIN_SERVICE_URL || getServerServiceURL('admin');

export const dynamic = 'force-dynamic';

export async function POST(
    request: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    // Defense-in-depth: reject requests with no auth credentials before proxying
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    // Validate Supabase session tokens (expired/revoked sessions get 401)
    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    const adminKey = getAdminMasterKey();
    if (!adminKey) {
        console.error('[review/approve] ADMIN_MASTER_KEY is not configured');
        return NextResponse.json(
            { error: 'Admin service is not configured — contact your administrator' },
            { status: 503 }
        );
    }

    const { id } = await params;

    try {
        const response = await fetch(
            `${ADMIN_URL}/v1/admin/review/flagged-extractions/${id}/approve`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Admin-Key': adminKey,
                },
                body: JSON.stringify({
                    reviewer_id: 'web-frontend',
                    notes: 'Approved via web interface',
                }),
            }
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Approval failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Approval failed';
        console.error('Approve error:', error);
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
