import { NextRequest, NextResponse } from 'next/server';

// Proxy FSMA API requests to the Graph/FSMA backend service
// This allows browser clients to access FSMA endpoints without CORS issues

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
        const fsmaUrl = process.env.GRAPH_SERVICE_URL || 'http://localhost:8200';
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
            `${fsmaUrl}/v1/fsma/${path}${queryString}`,
            fetchOptions
        );

        // For file downloads, return blob
        const contentType = response.headers.get('content-type') || '';
        if (contentType.includes('text/csv') || contentType.includes('application/octet-stream')) {
            const blob = await response.blob();
            return new NextResponse(blob, {
                status: response.status,
                headers: {
                    'Content-Type': contentType,
                    'Content-Disposition': response.headers.get('content-disposition') || '',
                },
            });
        }

        const data = await response.json();

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'FSMA request failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);

    } catch (error: any) {
        console.error('FSMA proxy error:', error);
        return NextResponse.json(
            { error: error.message || 'FSMA request failed' },
            { status: 500 }
        );
    }
}
