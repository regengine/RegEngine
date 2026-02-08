import { NextRequest, NextResponse } from 'next/server';

// Proxy opportunities API requests to the Opportunity backend service
// This allows browser clients to access opportunity endpoints without CORS issues

const OPPORTUNITY_URL = process.env.OPPORTUNITY_SERVICE_URL || 'http://localhost:8300';

// Required for static export
export function generateStaticParams() {
    return [];
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
                'X-RegEngine-API-Key': 'admin', // Use admin key for demo
            },
        };

        // Include body for POST requests
        if (method === 'POST') {
            try {
                const body = await request.json();
                fetchOptions.body = JSON.stringify(body);
            } catch {
                // No body or invalid JSON, continue without body
            }
        }

        const response = await fetch(
            `${OPPORTUNITY_URL}/${path}${queryString}`,
            fetchOptions
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Opportunity request failed', items: [] },
                { status: response.status }
            );
        }

        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('Opportunities proxy error:', error);
        const message = error instanceof Error ? error.message : 'Opportunity request failed';
        return NextResponse.json(
            { error: message, items: [] },
            { status: 500 }
        );
    }
}
