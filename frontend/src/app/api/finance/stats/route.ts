import { NextResponse } from 'next/server';

// Required for static export
export const dynamic = 'force-static';

export async function GET() {
    return NextResponse.json({
        total_snapshots: 430,
        compliant_ratio: 0.94,
        period: 'Q1-2026'
    });
}
