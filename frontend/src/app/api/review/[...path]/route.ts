import { NextRequest, NextResponse } from 'next/server';

// Proxy review API requests to the Admin backend service
// This allows browser clients to access review endpoints without CORS issues

const ADMIN_URL = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    // Return a dummy path to satisfy Next.js static export requirement for catch-all
    return [{ path: ['_build'] }];
};

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
            return NextResponse.json({ message: 'Dynamic proxy not available during static build' });
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

        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('Review proxy error:', error);
        const message = error instanceof Error ? error.message : 'Review request failed';
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
