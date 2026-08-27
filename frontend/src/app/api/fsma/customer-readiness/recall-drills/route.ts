import { NextRequest, NextResponse } from 'next/server';
import {
    requireProxyAuth,
    resolveCallerTenantId,
    validateProxySession,
} from '@/lib/api-proxy';

export const dynamic = 'force-dynamic';

const NOT_CONNECTED_MESSAGE =
    'Recall drill automation is not yet configured for this account.';

/**
 * The "not yet configured" stub is a *success* shape the dashboard renders as an
 * explanatory banner. It is reserved for the two states that genuinely mean the
 * capability is not wired up:
 *   - `INGESTION_SERVICE_URL` is unset (`reason: 'unconfigured'`), or
 *   - the ingestion service does not expose the route at all, i.e. 404
 *     (`reason: 'upstream_route_missing'`).
 *
 * The second case is the live one here: `/api/v1/fsma/recall/drills` does not
 * exist in the ingestion service — `services/ingestion/app/fsma_readiness_compat.py`
 * defines only `/export-jobs` and `/mappings`. Keeping 404 on the stub path
 * preserves today's user-facing copy for that known gap while still tagging the
 * reason, so it is distinguishable from an unset service URL. Every other
 * upstream status — and every network failure — is a real error and is
 * propagated as a non-2xx with a distinct code rather than masked as a 200 (#2922).
 *
 * Remaining work tracked by #2922: either implement
 * `/api/v1/fsma/recall/drills` in the ingestion service, or delete this proxy
 * and its dashboard entry. Both live outside this file.
 */
function notConnected(reason: 'unconfigured' | 'upstream_route_missing') {
    return NextResponse.json({
        items: [],
        meta: {
            status: 'not_connected',
            reason,
            message: NOT_CONNECTED_MESSAGE,
        },
    });
}

function upstreamError(code: string, message: string, status: number) {
    return NextResponse.json(
        { error: message, code, items: [], meta: { status: 'error', code } },
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
        res = await fetch(`${backendUrl}/api/v1/fsma/recall/drills`, {
            headers,
            cache: 'no-store',
        });
    } catch (error) {
        console.error('[fsma/recall-drills] ingestion service unreachable', error);
        return upstreamError(
            'E_INGESTION_UNREACHABLE',
            'Recall drill service is unreachable',
            502,
        );
    }

    if (res.ok) {
        const data = await res.json().catch(() => null);
        if (data === null) {
            console.error('[fsma/recall-drills] ingestion returned a non-JSON body');
            return upstreamError(
                'E_INGESTION_BAD_RESPONSE',
                'Recall drill service returned an unreadable response',
                502,
            );
        }
        return NextResponse.json(data);
    }

    if (res.status === 404) {
        console.warn('[fsma/recall-drills] ingestion does not expose /api/v1/fsma/recall/drills');
        return notConnected('upstream_route_missing');
    }

    console.error(`[fsma/recall-drills] ingestion responded ${res.status}`);
    return upstreamError(
        'E_INGESTION_ERROR',
        'Recall drill lookup failed',
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
            message: 'Recall drill automation is not yet available — it is still in development. Run a manual drill from the Requests workflow in the meantime.',
        },
        { status: 501 }
    );
}
