import { NextResponse } from 'next/server';
import { RECALL_DRILL_RUNS } from '@/lib/customer-readiness';
// Required for static export (output: 'export') compatibility
export const dynamic = 'force-static';

export async function GET() {
    return NextResponse.json({
        drills: RECALL_DRILL_RUNS,
    });
}

export async function POST(request: Request) {
    const body = await request.json().catch(() => ({}));

    return NextResponse.json(
        {
            drill: {
                id: 'drill_preview_run',
                scenario: body.scenario ?? 'Customer-triggered drill',
                lots: body.lots ?? ['LOT-PREVIEW-001'],
                dateRange: body.dateRange ?? 'Preview range',
                status: 'in_progress',
                elapsed: '0m 00s',
                artifacts: ['live workspace'],
                warnings: ['Preview route: final artifact generation is simulated in the frontend layer.'],
            },
        },
        { status: 202 }
    );
}
