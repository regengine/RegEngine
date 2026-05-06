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
    buildDevComplianceSnapshotAuditPack,
} from '@/lib/dev-compliance-snapshots';

export const dynamic = 'force-dynamic';

function getComplianceUrl(): string {
    const url = process.env.COMPLIANCE_SERVICE_URL || getServerServiceURL('compliance');
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/audit-pack] COMPLIANCE_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
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
            `${COMPLIANCE_URL}/v1/compliance/snapshots/${tenantId}/${snapshotId}/audit-pack`,
            { headers },
        );

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            if (allowFallback && (response.status === 404 || response.status === 503)) {
                const auditPack = buildDevComplianceSnapshotAuditPack({ tenantId, snapshotId });
                if (auditPack) {
                    return new NextResponse(auditPack, {
                        status: 200,
                        headers: {
                            'content-type': 'text/plain; charset=utf-8',
                            'content-disposition': `attachment; filename="ZeroTrust-AuditPack-${snapshotId}.txt"`,
                            'cache-control': 'no-store',
                        },
                    });
                }
            }
            return NextResponse.json(
                { error: data.detail || 'Audit pack generation failed' },
                { status: response.status },
            );
        }

        const outgoingHeaders = new Headers();
        for (const header of ['content-type', 'content-disposition', 'cache-control']) {
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
        console.error('[proxy/audit-pack] Backend unreachable:', error);
        if (allowFallback) {
            const auditPack = buildDevComplianceSnapshotAuditPack({ tenantId, snapshotId });
            if (auditPack) {
                return new NextResponse(auditPack, {
                    status: 200,
                    headers: {
                        'content-type': 'text/plain; charset=utf-8',
                        'content-disposition': `attachment; filename="ZeroTrust-AuditPack-${snapshotId}.txt"`,
                        'cache-control': 'no-store',
                    },
                });
            }
        }
        return NextResponse.json(
            { error: 'Audit pack service unavailable' },
            { status: 503 },
        );
    }
}
