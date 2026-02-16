import { NextResponse } from 'next/server';

// Required for static export
export const dynamic = 'force-static';

export async function POST() {
    return NextResponse.json({
        success: true,
        message: 'Demo environment setup not available during static build'
    });
}
