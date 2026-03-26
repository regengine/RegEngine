import { NextRequest, NextResponse } from 'next/server';
import { sanitizePath, proxyError, getServerApiKey, getAdminMasterKey } from '@/lib/api-proxy';

// Proxy review API requests to the Admin backend service
// This allows browser clients to access review endpoints without CORS issues

const ADMIN_URL = (() => {
    const url = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';
    const onVercel = Boolean(process.env.VERCEL || process.env.VERCEL_URL);
    if (onVercel && url.includes('.railway.internal')) {
        console.warn('[proxy/review] ADMIN_SERVICE_URL points to internal Railway URL — unreachable from Vercel.');
        return 'http://localhost:8400';
    }
    return url;
})();

export const dynamic = 'force-dynamic';

export async function GET(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const resolvedParams = await params;
    return proxyRequest(request, resolvedParams.path, 'GET');
}

export async function POST(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const resolvedParams = await params;
    return proxyRequest(request, resolvedParams.path, 'POST');
}

export async function DELETE(
    request: NextRequest,
    { params }: { params: Promise<{ path: string[] }> }
) {
    const resolvedParams = await params;
    return proxyRequest(request, resolvedParams.path, 'DELETE');
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
        const adminKey = getAdminMasterKey();
        if (adminKey) {
            headers['X-Admin-Key'] = adminKey;
        }
        const apiKey = getServerApiKey();
        if (apiKey) {
            headers['X-RegEngine-API-Key'] = apiKey;
        }

        const fetchOptions: RequestInit = {
            method,
            headers,
        };

        // Include body for POST requests
        if (method === 'POST') {
            try {
                const body = await request.json();
                // Add default reviewer info if not provided
                const enrichedBody = {
                    reviewer_id: 'web-frontend',
                    notes: 'Action via web interface',
                    ...body,
                };
                fetchOptions.body = JSON.stringify(enrichedBody);
            } catch {
                // For approve/reject with no body, send default payload
                fetchOptions.body = JSON.stringify({
                    reviewer_id: 'web-frontend',
                    notes: `${path.includes('approve') ? 'Approved' : 'Rejected'} via web interface`,
                });
            }
        }

        // Build backend path - insert 'flagged-extractions' for ID-based routes
        // Frontend: /api/review/{id}/approve → Backend: /v1/admin/review/flagged-extractions/{id}/approve
        let backendPath = path;
        if (path.match(/^[0-9a-f-]+\/(approve|reject)$/)) {
            // This is an ID-based action, inject 'flagged-extractions' prefix
            backendPath = `flagged-extractions/${path}`;
        }

        const response = await fetch(
            `${ADMIN_URL}/v1/admin/review/${backendPath}${queryString}`,
            fetchOptions
        );

        const data = await response.json().catch(() => ([]));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Review request failed' },
                { status: response.status }
            );
        }

        console.info(`[proxy/review] ${method} ${path} → ${response.status}`);
        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('Review proxy error:', error);
        const message = error instanceof Error ? error.message : 'Review request failed';
        return proxyError(message, 500);
    }
}
