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
    compareDevComplianceSnapshots,
} from '@/lib/dev-compliance-snapshots';

export const dynamic = 'force-dynamic';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/snapshot-diff] COMPLIANCE_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
        return getServerServiceURL('compliance');
    }
    return url;
}

interface Props {
    params: Promise<{ tenantId: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: Props,
) {
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    const { tenantId: rawTenantId } = await params;
    const tenantId = validateUuid(rawTenantId);
    const url = new URL(request.url);
    const snapshotA = validateUuid(url.searchParams.get('snapshot_a'));
    const snapshotB = validateUuid(url.searchParams.get('snapshot_b'));

    if (!tenantId || !snapshotA || !snapshotB) {
        return NextResponse.json(
            { error: 'Invalid tenant or snapshot identifier' },
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
            const result = compareDevComplianceSnapshots({ tenantId, snapshotA, snapshotB });
            if (result) {
                return NextResponse.json(result);
            }
        }
        console.error('[proxy/snapshot-diff] 503 — compliance backend not configured');
        return NextResponse.json(
            { error: 'backend_not_configured', message: 'Compliance backend is not configured' },
            { status: 503 },
        );
    }

    try {
        const response = await fetch(
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/diff?snapshot_a=${snapshotA}&snapshot_b=${snapshotB}`,
            { headers, redirect: 'manual' },
        );
        const redirectError = rejectUpstreamRedirect(response, 'compliance-snapshot-diff');
        if (redirectError) return redirectError;
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            if (allowFallback && (response.status === 404 || response.status === 503)) {
                const result = compareDevComplianceSnapshots({
                    tenantId,
                    snapshotA,
                    snapshotB,
                });
                if (result) {
                    return NextResponse.json(result);
                }
            }
            return NextResponse.json(
                { error: data.detail || 'Snapshot comparison failed' },
                { status: response.status },
            );
        }

        return NextResponse.json(data);
    } catch (error: unknown) {
        console.error('[proxy/snapshot-diff] Backend unreachable:', error);
        if (allowFallback) {
            const result = compareDevComplianceSnapshots({
                tenantId,
                snapshotA,
                snapshotB,
            });
            if (result) {
                return NextResponse.json(result);
            }
        }
        return NextResponse.json(
            { error: 'Snapshot comparison service unavailable' },
            { status: 503 },
        );
    }
}
