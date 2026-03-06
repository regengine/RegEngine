import { NextRequest, NextResponse } from 'next/server';
import pg from 'pg';

const { Client } = pg;

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [{ id: 'item_static' }];
};



interface PageProps {
    params: Promise<{ id: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: PageProps
) {
    // Guard against static export execution
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
        return NextResponse.json({ message: 'Dynamic data not available during static build' });
    }

    const { id } = await params;

    const dbUrl = process.env.DATABASE_URL;
    if (!dbUrl) {
        return NextResponse.json(
            { error: 'Database not configured' },
            { status: 503 }
        );
    }

    const client = new Client(dbUrl);

    try {
        await client.connect();

        const result = await client.query(
            `SELECT 
          id, substation_id, facility_name, snapshot_time, created_at,
          system_status::text as system_status, 
          generated_by::text as generated_by, 
          content_hash, signature_hash, previous_snapshot_id,
          asset_states, esp_config, patch_metrics, active_mismatches,
          regulatory_version
        FROM energy.compliance_snapshots
        WHERE id = $1::uuid`,
            [id]
        );

        if (result.rows.length === 0) {
            return NextResponse.json(
                { error: 'Snapshot not found' },
                { status: 404 }
            );
        }

        const snapshot = result.rows[0];

        const verification_status = snapshot.signature_hash ? 'valid' : 'pending';
        let chain_status: 'valid' | 'broken' | 'genesis' = 'genesis';

        if (snapshot.previous_snapshot_id) {
            const prevCheck = await client.query(
                'SELECT 1 FROM energy.compliance_snapshots WHERE id = $1',
                [snapshot.previous_snapshot_id]
            );
            chain_status = prevCheck.rows.length > 0 ? 'valid' : 'broken';
        }

        return NextResponse.json({
            ...snapshot,
            verification_status,
            chain_status,
            corruption_type: null,
            corruption_detected_at: null,
        }, {
            headers: { 'X-Data-Source': 'DATABASE' }
        });
    } catch (dbError: unknown) {
        const msg = dbError instanceof Error ? dbError.message : String(dbError);
        console.error('Database query failed:', msg);
        return NextResponse.json(
            { error: 'Database query failed', detail: msg },
            { status: 500 }
        );
    } finally {
        try { await client.end(); } catch { }
    }
}
