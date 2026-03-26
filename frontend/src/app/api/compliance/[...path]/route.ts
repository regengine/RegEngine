import { NextRequest, NextResponse } from 'next/server';
import { sanitizePath, proxyError, getServerApiKey } from '@/lib/api-proxy';

// Proxy compliance API requests to the Compliance backend service
// This allows browser clients to access compliance endpoints without CORS issues

const COMPLIANCE_URL = process.env.COMPLIANCE_SERVICE_URL || 'http://localhost:8500';

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

        if (method === 'POST') {
            try {
                const body = await request.json();
                fetchOptions.body = JSON.stringify(body);
            } catch {
                // No body or invalid JSON
            }
        }

        const response = await fetch(
            `${COMPLIANCE_URL}/${path}${queryString}`,
            fetchOptions
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Compliance request failed' },
                { status: response.status }
            );
        }

        console.info(`[proxy/compliance] ${method} ${path} → ${response.status}`);
        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('Compliance proxy error:', error);
        const message = error instanceof Error ? error.message : 'Compliance request failed';
        return proxyError(message, 500);
    }
}
