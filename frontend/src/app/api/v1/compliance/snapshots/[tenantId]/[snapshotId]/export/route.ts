import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import {
    requireProxyAuth,
    validateProxySession,
    validateUuid,
    enforceTenantMatch,
} from '@/lib/api-proxy';
import { prepareTenantScopedProxyHeaders, rejectUpstreamRedirect } from '@/lib/proxy-factory';
import {
    allowDevComplianceSnapshotFallback,
    exportDevComplianceSnapshot,
} from '@/lib/dev-compliance-snapshots';

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

    const { tenantId: rawTenantId, snapshotId: rawSnapshotId } = await params;
    // Validate UUIDs before interpolating into the upstream URL (see
    // verify/route.ts — same hardening applied to every named-segment proxy).
    const tenantId = validateUuid(rawTenantId);
    const snapshotId = validateUuid(rawSnapshotId);
    if (!tenantId || !snapshotId) {
        return NextResponse.json(
            { error: 'Invalid tenant or snapshot identifier' },
            { status: 400 },
        );
    }

    // Cross-tenant authorization: bind this request to the caller's own tenant.
    const tenantError = await enforceTenantMatch(request, tenantId);
    if (tenantError) return tenantError;
    const url = new URL(request.url);
    const queryString = url.search;

    const COMPLIANCE_URL = getComplianceUrl();

    const headers = new Headers({
        'Content-Type': 'application/json',
    });
    const credentialError = prepareTenantScopedProxyHeaders(headers, request, tenantId);
    if (credentialError) return credentialError;
    const allowFallback = allowDevComplianceSnapshotFallback();
    if (!COMPLIANCE_URL) {
        if (allowFallback) {
            const exportPayload = exportDevComplianceSnapshot({ tenantId, snapshotId });
            if (exportPayload) {
                return NextResponse.json(exportPayload);
            }
        }
        console.error('[proxy/export] 503 — compliance backend not configured');
        return NextResponse.json(
            { error: 'backend_not_configured', message: 'Compliance backend is not configured' },
            { status: 503 },
        );
    }

    try {
        const response = await fetch(
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/${snapshotId}/export${queryString}`,
            {
                method: 'GET',
                headers,
                redirect: 'manual',
            }
        );
        const redirectError = rejectUpstreamRedirect(response, 'compliance-snapshot-export');
        if (redirectError) return redirectError;

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            if (allowFallback && (response.status === 404 || response.status === 503)) {
                const exportPayload = exportDevComplianceSnapshot({ tenantId, snapshotId });
                if (exportPayload) {
                    return NextResponse.json(exportPayload);
                }
            }
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

        return new NextResponse(response.body, {
            status: response.status,
            headers: outgoingHeaders,
        });

    } catch (error: unknown) {
        console.error('[proxy/export] Backend unreachable:', error);
        if (allowFallback) {
            const exportPayload = exportDevComplianceSnapshot({ tenantId, snapshotId });
            if (exportPayload) {
                return NextResponse.json(exportPayload);
            }
        }
        return NextResponse.json(
            { error: 'Export service unavailable' },
            { status: 503 }
        );
    }
}
