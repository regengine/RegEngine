import { NextRequest, NextResponse } from 'next/server';

// Proxy ingestion requests to the backend service
// This allows browser clients to ingest files without CORS issues

export async function POST(request: NextRequest) {
    try {
        const formData = await request.formData();

        // Use 'admin' key for backend - demo-generated keys from admin service
        // are not recognized by the ingestion service in dev mode
        const apiKey = 'admin';

        const ingestionUrl = process.env.INGESTION_SERVICE_URL || 'http://localhost:8002';

        const response = await fetch(`${ingestionUrl}/ingest/file`, {
            method: 'POST',
            headers: {
                'X-RegEngine-API-Key': apiKey,
                // Do not set Content-Type header for multipart/form-data
                // fetch will set it automatically with the boundary
            },
            body: formData,
        });

        const data = await response.json();

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Ingestion failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);

    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Ingestion request failed';
        console.error('Ingestion proxy error:', error);
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
