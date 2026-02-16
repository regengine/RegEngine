import { NextRequest, NextResponse } from 'next/server';

// Required for static export
export const dynamic = 'force-static';
export const generateStaticParams = async () => {
    return [{ id: '_build' }];
};

// Mock export data
const MOCK_EXPORTS: Record<string, any> = {
    '00000000-0000-0000-0000-000000000001': {
        snapshot_id: '00000000-0000-0000-0000-000000000001',
        export_timestamp: new Date().toISOString(),
        facility: {
            substation_id: 'TEST-ALPHA',
            facility_name: 'Alpha Test Station',
        },
        temporal_data: {
            snapshot_time: '2026-01-25T18:00:00Z',
            created_at: '2026-01-25T18:00:05Z',
        },
        system_state: {
            status: 'NOMINAL',
            generated_by: 'SYSTEM_AUTO',
            regulatory_version: 'CIP-013-1',
        },
        cryptographic_verification: {
            content_hash: 'a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2',
            signature_hash: 'f2e1d0c9b8a7z6y5x4w3v2u1t0s9r8q7p6o5n4m3l2k1j0i9h8g7f6e5d4c3b2a1',
            hash_algorithm: 'SHA-256',
        },
        chain_data: {
            previous_snapshot_id: null,
            is_genesis: true,
        },
        compliance_data: {
            asset_states: {
                transformers: [
                    { id: 'T1', status: 'operational' },
                    { id: 'T2', status: 'operational' }
                ]
            },
            esp_config: { firewall_version: '2.4.1' },
            patch_metrics: { total_systems: 12, patched: 12 },
        },
    },
    '00000000-0000-0000-0000-000000000002': {
        snapshot_id: '00000000-0000-0000-0000-000000000002',
        export_timestamp: new Date().toISOString(),
        facility: {
            substation_id: 'TEST-ALPHA',
            facility_name: 'Alpha Test Station',
        },
        temporal_data: {
            snapshot_time: '2026-01-25T19:00:00Z',
            created_at: '2026-01-25T19:00:05Z',
        },
        system_state: {
            status: 'DEGRADED',
            generated_by: 'INCIDENT_RESPONSE',
            regulatory_version: 'CIP-013-1',
        },
        cryptographic_verification: {
            content_hash: 'b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6a7b8c9d0e1f2g3',
            signature_hash: 'g3f2e1d0c9b8a7z6y5x4w3v2u1t0s9r8q7p6o5n4m3l2k1j0i9h8g7f6e5d4c3b2',
            hash_algorithm: 'SHA-256',
        },
        chain_data: {
            previous_snapshot_id: '00000000-0000-0000-0000-000000000001',
            is_genesis: false,
        },
        compliance_data: {
            asset_states: {
                transformers: [
                    { id: 'T1', status: 'operational' },
                    { id: 'T2', status: 'degraded', issue: 'High temperature' }
                ]
            },
            esp_config: { firewall_version: '2.4.1' },
            patch_metrics: { total_systems: 12, patched: 11, pending: 1 },
            active_mismatches: [{ asset_id: 'T2', type: 'PERFORMANCE_DEGRADATION' }]
        },
    }
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
        return NextResponse.json({ message: 'Dynamic export not available during static build' });
    }

    const { id } = await params;

    const exportData = MOCK_EXPORTS[id];

    if (!exportData) {
        return NextResponse.json(
            { error: 'Snapshot not found' },
            { status: 404 }
        );
    }

    return new NextResponse(JSON.stringify(exportData, null, 2), {
        status: 200,
        headers: {
            'Content-Type': 'application/json',
            'Content-Disposition': `attachment; filename="snapshot-${id}.json"`,
            'X-Data-Source': 'MOCK',
        },
    });
}
