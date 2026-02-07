import { NextRequest, NextResponse } from 'next/server';

// Proxy ingestion requests to the backend service
// This allows browser clients to ingest documents without CORS issues

export async function POST(request: NextRequest) {
    try {
        const body = await request.json();
        // Use 'admin' key for backend - demo-generated keys from admin service
        // are not recognized by the ingestion service in dev mode
        const apiKey = 'admin';

        const ingestionUrl = process.env.INGESTION_SERVICE_URL || 'http://localhost:8002';

        const response = await fetch(`${ingestionUrl}/v1/ingest/url`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-RegEngine-API-Key': apiKey,
            },
            body: JSON.stringify(body),
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
