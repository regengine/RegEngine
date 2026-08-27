/**
 * NLP Ask API route — proxies natural-language traceability queries to the
 * live NLP service at NLP_SERVICE_URL/query/traceability.
 *
 * Brought in line with the shared proxy pattern (#2538): this route used to be
 * the lone hand-written proxy that skipped requireProxyAuth/validateProxySession
 * and forwarded caller-supplied credential headers (X-RegEngine-API-Key,
 * X-Tenant-ID, Authorization, …) verbatim — the exact header-trust drift the
 * proxy factory exists to prevent (#1152). It now runs the standard preflight,
 * strips caller-managed credential headers, and injects the authoritative tenant
 * + first-party service key server-side via applyCookieCredentials /
 * applyFirstPartyServiceCredentials.
 *
 * When NLP_SERVICE_URL is not configured the route returns 503 with a clear
 * message so failures are visible rather than silently falling back to stubs.
 */
import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';
import {
    requireProxyAuth,
    validateProxySession,
    hasSupabaseSessionCookies,
} from '@/lib/api-proxy';
import {
    applyCookieCredentials,
    applyFirstPartyServiceCredentialsForSession,
} from '@/lib/proxy-factory';
import { experimentalFeaturesEnabled } from '@/lib/experimental-features';

export async function POST(request: NextRequest) {
    // The NLP router is auto-disabled in production unless experimental routers
    // are enabled; mirror the /tools/ask page-level guard so the API surface is
    // not publicly reachable when the feature is off.
    if (!experimentalFeaturesEnabled()) {
        return NextResponse.json({ error: 'Not found' }, { status: 404 });
    }

    // Defense-in-depth: reject requests with no auth credentials before proxying,
    // matching createJsonProxy. Supabase-only sessions get full session validation.
    const authError = requireProxyAuth(request);
    const requireSupabaseSession = Boolean(authError && hasSupabaseSessionCookies(request));
    if (authError && !requireSupabaseSession) return authError;

    const sessionError = await validateProxySession(request, { requireSupabaseSession });
    if (sessionError) return sessionError;

    const nlpBaseUrl = process.env.NLP_SERVICE_URL || getServerServiceURL('nlp');
    if (!nlpBaseUrl) {
        return NextResponse.json(
            {
                error: 'nlp_service_not_configured',
                detail:
                    'NLP_SERVICE_URL is not set. Configure this environment variable to ' +
                    'enable live natural-language traceability queries.',
            },
            { status: 503 },
        );
    }

    let body: unknown;
    try {
        body = await request.json();
    } catch {
        return NextResponse.json({ error: 'Invalid JSON body' }, { status: 400 });
    }

    // Build outbound headers from validated cookies/env — never from caller-
    // supplied credential headers. applyCookieCredentials strips browser-managed
    // X-RegEngine-API-Key / X-Tenant-ID / Authorization and re-injects from the
    // httpOnly cookies; applyFirstPartyServiceCredentials adds the server key and
    // authoritative tenant for cookie/session callers and fails closed without a
    // valid tenant context.
    const forwardHeaders = new Headers({ 'Content-Type': 'application/json' });
    const requestId = request.headers.get('X-Request-ID');
    if (requestId) forwardHeaders.set('X-Request-ID', requestId);

    applyCookieCredentials(forwardHeaders, request);
    const credentialError = await applyFirstPartyServiceCredentialsForSession(forwardHeaders, request);
    if (credentialError) return credentialError;

    const upstreamUrl = `${nlpBaseUrl.replace(/\/$/, '')}/query/traceability`;

    let upstreamResponse: Response;
    try {
        upstreamResponse = await fetch(upstreamUrl, {
            method: 'POST',
            headers: forwardHeaders,
            body: JSON.stringify(body),
            // 30-second hard timeout to avoid hanging the edge function.
            signal: AbortSignal.timeout(30_000),
        });
    } catch (err) {
        const correlationId = crypto.randomUUID();
        console.error('[nlp/ask] Upstream request failed', { correlationId, upstreamUrl, error: String(err) });
        return NextResponse.json(
            {
                error: 'nlp_service_unreachable',
                detail: 'NLP service is temporarily unavailable. Please retry.',
                correlation_id: correlationId,
            },
            { status: 503 },
        );
    }

    const data = await upstreamResponse.json().catch(() => ({}));
    return NextResponse.json(data, { status: upstreamResponse.status });
}
