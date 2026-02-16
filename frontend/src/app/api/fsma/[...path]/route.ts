import { NextRequest, NextResponse } from 'next/server';

const COMPLIANCE_URL = process.env.COMPLIANCE_SERVICE_URL || 'http://localhost:8500';

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [{ path: ['_build'] }];
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
            `${COMPLIANCE_URL}/fsma-204/${path}${queryString}`,
            fetchOptions
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'FSMA request failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('FSMA proxy error:', error);
        const message = error instanceof Error ? error.message : 'FSMA request failed';
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
