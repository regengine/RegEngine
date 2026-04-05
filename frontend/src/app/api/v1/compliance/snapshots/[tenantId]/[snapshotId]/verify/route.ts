import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import { requireProxyAuth, validateProxySession, getServerApiKey } from '@/lib/api-proxy';

export const dynamic = 'force-dynamic';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/verify] COMPLIANCE_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
        return getServerServiceURL('compliance');
    }
    return url;
}

interface Props {
    params: Promise<{ tenantId: string; snapshotId: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: Props
) {
    // Defense-in-depth: reject requests with no auth credentials before proxying
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    // Validate Supabase session tokens (expired/revoked sessions get 401)
    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    const { tenantId, snapshotId } = await params;
    const url = new URL(request.url);
    const queryString = url.search;

    const COMPLIANCE_URL = getComplianceUrl();

    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
    };
    const apiKey = getServerApiKey();
    if (apiKey) {
        headers['X-RegEngine-API-Key'] = apiKey;
    }

    try {
        const response = await fetch(
            `${COMPLIANCE_URL}/api/v1/compliance/snapshots/${tenantId}/${snapshotId}/verify${queryString}`,
            {
                method: 'GET',
                headers,
            }
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { is_valid: false, error: data.detail || 'Verification failed' },
                { status: response.status }
            );
        }

        if (process.env.NODE_ENV !== 'production') { console.info(`[proxy/verify] GET ${tenantId}/${snapshotId}/verify → ${response.status}`); }
        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('[proxy/verify] Backend unreachable:', error);
        return NextResponse.json(
            { is_valid: false, error: 'Verification service unavailable' },
            { status: 503 }
        );
    }
}
