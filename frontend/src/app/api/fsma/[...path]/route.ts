import { NextRequest, NextResponse } from 'next/server';
import { sanitizePath, proxyError } from '@/lib/api-proxy';

// force-dynamic ensures this proxy runs as a serverless function on every request.
// CI no longer uses static export.
export const dynamic = 'force-dynamic';

const COMPLIANCE_URL = process.env.COMPLIANCE_SERVICE_URL || 'http://localhost:8500';
const GRAPH_SERVICE_URL = process.env.GRAPH_SERVICE_URL || 'http://localhost:8200';

async function proxyRequest(
    request: NextRequest,
    pathParts: string[],
    method: string
) {
    try {
        const path = sanitizePath(pathParts);
        if (!path) {
            return proxyError('Invalid path', 400, { code: 'INVALID_PATH' });
        }
        const url = new URL(request.url);
        const queryString = url.search;

        const apiKey = request.headers.get('X-RegEngine-API-Key') || '';
        const tenantId = request.headers.get('X-Tenant-ID') || '';

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
            targetUrl = `${GRAPH_SERVICE_URL}/api/v1/fsma/${path}${queryString}`;
        } else {
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

        console.info(`[proxy/fsma] ${method} ${path} → ${response.status}`);
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

export async function DELETE(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const { path } = await params;
    return proxyRequest(request, path, 'DELETE');
}
