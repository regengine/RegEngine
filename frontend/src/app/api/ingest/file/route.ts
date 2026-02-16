import { NextRequest, NextResponse } from 'next/server';

// Required for static export
export const dynamic = 'force-static';

export async function POST(request: NextRequest) {
    // Guard against static export execution
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
        return NextResponse.json({ success: true, message: 'Upload queued (static mode)' });
    }

    return NextResponse.json({ success: true });
}
