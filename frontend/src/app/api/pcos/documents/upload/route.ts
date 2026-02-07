import { NextRequest, NextResponse } from 'next/server';

// Proxy PCOS document uploads to the Admin service
// Handles multipart/form-data file uploads

const ADMIN_URL = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';

export async function POST(request: NextRequest) {
    try {
        // Get the form data from the request
        const formData = await request.formData();

        // Get tenant ID from header or use default
        const tenantId = request.headers.get('X-Tenant-ID') || '00000000-0000-0000-0000-000000000001';

        // Forward the multipart form data to the backend
        const response = await fetch(`${ADMIN_URL}/pcos/documents/upload`, {
            method: 'POST',
            headers: {
                'X-Tenant-ID': tenantId,
            },
            body: formData,
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Upload failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);

    } catch (error: unknown) {
        console.error('PCOS document upload proxy error:', error);
        const message = error instanceof Error ? error.message : 'Upload failed';
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
