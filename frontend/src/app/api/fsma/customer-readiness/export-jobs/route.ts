import { NextResponse } from 'next/server';
export const dynamic = 'force-dynamic';

export async function GET() {
    const backendUrl = process.env.INGESTION_SERVICE_URL;
    if (backendUrl) {
        try {
            const res = await fetch(`${backendUrl}/api/v1/fsma/export-jobs`, {
                headers: { 'Content-Type': 'application/json' },
                cache: 'no-store',
            });
            if (res.ok) {
                const data = await res.json();
                return NextResponse.json(data);
            }
        } catch {
            // Backend unreachable — fall through to not_connected response
        }
    }

    return NextResponse.json({
        jobs: [],
        meta: {
            status: 'not_connected',
            message: 'Export job scheduling is not yet configured for this account.',
        },
    });
}

export async function POST() {
    return NextResponse.json(
        {
            error: 'Not Implemented',
            message: 'Export job scheduling is not yet available. Connect your supply chain data to enable this feature.',
        },
        { status: 501 }
    );
}
