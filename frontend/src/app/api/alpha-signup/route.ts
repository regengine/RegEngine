import { NextRequest, NextResponse } from 'next/server';

// Required for static export
export const dynamic = 'force-static';

export async function POST(request: NextRequest) {
    return NextResponse.json({ success: true, message: 'Action not available during static build' });
}
