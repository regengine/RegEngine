import { NextRequest, NextResponse } from 'next/server';

// Proxy compliance API requests to the Compliance backend service
// This allows browser clients to access compliance endpoints without CORS issues

const COMPLIANCE_URL = process.env.COMPLIANCE_SERVICE_URL || 'http://localhost:8500';

// Required for static export
export function generateStaticParams() {
    return [];
}

export async function GET(
    request: NextRequest,
    { params }: { params: { path: string[] } }
) {
    return proxyRequest(request, params.path, 'GET');
}

export async function POST(
    request: NextRequest,
    { params }: { params: { path: string[] } }
) {
    return proxyRequest(request, params.path, 'POST');
}

async function proxyRequest(
    request: NextRequest,
    pathParts: string[],
    method: string
) {
    try {
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

        return NextResponse.json(data);

    } catch (error: any) {
        console.error('Compliance proxy error:', error);
        return NextResponse.json(
            { error: error.message || 'Compliance request failed' },
            { status: 500 }
        );
    }
}
