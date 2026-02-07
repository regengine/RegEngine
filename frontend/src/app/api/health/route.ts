import { NextResponse } from 'next/server';

// Simple health check endpoint for the frontend
// This is called by various components to check API availability

export async function GET() {
    return NextResponse.json({
        status: 'healthy',
        service: 'regengine-frontend',
        timestamp: new Date().toISOString(),
    });
}
