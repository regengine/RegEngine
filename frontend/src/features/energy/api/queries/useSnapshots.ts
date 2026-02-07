/**
 * Snapshot Queries
 * 
 * Read-only React Query hooks for compliance snapshots.
 * NO MUTATIONS - read barrier enforced.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { energyApi } from '../client';
import type {
    ComplianceSnapshot,
    SnapshotListResponse,
    SnapshotFilters
} from '../../types/energy.types';

/**
 * Fetch paginated list of snapshots for a substation.
 * 
 * @param filters - Substation ID + optional filters (time range, status, pagination)
 * @returns React Query result with snapshot list
 */
export const useSnapshots = (
    filters: SnapshotFilters
): UseQueryResult<SnapshotListResponse> => {
    return useQuery({
        queryKey: ['snapshots', filters],
        queryFn: async () => {
            const { data } = await energyApi.get<SnapshotListResponse>('/energy/snapshots', {
                params: filters
            });
            return data;
        },
        staleTime: 30000, // 30s cache
        enabled: !!filters.substation_id // Only fetch if substation ID provided
    });
};

/**
 * Fetch detailed snapshot by ID.
 * 
 * @param snapshotId - Snapshot UUID
 * @param includeAssetDetails - Load heavy JSONB fields (default: false)
 * @param includeEspConfig - Load ESP config JSONB (default: false)
 * @returns React Query result with snapshot details
 */
export const useSnapshotDetail = (
    snapshotId: string | null,
    options?: {
        includeAssetDetails?: boolean;
        includeEspConfig?: boolean;
    }
): UseQueryResult<ComplianceSnapshot> => {
    return useQuery({
        queryKey: ['snapshot', snapshotId, options],
        queryFn: async () => {
            const { data } = await energyApi.get<ComplianceSnapshot>(
                `/energy/snapshots/${snapshotId}`,
                {
                    params: {
                        include_asset_details: options?.includeAssetDetails ?? false,
                        include_esp_config: options?.includeEspConfig ?? false
                    }
                }
            );
            return data;
        },
        enabled: !!snapshotId, // Only fetch if ID provided
        staleTime: 60000 // 1min cache (snapshots are immutable)
    });
};

/**
 * Export snapshots to CSV (streaming).
 * 
 * This does NOT use React Query - it triggers direct download.
 * 
 * @param filters - Substation ID + time range
 * @returns Promise that triggers download
 */
export const exportSnapshotsCSV = async (
    filters: Required<Pick<SnapshotFilters, 'substation_id' | 'from_time' | 'to_time'>>
): Promise<void> => {
    const response = await energyApi.get('/energy/snapshots/export', {
        params: {
            substation_id: filters.substation_id,
            from_time: filters.from_time,
            to_time: filters.to_time,
            format: 'csv'
        },
        responseType: 'blob'
    });

    // Trigger browser download
    const url = window.URL.createObjectURL(new Blob([response.data]));
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute(
        'download',
        `snapshots_${filters.substation_id}_${new Date().toISOString().split('T')[0]}.csv`
    );
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
};
