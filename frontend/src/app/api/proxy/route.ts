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

const BACKEND_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || getServerServiceURL('admin');

export async function POST(request: NextRequest) {
    try {
        // Defense-in-depth: reject requests with no auth credentials before proxying
        const authError = requireProxyAuth(request);
        if (authError) return authError;

        // Validate Supabase session tokens (expired/revoked sessions get 401)
        const sessionError = await validateProxySession(request);
        if (sessionError) return sessionError;

        const { url, method = 'GET', body } = await request.json();

        if (!url || typeof url !== 'string') {
            return NextResponse.json({ error: 'Missing url parameter' }, { status: 400 });
        }

        // Read credentials from HTTP-only cookies
        const apiKey = request.cookies.get('re_api_key')?.value;
        const adminKey = request.cookies.get('re_admin_key')?.value;
        const tenantId = request.cookies.get('re_tenant_id')?.value;

        const headers: Record<string, string> = {
            'Content-Type': 'application/json',
        };
        if (apiKey) headers['X-RegEngine-API-Key'] = apiKey;
        if (adminKey) headers['X-Admin-Key'] = adminKey;
        if (tenantId) headers['X-Tenant-ID'] = tenantId;

        // Forward the Supabase access token if present
        const authHeader = request.headers.get('Authorization');
        if (authHeader) headers['Authorization'] = authHeader;

        const backendUrl = url.startsWith('http') ? url : `${BACKEND_BASE}${url}`;

        const backendResponse = await fetch(backendUrl, {
            method,
            headers,
            body: body ? JSON.stringify(body) : undefined,
        });

        const data = await backendResponse.json().catch(() => ({}));
        return NextResponse.json(data, { status: backendResponse.status });
    } catch (err) {
        return NextResponse.json(
            { error: 'Proxy request failed', detail: String(err) },
            { status: 502 }
        );
    }
}
