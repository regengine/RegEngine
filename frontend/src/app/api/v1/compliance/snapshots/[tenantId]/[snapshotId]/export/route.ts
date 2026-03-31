import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import { requireProxyAuth, validateProxySession, getServerApiKey } from '@/lib/api-proxy';

export const dynamic = 'force-dynamic';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/export] COMPLIANCE_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
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
            `${COMPLIANCE_URL}/api/v1/compliance/snapshots/${tenantId}/${snapshotId}/export${queryString}`,
            {
                method: 'GET',
                headers,
            }
        );

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            return NextResponse.json(
                { error: data.detail || 'Export failed' },
                { status: response.status }
            );
        }

        // Pass through the response body and content headers for file downloads
        const outgoingHeaders = new Headers();
        const passthroughHeaders = ['content-type', 'content-disposition', 'cache-control'];
        for (const header of passthroughHeaders) {
            const value = response.headers.get(header);
            if (value) {
                outgoingHeaders.set(header, value);
            }
        }

        console.info(`[proxy/export] GET ${tenantId}/${snapshotId}/export → ${response.status}`);
        return new NextResponse(response.body, {
            status: response.status,
            headers: outgoingHeaders,
        });

    } catch (error: unknown) {
        console.error('[proxy/export] Backend unreachable:', error);
        return NextResponse.json(
            { error: 'Export service unavailable' },
            { status: 503 }
        );
    }
}
