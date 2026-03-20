import { NextResponse } from 'next/server';
import { ARCHIVE_EXPORT_JOBS } from '@/lib/customer-readiness';
export const dynamic = 'force-dynamic';

export async function GET() {
    return NextResponse.json({
        jobs: ARCHIVE_EXPORT_JOBS,
    });
}

export async function POST(request: Request) {
    const body = await request.json().catch(() => ({}));

    return NextResponse.json(
        {
            job: {
                id: 'job_created_preview',
                name: body.name ?? 'New recurring archive job',
                format: body.format ?? 'FDA Package',
                cadence: body.cadence ?? 'Weekly',
                destination: body.destination ?? 'Object storage archive',
                status: 'active',
                lastRun: 'Not yet run',
                nextRun: 'Scheduled after save',
                manifestHash: 'sha256:pending-first-run',
                tenantId: body.tenantId ?? 'tenant_preview',
            },
        },
        { status: 201 }
    );
}
