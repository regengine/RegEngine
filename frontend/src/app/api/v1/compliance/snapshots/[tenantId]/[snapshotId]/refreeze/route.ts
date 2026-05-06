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
    const headers: Record<string, string> = {
        'Content-Type': request.headers.get('content-type') || 'application/json',
    };
    const apiKey = getServerApiKey();
    if (apiKey) {
        headers['X-RegEngine-API-Key'] = apiKey;
    }
    const allowFallback = allowDevComplianceSnapshotFallback();

    try {
        const response = await fetch(
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/${snapshotId}/refreeze`,
            {
                method: 'POST',
                headers,
                body: rawBody || undefined,
            },
        );
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
