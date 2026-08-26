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
    refreezeDevComplianceSnapshot,
} from '@/lib/dev-compliance-snapshots';

export const dynamic = 'force-dynamic';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/refreeze] COMPLIANCE_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
        return getServerServiceURL('compliance');
    }
    return url;
}

interface Props {
    params: Promise<{ tenantId: string; snapshotId: string }>;
}

export async function POST(
    request: NextRequest,
    { params }: Props,
) {
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    const { tenantId: rawTenantId, snapshotId: rawSnapshotId } = await params;
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

    const rawBody = await request.text();
    let parsedBody: Record<string, unknown> = {};
    if (rawBody) {
        try {
            parsedBody = JSON.parse(rawBody) as Record<string, unknown>;
        } catch {
            parsedBody = {};
        }
    }
    const COMPLIANCE_URL = getComplianceUrl();
    const headers = new Headers({
        'Content-Type': request.headers.get('content-type') || 'application/json',
    });
    const credentialError = prepareTenantScopedProxyHeaders(headers, request, tenantId);
    if (credentialError) return credentialError;
    const allowFallback = allowDevComplianceSnapshotFallback();
    if (!COMPLIANCE_URL) {
        if (allowFallback) {
            const result = refreezeDevComplianceSnapshot({
                tenantId,
                snapshotId,
                createdBy: typeof parsedBody.created_by === 'string' ? parsedBody.created_by : undefined,
            });
            if (result) {
                return NextResponse.json(result);
            }
        }
        console.error('[proxy/refreeze] 503 — compliance backend not configured');
        return NextResponse.json(
            { error: 'backend_not_configured', message: 'Compliance backend is not configured' },
            { status: 503 },
        );
    }

    try {
        const response = await fetch(
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/${snapshotId}/refreeze`,
            {
                method: 'POST',
                headers,
                body: rawBody || undefined,
                redirect: 'manual',
            },
        );
        const redirectError = rejectUpstreamRedirect(response, 'compliance-snapshot-refreeze');
        if (redirectError) return redirectError;
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            if (allowFallback && (response.status === 404 || response.status === 503)) {
                const result = refreezeDevComplianceSnapshot({
                    tenantId,
                    snapshotId,
                    createdBy: typeof parsedBody.created_by === 'string' ? parsedBody.created_by : undefined,
                });
                if (result) {
                    return NextResponse.json(result);
                }
            }
            return NextResponse.json(
                { error: data.detail || 'Snapshot refreeze failed' },
                { status: response.status },
            );
        }

        return NextResponse.json(data);
    } catch (error: unknown) {
        console.error('[proxy/refreeze] Backend unreachable:', error);
        if (allowFallback) {
            const result = refreezeDevComplianceSnapshot({
                tenantId,
                snapshotId,
                createdBy: typeof parsedBody.created_by === 'string' ? parsedBody.created_by : undefined,
            });
            if (result) {
                return NextResponse.json(result);
            }
        }
        return NextResponse.json(
            { error: 'Snapshot refreeze service unavailable' },
            { status: 503 },
        );
    }
}
