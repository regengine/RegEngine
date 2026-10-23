import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import {
    requireProxyAuth,
    validateProxySession,
    validateUuid,
    enforceTenantMatch,
} from '@/lib/api-proxy';
import { prepareTenantScopedProxyHeaders, rejectUpstreamRedirect } from '@/lib/proxy-factory';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/compliance-status] COMPLIANCE_SERVICE_URL points to internal Railway URL; unreachable from Vercel.');
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

    // Cross-tenant authorization: bind this request to the caller's own tenant.
    const tenantError = await enforceTenantMatch(request, tenantId);
    if (tenantError) return tenantError;
    const searchParams = request.nextUrl.searchParams;
    const detailed = searchParams.get('detailed') === 'true';

    const COMPLIANCE_URL = getComplianceUrl();
    if (!COMPLIANCE_URL) {
        console.error('[proxy/compliance-status] 503: compliance backend not configured');
        return NextResponse.json(
            { error: 'backend_not_configured', message: 'Compliance backend is not configured' },
            { status: 503 },
        );
    }
    const headers = new Headers({
        'Content-Type': 'application/json',
    });
    const credentialError = prepareTenantScopedProxyHeaders(headers, request, tenantId);
    if (credentialError) return credentialError;

    try {
        const res = await fetch(`${COMPLIANCE_URL}/v1/compliance/status/${tenantId}?detailed=${detailed}`, {
            headers,
            redirect: 'manual',
        });
        const redirectError = rejectUpstreamRedirect(res, 'compliance-status');
        if (redirectError) return redirectError;
        const data = await res.json();
        return NextResponse.json(data, { status: res.status });
    } catch {
        return NextResponse.json(
            { error: 'compliance_service_unavailable', message: 'Unable to reach compliance service' },
            { status: 503 }
        );
    }
}
