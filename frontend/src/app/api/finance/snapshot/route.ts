import { NextResponse } from 'next/server';

// Required for static export
export const dynamic = 'force-static';

export async function GET() {
    return NextResponse.json({
        id: 'finance-snapshot-latest',
        status: 'FINALIZED',
        vertical: 'FINANCE'
    });
}
