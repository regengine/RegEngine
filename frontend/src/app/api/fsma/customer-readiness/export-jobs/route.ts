import { NextRequest, NextResponse } from 'next/server';
import {
    requireProxyAuth,
    resolveCallerTenantId,
    validateProxySession,
} from '@/lib/api-proxy';

export const dynamic = 'force-dynamic';

const NOT_CONNECTED_MESSAGE =
    'Export job scheduling is not yet configured for this account.';

/**
 * The "not yet configured" stub is a *success* shape the dashboard renders as an
 * explanatory banner. It is reserved for the two states that genuinely mean the
 * capability is not wired up:
 *   - `INGESTION_SERVICE_URL` is unset (`reason: 'unconfigured'`), or
 *   - the ingestion service does not expose the route at all, i.e. 404
 *     (`reason: 'upstream_route_missing'`).
 * Every other upstream status — and every network failure — is a real error and
 * is propagated as a non-2xx with a distinct code, instead of being masked as a
 * 200 that is indistinguishable from a healthy empty account (#2922).
 */
function notConnected(reason: 'unconfigured' | 'upstream_route_missing') {
    return NextResponse.json({
        jobs: [],
        meta: {
            status: 'not_connected',
            reason,
            message: NOT_CONNECTED_MESSAGE,
        },
    });
}

function upstreamError(code: string, message: string, status: number) {
    return NextResponse.json(
        { error: message, code, jobs: [], meta: { status: 'error', code } },
        { status },
    );
}

export async function GET(request: NextRequest) {
    // These proxies previously ran with no auth at all. Gate them now, before
    // they are ever connected to real tenant rows (#2922).
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    const backendUrl = process.env.INGESTION_SERVICE_URL;
    if (!backendUrl) {
        return notConnected('unconfigured');
    }

    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    // Server-derived tenant only — never the client-writable re_tenant_id cookie.
    const tenantId = await resolveCallerTenantId(request);
    if (tenantId) {
        headers['X-Tenant-ID'] = tenantId;
    }

    let res: Response;
    try {
        res = await fetch(`${backendUrl}/api/v1/fsma/export-jobs`, {
            headers,
            cache: 'no-store',
        });
    } catch (error) {
        console.error('[fsma/export-jobs] ingestion service unreachable', error);
        return upstreamError(
            'E_INGESTION_UNREACHABLE',
            'Export job service is unreachable',
            502,
        );
    }

    if (res.ok) {
        const data = await res.json().catch(() => null);
        if (data === null) {
            console.error('[fsma/export-jobs] ingestion returned a non-JSON body');
            return upstreamError(
                'E_INGESTION_BAD_RESPONSE',
                'Export job service returned an unreadable response',
                502,
            );
        }
        return NextResponse.json(data);
    }

    if (res.status === 404) {
        console.warn('[fsma/export-jobs] ingestion does not expose /api/v1/fsma/export-jobs');
        return notConnected('upstream_route_missing');
    }

    console.error(`[fsma/export-jobs] ingestion responded ${res.status}`);
    return upstreamError(
        'E_INGESTION_ERROR',
        'Export job lookup failed',
        res.status >= 500 ? 502 : res.status,
    );
}

export async function POST(request: NextRequest) {
    const authError = requireProxyAuth(request);
    if (authError) return authError;

    const sessionError = await validateProxySession(request);
    if (sessionError) return sessionError;

    return NextResponse.json(
        {
            error: 'Not Implemented',
            message: 'Export job scheduling is not yet available — it is still in development. Records remain exportable on demand from FDA Export.',
        },
        { status: 501 }
    );
}
