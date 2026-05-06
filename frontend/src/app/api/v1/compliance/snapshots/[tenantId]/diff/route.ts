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
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/diff?snapshot_a=${snapshotA}&snapshot_b=${snapshotB}`,
            { headers },
        );
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
