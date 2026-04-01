/**
 * NLP Ask API route — proxies natural-language traceability queries to the
 * live NLP service at NLP_SERVICE_URL/query/traceability.
 *
 * When NLP_SERVICE_URL is not configured the route returns 503 with a clear
 * message so failures are visible rather than silently falling back to stubs.
 */
import { NextRequest, NextResponse } from 'next/server';
import { getServerServiceURL } from '@/lib/api-config';

export async function POST(request: NextRequest) {
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

    // Forward auth headers from the caller so the NLP service can verify the tenant.
    const forwardHeaders: Record<string, string> = {
        'Content-Type': 'application/json',
    };

    const headersToForward = [
        'X-RegEngine-API-Key',
        'X-Tenant-ID',
        'X-RegEngine-Tenant-ID',
        'X-Request-ID',
        'Authorization',
    ];
    for (const h of headersToForward) {
        const val = request.headers.get(h);
        if (val) forwardHeaders[h] = val;
    }

    // Also read api key from cookie (set by the dashboard login flow).
    const cookieApiKey = request.cookies.get('re_access_token')?.value;
    if (cookieApiKey && !forwardHeaders['Authorization']) {
        forwardHeaders['Authorization'] = `Bearer ${cookieApiKey}`;
    }

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
        return NextResponse.json(
            {
                error: 'nlp_service_unreachable',
                detail: `Could not reach NLP service at ${upstreamUrl}: ${String(err)}`,
            },
            { status: 503 },
        );
    }

    const data = await upstreamResponse.json().catch(() => ({}));
    return NextResponse.json(data, { status: upstreamResponse.status });
}
