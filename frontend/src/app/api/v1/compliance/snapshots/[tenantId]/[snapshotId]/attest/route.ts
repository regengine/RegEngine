import { NextRequest, NextResponse } from 'next/server';
import {
    requireProxyAuth,
    validateProxySession,
    validateUuid,
    enforceTenantMatch,
} from '@/lib/api-proxy';
import { prepareTenantScopedProxyHeaders, rejectUpstreamRedirect } from '@/lib/proxy-factory';
import {
    allowDevComplianceSnapshotFallback,
    attestDevComplianceSnapshot,
} from '@/lib/dev-compliance-snapshots';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || process.env.NEXT_PUBLIC_API_BASE_URL;
    if (url) {
        const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
        if (onVercel && url.includes('.railway.internal')) {
            console.warn('[proxy/attest] COMPLIANCE_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
            return process.env.NEXT_PUBLIC_API_BASE_URL || url;
        }
        return url;
    }
    if (process.env.VERCEL) {
        console.error('[api/attest] COMPLIANCE_SERVICE_URL not configured — localhost is unreachable from Vercel');
        return '';
    }
    return 'http://localhost:8500';
}

export const dynamic = 'force-dynamic';

interface Props {
    params: Promise<{ tenantId: string; snapshotId: string }>;
}

export async function POST(
    request: NextRequest,
    { params }: Props
) {
    // Defense-in-depth: reject requests with no auth credentials before proxying
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    // Validate Supabase session tokens (expired/revoked sessions get 401)
    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    const COMPLIANCE_URL = getComplianceUrl();
    const allowFallback = allowDevComplianceSnapshotFallback();
    if (!COMPLIANCE_URL && !allowFallback) {
        console.error('[proxy/attest] 503 — compliance backend not configured');
        return NextResponse.json(
            { error: 'backend_not_configured', message: 'Compliance backend is not configured' },
            { status: 503 },
        );
    }

    const { tenantId: rawTenantId, snapshotId: rawSnapshotId } = await params;
    // Validate UUIDs before interpolating into the upstream URL.
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
    const body = await request.json().catch(() => ({}));
    const parsedBody = typeof body === 'object' && body !== null ? body as Record<string, unknown> : {};

    // Forward the caller's tenant credential/session. A first-party key is
    // injected only when its configured tenant binding matches the path.
    const headers = new Headers({ 'Content-Type': 'application/json' });
    const credentialError = prepareTenantScopedProxyHeaders(headers, request, tenantId);
    if (credentialError) return credentialError;

    // When the backend base is unresolved (empty sentinel from getComplianceUrl),
    // never construct a relative fetch URL. Use the dev fallback if available.
    if (!COMPLIANCE_URL && allowFallback) {
        const result = attestDevComplianceSnapshot({
            tenantId,
            snapshotId,
            attestedBy: String(parsedBody.attested_by || 'playwright@regengine.local'),
            attestationTitle: String(parsedBody.attestation_title || 'Compliance Owner'),
        });
        if (result) {
            return NextResponse.json(result);
        }
    }

    try {
        const response = await fetch(
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/${snapshotId}/attest`,
            {
                method: 'POST',
                headers,
                body: JSON.stringify(body),
                redirect: 'manual',
            }
        );
        const redirectError = rejectUpstreamRedirect(response, 'compliance-snapshot-attest');
        if (redirectError) return redirectError;

        if (!response.ok) {
            const error = await response.json().catch(() => ({}));
            if (allowFallback && (response.status === 404 || response.status === 503)) {
                const result = attestDevComplianceSnapshot({
                    tenantId,
                    snapshotId,
                    attestedBy: String(parsedBody.attested_by || 'playwright@regengine.local'),
                    attestationTitle: String(parsedBody.attestation_title || 'Compliance Owner'),
                });
                if (result) {
                    return NextResponse.json(result);
                }
            }
            console.error('Attestation failed:', response.status, error);
            return NextResponse.json(
                { error: error.detail || 'Attestation failed' },
                { status: response.status }
            );
        }

        const data = await response.json();
        return NextResponse.json(data);
    } catch (error: unknown) {
        if (allowFallback) {
            const result = attestDevComplianceSnapshot({
                tenantId,
                snapshotId,
                attestedBy: String(parsedBody.attested_by || 'playwright@regengine.local'),
                attestationTitle: String(parsedBody.attestation_title || 'Compliance Owner'),
            });
            if (result) {
                return NextResponse.json(result);
            }
        }
        const message = error instanceof Error ? error.message : 'Attestation request failed';
        console.error('Attestation proxy error:', message);
        return NextResponse.json(
            { error: message },
            { status: 502 }
        );
    }
}
