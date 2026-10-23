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
    createDevComplianceSnapshot,
    listDevComplianceSnapshots,
} from '@/lib/dev-compliance-snapshots';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/snapshots] COMPLIANCE_SERVICE_URL points to internal Railway URL; unreachable from Vercel.');
        return getServerServiceURL('compliance');
    }
    return url;
}

export const dynamic = 'force-dynamic';

interface PageProps {
    params: Promise<{ tenantId: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: PageProps
) {
    // Defense-in-depth: reject requests with no auth credentials before proxying
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    // Validate Supabase session tokens (expired/revoked sessions get 401)
    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    const { tenantId: rawTenantId } = await params;
    // Validate UUID before interpolating into the upstream URL to prevent
    // a crafted segment from escaping the intended path.
    const tenantId = validateUuid(rawTenantId);
    if (!tenantId) {
        return NextResponse.json(
            { error: 'Invalid tenant identifier', items: [] },
            { status: 400 },
        );
    }

    // Cross-tenant authorization: bind this request to the caller's own tenant.
    const tenantError = await enforceTenantMatch(request, tenantId);
    if (tenantError) return tenantError;

    const COMPLIANCE_URL = getComplianceUrl();
    const headers = new Headers({
        'Content-Type': 'application/json',
    });
    const credentialError = prepareTenantScopedProxyHeaders(headers, request, tenantId);
    if (credentialError) return credentialError;
    const allowFallback = allowDevComplianceSnapshotFallback();
    if (!COMPLIANCE_URL) {
        if (allowFallback) {
            return NextResponse.json({ items: listDevComplianceSnapshots(tenantId) });
        }
        console.error('[proxy/snapshots] 503: compliance backend not configured');
        return NextResponse.json(
            { error: 'backend_not_configured', message: 'Compliance backend is not configured', items: [] },
            { status: 503 },
        );
    }

    try {
        const response = await fetch(`${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}`, {
            headers,
            redirect: 'manual',
        });
        const redirectError = rejectUpstreamRedirect(response, 'compliance-snapshots');
        if (redirectError) return redirectError;
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            if (allowFallback && (response.status === 404 || response.status === 503)) {
                return NextResponse.json({ items: listDevComplianceSnapshots(tenantId) });
            }
            return NextResponse.json(
                { error: data.detail || 'Compliance snapshot request failed', items: [] },
                { status: response.status }
            );
        }

        return NextResponse.json(data);
    } catch (error) {
        console.error('[proxy/snapshots] Backend unreachable:', error);
        if (allowFallback) {
            return NextResponse.json({ items: listDevComplianceSnapshots(tenantId) });
        }
        return NextResponse.json(
            { error: 'Compliance snapshot service unavailable', items: [] },
            { status: 503 }
        );
    }
}

export async function POST(
    request: NextRequest,
    { params }: PageProps
) {
    // Defense-in-depth: reject requests with no auth credentials before proxying
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    // Validate Supabase session tokens (expired/revoked sessions get 401)
    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    const { tenantId: rawTenantId } = await params;
    // Validate UUID before interpolating into the upstream URL to prevent
    // a crafted segment from escaping the intended path.
    const tenantId = validateUuid(rawTenantId);
    if (!tenantId) {
        return NextResponse.json(
            { error: 'Invalid tenant identifier', items: [] },
            { status: 400 },
        );
    }

    // Cross-tenant authorization: bind this request to the caller's own tenant.
    const tenantError = await enforceTenantMatch(request, tenantId);
    if (tenantError) return tenantError;
    const body = await request.json().catch(() => ({}));
    const parsedBody = typeof body === 'object' && body !== null ? body as Record<string, unknown> : {};

    const COMPLIANCE_URL = getComplianceUrl();
    const headers = new Headers({
        'Content-Type': 'application/json',
    });
    const credentialError = prepareTenantScopedProxyHeaders(headers, request, tenantId);
    if (credentialError) return credentialError;
    const allowFallback = allowDevComplianceSnapshotFallback();
    if (!COMPLIANCE_URL) {
        if (allowFallback) {
            const snapshot = createDevComplianceSnapshot({
                tenantId,
                snapshotName: String(parsedBody.snapshot_name || 'Manual Snapshot'),
                snapshotReason: typeof parsedBody.snapshot_reason === 'string' ? parsedBody.snapshot_reason : undefined,
                createdBy: String(parsedBody.created_by || 'playwright@regengine.local'),
            });
            return NextResponse.json(snapshot);
        }
        console.error('[proxy/snapshots] 503: compliance backend not configured');
        return NextResponse.json(
            { error: 'backend_not_configured', message: 'Compliance backend is not configured' },
            { status: 503 },
        );
    }

    try {
        const response = await fetch(`${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}`, {
            method: 'POST',
            headers,
            body: JSON.stringify(body),
            redirect: 'manual',
        });
        const redirectError = rejectUpstreamRedirect(response, 'compliance-snapshots');
        if (redirectError) return redirectError;
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            if (allowFallback && (response.status === 404 || response.status === 503)) {
                const snapshot = createDevComplianceSnapshot({
                    tenantId,
                    snapshotName: String(parsedBody.snapshot_name || 'Manual Snapshot'),
                    snapshotReason: typeof parsedBody.snapshot_reason === 'string' ? parsedBody.snapshot_reason : undefined,
                    createdBy: String(parsedBody.created_by || 'playwright@regengine.local'),
                });
                return NextResponse.json(snapshot);
            }
            return NextResponse.json(
                { error: data.detail || 'Snapshot creation failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);
    } catch (error) {
        console.error('[proxy/snapshots] Backend unreachable:', error);
        if (allowFallback) {
            const snapshot = createDevComplianceSnapshot({
                tenantId,
                snapshotName: String(parsedBody.snapshot_name || 'Manual Snapshot'),
                snapshotReason: typeof parsedBody.snapshot_reason === 'string' ? parsedBody.snapshot_reason : undefined,
                createdBy: String(parsedBody.created_by || 'playwright@regengine.local'),
            });
            return NextResponse.json(snapshot);
        }
        return NextResponse.json(
            { error: 'Compliance snapshot service unavailable' },
            { status: 503 }
        );
    }
}
