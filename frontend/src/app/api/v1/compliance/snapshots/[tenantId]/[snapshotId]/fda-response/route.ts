import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import {
    requireProxyAuth,
    validateProxySession,
    getServerApiKey,
    validateUuid,
} from '@/lib/api-proxy';
import {
    allowDevComplianceSnapshotFallback,
    buildDevComplianceSnapshotFdaResponse,
} from '@/lib/dev-compliance-snapshots';

export const dynamic = 'force-dynamic';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/fda-response] COMPLIANCE_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
        return getServerServiceURL('compliance');
    }
    return url;
}

interface Props {
    params: Promise<{ tenantId: string; snapshotId: string }>;
}

export async function GET(
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

    const COMPLIANCE_URL = getComplianceUrl();
    const headers: Record<string, string> = {
        'Content-Type': 'application/json',
    };
    const apiKey = getServerApiKey();
    if (apiKey) {
        headers['X-RegEngine-API-Key'] = apiKey;
    }
    const allowFallback = allowDevComplianceSnapshotFallback();

    try {
        const response = await fetch(
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/${snapshotId}/fda-response`,
            { headers },
        );

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            if (allowFallback && (response.status === 404 || response.status === 503)) {
                const fdaResponse = buildDevComplianceSnapshotFdaResponse({ tenantId, snapshotId });
                if (fdaResponse) {
                    return NextResponse.json(fdaResponse);
                }
            }
            return NextResponse.json(
                { error: data.detail || 'FDA response generation failed' },
                { status: response.status },
            );
        }

        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('application/json')) {
            const data = await response.json();
            return NextResponse.json(data);
        }

        return NextResponse.json({ text: await response.text() });
    } catch (error: unknown) {
        console.error('[proxy/fda-response] Backend unreachable:', error);
        if (allowFallback) {
            const fdaResponse = buildDevComplianceSnapshotFdaResponse({ tenantId, snapshotId });
            if (fdaResponse) {
                return NextResponse.json(fdaResponse);
            }
        }
        return NextResponse.json(
            { error: 'FDA response service unavailable' },
            { status: 503 },
        );
    }
}
