import { NextRequest, NextResponse } from 'next/server';
import { sanitizePath, proxyError, requireProxyAuth, validateProxySession } from '@/lib/api-proxy';

// force-dynamic ensures this proxy runs as a serverless function on every request.
// CI no longer uses static export.
export const dynamic = 'force-dynamic';

function guardUrl(envVar: string, fallback: string): string {
    const url = process.env[envVar] || process.env.NEXT_PUBLIC_API_BASE_URL;
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (url) {
        if (onVercel && url.includes('.railway.internal')) {
            console.warn(`[proxy/fsma] ${envVar} points to internal Railway URL — unreachable from Vercel.`);
            return '';
        }
        return url;
    }
    if (onVercel) {
        console.error(`[proxy/fsma] ${envVar} not configured — localhost is unreachable from Vercel`);
        return '';
    }
    return fallback;
}
const COMPLIANCE_URL = guardUrl('COMPLIANCE_SERVICE_URL', 'http://localhost:8500');
const GRAPH_SERVICE_URL = guardUrl('GRAPH_SERVICE_URL', 'http://localhost:8200');

async function proxyRequest(
    request: NextRequest,
    pathParts: string[],
    method: string
) {
    try {
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

        // Read credentials from HTTP-only cookies first, fall back to headers
        const apiKey = request.cookies.get('re_api_key')?.value
            || request.headers.get('X-RegEngine-API-Key')
            || process.env.REGENGINE_API_KEY
            || '';
        const tenantId = request.cookies.get('re_tenant_id')?.value
            || request.headers.get('X-Tenant-ID')
            || '';

        const fetchOptions: RequestInit = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'X-RegEngine-API-Key': apiKey,
                ...(tenantId && { 'X-Tenant-ID': tenantId }),
            },
        };

        if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
            try {
                const body = await request.json();
                fetchOptions.body = JSON.stringify(body);
            } catch {
                // No body or invalid JSON
            }
        }

        // Route to the correct backend service
        let targetUrl: string;
        if (
            path.startsWith('compliance/') ||
            path.startsWith('traceability/') ||
            path.startsWith('recall/') ||
            path.startsWith('science/') ||
            path.startsWith('metrics/') ||
            path.startsWith('drift/') ||
            path.startsWith('gaps') ||
            path.startsWith('export/')
        ) {
            if (!GRAPH_SERVICE_URL) {
                return proxyError('GRAPH_SERVICE_URL not configured', 503);
            }
            targetUrl = `${GRAPH_SERVICE_URL}/api/v1/fsma/${path}${queryString}`;
        } else {
            if (!COMPLIANCE_URL) {
                return proxyError('COMPLIANCE_SERVICE_URL not configured', 503);
            }
            // Wizard / applicability / exemptions — handled by Compliance Service
            targetUrl = `${COMPLIANCE_URL}/fsma-204/${path}${queryString}`;
        }

        const response = await fetch(targetUrl, fetchOptions);
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'FSMA request failed' },
                { status: response.status }
            );
        }

        if (process.env.NODE_ENV !== 'production') { console.info(`[proxy/fsma] ${method} ${path} → ${response.status}`); }
        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('FSMA proxy error:', error);
        const message = error instanceof Error ? error.message : 'FSMA request failed';
        return proxyError(message, 500);
    }
}

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
