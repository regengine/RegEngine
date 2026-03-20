import { NextResponse } from 'next/server';

export const dynamic = 'force-dynamic';

function getAdminKey(): string | null {
    return process.env.ADMIN_MASTER_KEY || null;
}

const ADMIN_URL = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';

export async function GET() {
    // Guard against static export execution
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
        return NextResponse.json([]);
    }

    const adminKey = getAdminKey();

    if (!adminKey) {
        return NextResponse.json(
            { error: 'Admin Master Key not configured on server' },
            { status: 500 }
        );
    }

    try {
        const res = await fetch(`${ADMIN_URL}/v1/admin/review/flagged-extractions?status_filter=PENDING&limit=50`, {
            headers: {
                'X-Admin-Key': adminKey,
            },
        });

        if (!res.ok) {
            throw new Error(`Failed to fetch review queue: ${res.statusText}`);
        }

        const data = await res.json();

        // Transform to match frontend expected format
        interface ReviewItemRaw {
            review_id: string;
            doc_hash: string;
            confidence_score: number;
            created_at: string;
            updated_at?: string;
            status?: string;
            tenant_id?: string;
            text_raw?: string;
            extraction?: Record<string, unknown>;
        }
        const items = (data.items || []).map((item: ReviewItemRaw) => ({
            id: item.review_id,
            doc_hash: item.doc_hash,
            confidence_score: item.confidence_score,
            created_at: item.created_at,
            updated_at: item.updated_at || item.created_at,
            status: item.status || 'PENDING',
            tenant_id: item.tenant_id || '',
            source_text: item.text_raw || '',
            extracted_data: item.extraction || {},
        }));

        return NextResponse.json(items);

    } catch (error: unknown) {
        console.error('Review queue fetch failed:', error);
        const message = error instanceof Error ? error.message : 'Failed to load review queue';
        return NextResponse.json(
            { error: message },
            { status: 500 }
        );
    }
}
