import { NextResponse } from 'next/server';

// Required for static export
export const dynamic = 'force-static';

export async function GET() {
    return NextResponse.json({
        status: 'ok',
        timestamp: new Date().toISOString(),
        services: {
            frontend: 'healthy',
            api: 'static-proxy-mode'
        }
    });
}
