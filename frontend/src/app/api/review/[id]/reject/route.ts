import { NextRequest, NextResponse } from 'next/server';

const ADMIN_URL = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';

export const dynamic = 'force-dynamic';

export async function POST(
    request: NextRequest,
    { params }: { params: Promise<{ id: string }> }
) {
    try {
        // Guard against static export execution
        if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
            return NextResponse.json({ message: 'Dynamic action not available during static build' });
        }

        const { id } = await params;

        const response = await fetch(
            `${ADMIN_URL}/v1/admin/review/flagged-extractions/${id}/reject`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Admin-Key': process.env.ADMIN_MASTER_KEY || 'admin',
                },
                body: JSON.stringify({
                    reviewer_id: 'web-frontend',
                    notes: 'Rejected via web interface',
                }),
            }
        );

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            return NextResponse.json(
                { error: data.detail || 'Rejection failed' },
                { status: response.status }
            );
        }

        return NextResponse.json(data);
    } catch (error: unknown) {
        const message = error instanceof Error ? error.message : 'Rejection failed';
        console.error('Reject error:', error);
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
