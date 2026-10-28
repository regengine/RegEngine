import { NextRequest, NextResponse } from 'next/server';
import { fetchAdminSessionPath } from '@/lib/admin-session-fetch';
import { rejectRetiredPrivilegedCredential } from '@/lib/api-proxy';
import { appendOpaqueSessionCookies, passthroughRequestHeaders } from '@/lib/proxy-factory';
import { attestPrivilegedProxyClientIp } from '@/lib/proxy-ip-attestation';

export const dynamic = 'force-dynamic';

export async function GET(request: NextRequest) {
    const retiredCredentialError = rejectRetiredPrivilegedCredential(request);
    if (retiredCredentialError) return retiredCredentialError;

    try {
        const headers = new Headers({ accept: 'application/json' });
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

        const res = await fetchAdminSessionPath(
            '/v1/admin/review/flagged-extractions?status_filter=PENDING&limit=50',
            {
                headers,
                cache: 'no-store',
            },
        );

        if (!res) {
            return NextResponse.json({ error: 'Review service unavailable' }, { status: 502 });
        }

        if (!res.ok) {
            const error = await res.json().catch(() => ({}));
            const requestId = res.headers.get('x-request-id');
            return NextResponse.json(
                { error: error.detail || 'Failed to load review queue' },
                requestId ? { status: res.status, headers: { 'x-request-id': requestId } } : { status: res.status },
            );
        }

        const data = await res.json();

        // Transform to match frontend expected format
        interface ReviewItemRaw {
            review_id: string;
            doc_hash: string;
            confidence_score: number;
            created_at: string;
            updated_at?: string;
            status?: string;
            tenant_id?: string;
            text_preview?: string;
            extraction?: Record<string, unknown>;
        }
        const items = (data.items || []).map((item: ReviewItemRaw) => ({
            id: item.review_id,
            doc_hash: item.doc_hash,
            confidence_score: item.confidence_score,
            created_at: item.created_at,
            updated_at: item.updated_at || item.created_at,
            status: item.status || 'PENDING',
            tenant_id: item.tenant_id || '',
            source_text: item.text_preview || '',
            extracted_data: item.extraction || {},
        }));

        const requestId = res.headers.get('x-request-id');
        return requestId
            ? NextResponse.json(items, { headers: { 'x-request-id': requestId } })
            : NextResponse.json(items);

    } catch (error: unknown) {
        console.error('Review queue fetch failed:', error);
        return NextResponse.json(
            { error: 'Review service unavailable' },
            { status: 502 }
        );
    }
}
