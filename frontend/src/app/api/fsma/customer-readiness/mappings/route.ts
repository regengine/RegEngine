import { NextResponse } from 'next/server';
import { MAPPING_REVIEW_ITEMS } from '@/lib/customer-readiness';
// Required for static export (output: 'export') compatibility
export const dynamic = 'force-static';

export async function GET() {
    return NextResponse.json({
        items: MAPPING_REVIEW_ITEMS,
    });
}

export async function POST(request: Request) {
    const body = await request.json().catch(() => ({}));

    return NextResponse.json(
        {
            item: {
                id: 'mapping_preview_submission',
                source: body.source ?? 'Uploaded source schema',
                sourceField: body.sourceField ?? 'unknown_field',
                mappedField: body.mappedField ?? null,
                status: body.mappedField ? 'needs_review' : 'missing_required_kde',
                detail: 'Preview response from the frontend mock API route.',
            },
        },
        { status: 201 }
    );
}
