import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import {
    requireProxyAuth,
    validateProxySession,
    getServerApiKey,
    validateUuid,
    enforceTenantMatch,
} from '@/lib/api-proxy';
import {
    allowDevComplianceSnapshotFallback,
    verifyDevComplianceSnapshot,
} from '@/lib/dev-compliance-snapshots';

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

    const { tenantId: rawTenantId, snapshotId: rawSnapshotId } = await params;
    // #1152-style hardening: tenantId/snapshotId are interpolated into the
    // upstream URL; validate as UUIDs before forwarding to prevent a
    // crafted segment (e.g. `../../admin/key`) from escaping the intended
    // path and reaching an unintended backend endpoint.
    const tenantId = validateUuid(rawTenantId);
    const snapshotId = validateUuid(rawSnapshotId);
    if (!tenantId || !snapshotId) {
        return NextResponse.json(
            { is_valid: false, error: 'Invalid tenant or snapshot identifier' },
            { status: 400 },
        );
    }

    // Cross-tenant authorization: bind this request to the caller's own tenant.
    const tenantError = enforceTenantMatch(request, tenantId);
    if (tenantError) return tenantError;
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
    const allowFallback = allowDevComplianceSnapshotFallback();
    const verifiedBy = url.searchParams.get('verified_by') || 'playwright@regengine.local';

    try {
        const response = await fetch(
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/${snapshotId}/verify${queryString}`,
            {
                method: 'GET',
                headers,
            }
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            if (allowFallback && (response.status === 404 || response.status === 503)) {
                const result = verifyDevComplianceSnapshot({
                    tenantId,
                    snapshotId,
                    verifiedBy,
                });
                if (result) {
                    return NextResponse.json(result);
                }
            }
            return NextResponse.json(
                { is_valid: false, error: data.detail || 'Verification failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('[proxy/verify] Backend unreachable:', error);
        if (allowFallback) {
            const result = verifyDevComplianceSnapshot({
                tenantId,
                snapshotId,
                verifiedBy,
            });
            if (result) {
                return NextResponse.json(result);
            }
        }
        return NextResponse.json(
            { is_valid: false, error: 'Verification service unavailable' },
            { status: 503 }
        );
    }
}
