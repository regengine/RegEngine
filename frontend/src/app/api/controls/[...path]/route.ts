import { NextRequest, NextResponse } from 'next/server';

// Proxy controls/overlay API requests to the Admin backend service
// This allows browser clients to access controls endpoints without CORS issues

const ADMIN_URL = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';

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

export async function PUT(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    return proxyRequest(request, path, 'PUT');
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

        // Include body for POST/PUT requests
        if (method === 'POST' || method === 'PUT') {
            try {
                const body = await request.json();
                fetchOptions.body = JSON.stringify(body);
            } catch {
                // No body or invalid JSON, continue without body
            }
        }

        const response = await fetch(
            `${ADMIN_URL}/overlay/${path}${queryString}`,
            fetchOptions
        );

        const data = await response.json();

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Controls request failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);

    } catch (error: any) {
        console.error('Controls proxy error:', error);
        return NextResponse.json(
            { error: error.message || 'Controls request failed' },
            { status: 500 }
        );
    }
}
