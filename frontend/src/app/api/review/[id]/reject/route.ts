import { NextRequest, NextResponse } from 'next/server';
import { fetchAdminSessionPath } from '@/lib/admin-session-fetch';
import { rejectRetiredPrivilegedCredential, safeSegment } from '@/lib/api-proxy';
import { appendOpaqueSessionCookies, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { attestPrivilegedProxyClientIp } from '@/lib/proxy-ip-attestation';

export const dynamic = 'force-dynamic';

export async function POST(
    request: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    const retiredCredentialError = rejectRetiredPrivilegedCredential(request);
    if (retiredCredentialError) return retiredCredentialError;

    const { id: rawId } = await params;
    const id = safeSegment(rawId);
    if (!id) {
        return NextResponse.json({ error: 'Invalid review identifier' }, { status: 400 });
    }

    try {
        const headers = new Headers({
            accept: 'application/json',
            'content-type': 'application/json',
        });
        passthroughRequestHeaders(headers, request, [
            'origin',
            'referer',
            'user-agent',
            'x-csrf-token',
            'x-request-id',
            'x-tenant-id',
        ]);
        appendOpaqueSessionCookies(headers, request);
        const attestationError = attestPrivilegedProxyClientIp(headers, request);
        if (attestationError) return attestationError;
        const response = await fetchAdminSessionPath(
            `/v1/admin/review/flagged-extractions/${id}/reject`,
            {
                method: 'POST',
                headers,
                body: JSON.stringify({}),
            }
        );

        if (!response) {
            return NextResponse.json({ error: 'Review service unavailable' }, { status: 502 });
        }

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Rejection failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);
    } catch (error: unknown) {
        console.error('Reject error:', error);
        return NextResponse.json(
            { error: 'Review service unavailable' },
            { status: 502 }
        );
    }
}
