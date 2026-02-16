import { NextResponse } from 'next/server';

// Required for static export
export const dynamic = 'force-static';

export async function GET() {
    return NextResponse.json({
        connected: false,
        message: 'Database check not available during static build'
    });
}
