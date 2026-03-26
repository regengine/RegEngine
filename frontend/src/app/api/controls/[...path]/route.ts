import { NextRequest, NextResponse } from 'next/server';

const ADMIN_URL = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';

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

        const path = pathParts.join('/');
        const url = new URL(request.url);
        const queryString = url.search;

        const fetchOptions: RequestInit = {
            method,
            headers: {
                'Content-Type': 'application/json',
                'X-Admin-Key': process.env.ADMIN_MASTER_KEY || 'admin',
                'X-RegEngine-API-Key': 'admin',
            },
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
            `${ADMIN_URL}/v1/admin/${path}${queryString}`,
            fetchOptions
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Controls request failed' },
                { status: response.status }
            );
        }

        console.info(`[proxy/controls] ${method} ${path} → ${response.status}`);
        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('Controls proxy error:', error);
        const message = error instanceof Error ? error.message : 'Controls request failed';
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
