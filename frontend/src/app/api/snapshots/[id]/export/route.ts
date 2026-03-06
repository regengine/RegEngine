import { NextRequest, NextResponse } from 'next/server';
import pg from 'pg';

const { Client } = pg;

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [{ id: 'export_static' }];
};

interface PageProps {
    params: Promise<{ id: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: PageProps
) {
    if (process.env.REGENGINE_DEPLOY_MODE === 'static') {
        return NextResponse.json({ message: 'Dynamic export not available during static build' });
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
        const exportData = {
            snapshot_id: snapshot.id,
            export_timestamp: new Date().toISOString(),
            facility: {
                substation_id: snapshot.substation_id,
                facility_name: snapshot.facility_name,
            },
            temporal_data: {
                snapshot_time: snapshot.snapshot_time,
                created_at: snapshot.created_at,
            },
            system_state: {
                status: snapshot.system_status,
                generated_by: snapshot.generated_by,
                regulatory_version: snapshot.regulatory_version,
            },
            cryptographic_verification: {
                content_hash: snapshot.content_hash,
                signature_hash: snapshot.signature_hash,
                hash_algorithm: 'SHA-256',
            },
            chain_data: {
                previous_snapshot_id: snapshot.previous_snapshot_id,
                is_genesis: !snapshot.previous_snapshot_id,
            },
            compliance_data: {
                asset_states: snapshot.asset_states,
                esp_config: snapshot.esp_config,
                patch_metrics: snapshot.patch_metrics,
                active_mismatches: snapshot.active_mismatches,
            },
        };

        return new NextResponse(JSON.stringify(exportData, null, 2), {
            status: 200,
            headers: {
                'Content-Type': 'application/json',
                'Content-Disposition': `attachment; filename="snapshot-${id}.json"`,
                'X-Data-Source': 'DATABASE',
            },
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
