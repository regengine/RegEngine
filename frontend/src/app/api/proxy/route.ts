/**
 * API proxy — forwards requests to the RegEngine backend with credentials
 * from HTTP-only cookies. The browser never sees the raw API key.
 *
 * Usage: POST /api/proxy { url: "/api/v1/...", method: "GET", body?: {...} }
 *
 * This is the migration path for CRITICAL #2. Frontend code should
 * gradually switch from direct backend calls (with localStorage API key)
 * to calls through this proxy.
 */
import { NextRequest, NextResponse } from 'next/server';
import { requireProxyAuth, validateProxySession } from '@/lib/api-proxy';
import { getServerServiceURL } from '@/lib/api-config';
import { applyCookieCredentials } from '@/lib/proxy-factory';

const BACKEND_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || getServerServiceURL('admin');
const ALLOWED_METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE']);

function normalizeRelativeProxyPath(value: string): string | null {
    if (!value.startsWith('/') || value.startsWith('//') || value.includes('://')) {
        return null;
    }

    const parsed = new URL(value, 'https://regengine.local');
    const path = parsed.pathname;
    if (
        !path.startsWith('/api/') &&
        !path.startsWith('/v1/') &&
        path !== '/health'
    ) {
        return null;
    }
    let decodedPath: string;
    try {
        decodedPath = decodeURIComponent(path);
    } catch {
        return null;
    }
    if (decodedPath.split('/').some((segment) => segment === '..' || segment.includes('\0'))) {
        return null;
    }

    return `${path}${parsed.search}`;
}

export async function POST(request: NextRequest) {
    try {
        // Defense-in-depth: reject requests with no auth credentials before proxying
        const authError = requireProxyAuth(request);
        if (authError) return authError;

        // Validate Supabase session tokens (expired/revoked sessions get 401)
        const sessionError = await validateProxySession(request);
        if (sessionError) return sessionError;

        const { url, method = 'GET', body } = await request.json();
        const normalizedMethod = String(method).toUpperCase();

        if (!url || typeof url !== 'string') {
            return NextResponse.json({ error: 'Missing url parameter' }, { status: 400 });
        }
        if (!ALLOWED_METHODS.has(normalizedMethod)) {
            return NextResponse.json({ error: 'Unsupported proxy method' }, { status: 405 });
        }

        const relativePath = normalizeRelativeProxyPath(url);
        if (!relativePath) {
            return NextResponse.json({ error: 'Proxy url must be a relative RegEngine API path' }, { status: 400 });
        }

        const headers = new Headers({
            'Content-Type': 'application/json',
        });
        applyCookieCredentials(headers, request);

        const backendUrl = `${BACKEND_BASE}${relativePath}`;

        const backendResponse = await fetch(backendUrl, {
            method: normalizedMethod,
            headers,
            body: normalizedMethod === 'GET' ? undefined : (body ? JSON.stringify(body) : undefined),
        });

        const data = await backendResponse.json().catch(() => ({}));
        return NextResponse.json(data, { status: backendResponse.status });
    } catch (err) {
        const correlationId = crypto.randomUUID();
        console.error('[proxy] Request failed', { correlationId, error: String(err) });
        return NextResponse.json(
            { error: 'Proxy request failed', correlation_id: correlationId },
            { status: 502 }
        );
    }
}
