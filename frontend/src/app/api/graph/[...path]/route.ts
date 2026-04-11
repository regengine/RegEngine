import { NextRequest, NextResponse } from 'next/server';
import { sanitizePath, proxyError, getServerApiKey, requireProxyAuth, validateProxySession } from '@/lib/api-proxy';
import { getServerServiceURL } from '@/lib/api-config';

// Proxy graph API requests to the Graph backend service
// This allows browser clients to access graph endpoints without CORS issues

function getGraphUrl(): string {
    const url = process.env.GRAPH_SERVICE_URL || getServerServiceURL('graph');
    // Guard: *.railway.internal URLs are unreachable from Vercel serverless
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/graph] GRAPH_SERVICE_URL points to internal Railway URL — unreachable from Vercel. Set a public Railway URL.');
        return getServerServiceURL('graph');
    }
    return url;
}
const GRAPH_URL = getGraphUrl();

export const dynamic = 'force-dynamic';

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    return proxyRequest(request, path, 'GET');
}

export async function POST(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    return proxyRequest(request, path, 'POST');
}

export async function PUT(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    return proxyRequest(request, path, 'PUT');
}

export async function PATCH(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    return proxyRequest(request, path, 'PATCH');
}

export async function DELETE(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    return proxyRequest(request, path, 'DELETE');
}

async function proxyRequest(
    request: NextRequest,
    pathParts: string[],
    method: string
) {
    try {
        // Guard against static export execution
        if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
            return NextResponse.json(
                { error: 'API unavailable in static export mode. Deploy with server-side rendering for full API access.', deploy_mode: 'static' },
                { status: 503 },
            );
        }

        // Defense-in-depth: reject requests with no auth credentials before proxying
        const authError = requireProxyAuth(request);
        if (authError) return authError;

        // Validate Supabase session tokens (expired/revoked sessions get 401)
        const sessionError = await validateProxySession(request);
        if (sessionError) return sessionError;

        const path = sanitizePath(pathParts);
        if (!path) {
            return proxyError('Invalid path', 400, { code: 'INVALID_PATH' });
        }
        const url = new URL(request.url);
        const queryString = url.search;

        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };
        const apiKey = getServerApiKey();
        if (apiKey) {
            headers['X-RegEngine-API-Key'] = apiKey;
        }

        const fetchOptions: RequestInit = {
            method,
            headers,
        };

        if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
            try {
                const body = await request.json();
                fetchOptions.body = JSON.stringify(body);
            } catch {
                // No body or invalid JSON
            }
        }

        const response = await fetch(
            `${GRAPH_URL}/${path}${queryString}`,
            fetchOptions
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Graph request failed' },
                { status: response.status }
            );
        }

        if (process.env.NODE_ENV !== 'production') { console.info(`[proxy/graph] ${method} ${path} → ${response.status}`); }
        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('Graph proxy error:', error);
        const message = error instanceof Error ? error.message : 'Graph request failed';
        return proxyError(message, 500);
    }
}
