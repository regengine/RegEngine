/**
 * Verification Queries
 * 
 * Read-only React Query hooks for snapshot integrity verification.
 * NO MUTATIONS - read barrier enforced.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { energyApi } from '../client';
import type { VerificationReport } from '../../types/energy.types';

/**
 * Verify latest snapshot for a substation.
 * 
 * Polls every 60 seconds to detect corruption.
 * 
 * @param substationId - Substation ID to verify
 * @returns React Query result with verification report
 */
export const useVerifyLatestSnapshot = (
    substationId: string | null
): UseQueryResult<VerificationReport> => {
    return useQuery({
        queryKey: ['verification', 'latest', substationId],
        queryFn: async () => {
            const { data } = await energyApi.get<VerificationReport>(
                `/energy/verify/latest/${substationId}`
            );
            return data;
        },
        enabled: !!substationId,
        staleTime: 0, // Always fresh
        refetchInterval: 60000, // Poll every 60s
        refetchIntervalInBackground: true, // Continue polling when tab inactive
        retry: 1 // Don't retry too aggressively on verification errors
    });
};

/**
 * Verify recent snapshots (background verification).
 * 
 * @param limit - Number of recent snapshots to verify (default: 100)
 * @returns React Query result with verification summary
 */
export const useVerifyRecentSnapshots = (
    limit: number = 100
): UseQueryResult<{
    total_checked: number;
    valid: number;
    corrupted: number;
    corrupted_snapshots: Array<{
        snapshot_id: string;
        substation_id: string;
        checks: any[];
    }>;
}> => {
    return useQuery({
        queryKey: ['verification', 'recent', limit],
        queryFn: async () => {
            const { data } = await energyApi.get('/energy/verify/recent', {
                params: { limit }
            });
            return data;
        },
        staleTime: 30000, // 30s cache
        refetchInterval: 120000 // Poll every 2min (less aggressive)
    });
};
