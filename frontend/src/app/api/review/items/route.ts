import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

function getAdminKey(): string | null {
    let adminKey = process.env.ADMIN_MASTER_KEY;

    // Fallback: Try to read from root .env file (for local dev with docker-compose)
    if (!adminKey) {
        try {
            const envPath = path.resolve(process.cwd(), '../.env');
            if (fs.existsSync(envPath)) {
                const envContent = fs.readFileSync(envPath, 'utf8');
                const match = envContent.match(/ADMIN_MASTER_KEY=(.*)$/m);
                if (match && match[1]) {
                    adminKey = match[1].trim();
                    // Remove potential quotes
                    if ((adminKey.startsWith('"') && adminKey.endsWith('"')) ||
                        (adminKey.startsWith("'") && adminKey.endsWith("'"))) {
                        adminKey = adminKey.slice(1, -1);
                    }
                }
            }
        } catch (e) {
            console.warn('Failed to read root .env file:', e);
        }
    }

    return adminKey || null;
}

const ADMIN_URL = process.env.ADMIN_SERVICE_URL || 'http://localhost:8400';

export async function GET() {
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
        const items = (data.items || []).map((item: any) => ({
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

    } catch (error: any) {
        console.error('Review queue fetch failed:', error);
        return NextResponse.json(
            { error: error.message || 'Failed to load review queue' },
            { status: 500 }
        );
    }
}
