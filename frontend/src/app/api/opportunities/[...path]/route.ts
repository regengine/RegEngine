import { NextRequest, NextResponse } from 'next/server';

const OPPORTunity_URL = process.env.OPPORTUNITY_SERVICE_URL || 'http://localhost:8300';

// Required for static export
export const dynamic = 'force-dynamic';
export const generateStaticParams = async () => {
    return [{ path: ['static_proxy'] }];
};

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
            return NextResponse.json({ message: 'Dynamic proxy not available during static build' });
        }

        const path = pathParts.join('/');
        const url = new URL(request.url);
        const queryString = url.search;

        const fetchOptions: RequestInit = {
            method,
            headers: {
                'Content-Type': 'application/json',
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
            `${OPPORTunity_URL}/${path}${queryString}`,
            fetchOptions
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Opportunity request failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('Opportunity proxy error:', error);
        const message = error instanceof Error ? error.message : 'Opportunity request failed';
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
