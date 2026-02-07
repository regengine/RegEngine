import { NextRequest, NextResponse } from 'next/server';
import pg from 'pg';

const { Client } = pg;

// Mock data as fallback
const MOCK_SNAPSHOTS: Record<string, any> = {
    '00000000-0000-0000-0000-000000000001': {
        id: '00000000-0000-0000-0000-000000000001',
        substation_id: 'TEST-ALPHA',
        facility_name: 'Alpha Test Station',
        snapshot_time: '2026-01-25T18:00:00Z',
        created_at: '2026-01-25T18:00:05Z',
        system_status: 'NOMINAL',
        generated_by: 'SYSTEM_AUTO',
        content_hash: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2',
        signature_hash: 'f2e1d0c9b8a7z6y5x4w3v2u1t0s9r8q7p6o5n4m3l2k1j0i9h8g7f6e5d4c3b2a1',
        previous_snapshot_id: null,
        regulatory_version: 'CIP-013-1',
        asset_states: {
            transformers: [
                { id: 'T1', status: 'operational', last_check: '2026-01-25T17:30:00Z' },
                { id: 'T2', status: 'operational', last_check: '2026-01-25T17:30:00Z' }
            ]
        },
        esp_config: { firewall_version: '2.4.1', ids_enabled: true },
        patch_metrics: { total_systems: 12, patched: 12, pending: 0 },
        active_mismatches: []
    },
    '00000000-0000-0000-0000-000000000002': {
        id: '00000000-0000-0000-0000-000000000002',
        substation_id: 'TEST-ALPHA',
        facility_name: 'Alpha Test Station',
        snapshot_time: '2026-01-25T19:00:00Z',
        created_at: '2026-01-25T19:00:05Z',
        system_status: 'DEGRADED',
        generated_by: 'INCIDENT_RESPONSE',
        content_hash: 'b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3',
        signature_hash: 'g3f2e1d0c9b8a7z6y5x4w3v2u1t0s9r8q7p6o5n4m3l2k1j0i9h8g7f6e5d4c3b2',
        previous_snapshot_id: '00000000-0000-0000-0000-000000000001',
        regulatory_version: 'CIP-013-1',
        asset_states: {
            transformers: [
                { id: 'T1', status: 'operational' },
                { id: 'T2', status: 'degraded', issue: 'High temperature' }
            ]
        },
        esp_config: { firewall_version: '2.4.1', ids_enabled: true },
        patch_metrics: { total_systems: 12, patched: 11, pending: 1 },
        active_mismatches: [{ asset_id: 'T2', type: 'PERFORMANCE_DEGRADATION' }]
    }
};

interface PageProps {
    params: Promise<{ id: string }>;
}

export async function GET(
    request: NextRequest,
    { params }: PageProps
) {
    const { id } = await params;

    // Try database first, fall back to mock
    const client = new Client({
        host: 'localhost',
        port: 5432,
        database: 'regengine_admin',
        user: 'regengine',
        password: 'regengine',
    });

    try {
        await client.connect();

        // Try to query from energy schema
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

        if (result.rows.length > 0) {
            const snapshot = result.rows[0];

            // Compute statuses
            const verification_status = snapshot.signature_hash ? 'valid' : 'pending';
            let chain_status: 'valid' | 'broken' | 'genesis' = 'genesis';

            if (snapshot.previous_snapshot_id) {
                const prevCheck = await client.query(
                    'SELECT 1 FROM energy.compliance_snapshots WHERE id = $1',
                    [snapshot.previous_snapshot_id]
                );
                chain_status = prevCheck.rows.length > 0 ? 'valid' : 'broken';
            }

            await client.end();

            return NextResponse.json({
                ...snapshot,
                verification_status,
                chain_status,
                corruption_type: null,
                corruption_detected_at: null,
            }, {
                headers: { 'X-Data-Source': 'DATABASE' }
            });
        }
    } catch (dbError: any) {
        console.log('Database query failed, using mock data:', dbError.message);
    } finally {
        try { await client.end(); } catch { }
    }

    // Fallback to mock data
    const snapshot = MOCK_SNAPSHOTS[id];

    if (!snapshot) {
        return NextResponse.json(
            { error: 'Snapshot not found' },
            { status: 404 }
        );
    }

    // Compute statuses for mock data
    const verification_status = snapshot.signature_hash ? 'valid' : 'pending';
    const chain_status = !snapshot.previous_snapshot_id ? 'genesis' : 'valid';

    return NextResponse.json({
        ...snapshot,
        verification_status,
        chain_status,
        corruption_type: null,
        corruption_detected_at: null,
    }, {
        headers: { 'X-Data-Source': 'MOCK' }
    });
}
