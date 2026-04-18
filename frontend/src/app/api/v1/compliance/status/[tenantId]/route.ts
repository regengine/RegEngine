import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import {
    requireProxyAuth,
    validateProxySession,
    getServerApiKey,
    validateUuid,
} from '@/lib/api-proxy';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/compliance-status] COMPLIANCE_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
        return getServerServiceURL('compliance');
    }
    return url;
}

export const dynamic = 'force-dynamic';

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ tenantId: string }> }
) {
    // Defense-in-depth: reject requests with no auth credentials before proxying
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    // Validate Supabase session tokens (expired/revoked sessions get 401)
    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    const { tenantId: rawTenantId } = await params;
    // Validate UUID before interpolating into the upstream URL.
    const tenantId = validateUuid(rawTenantId);
    if (!tenantId) {
        return NextResponse.json(
            { error: 'invalid_tenant_identifier' },
            { status: 400 },
        );
    }
    const searchParams = request.nextUrl.searchParams;
    const detailed = searchParams.get('detailed') === 'true';

    const COMPLIANCE_URL = getComplianceUrl();
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
    };
    const apiKey = getServerApiKey();
    if (apiKey) {
        headers['X-RegEngine-API-Key'] = apiKey;
    }

    try {
        const res = await fetch(`${COMPLIANCE_URL}/v1/compliance/status/${tenantId}?detailed=${detailed}`, {
            headers,
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
