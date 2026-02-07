/**
 * Mismatch Queries
 * 
 * Read-only React Query hooks for compliance mismatches.
 * NO MUTATIONS - read barrier enforced.
 */

import { useQuery, UseQueryResult } from '@tanstack/react-query';
import { energyApi } from '../client';
import type {
    Mismatch,
    MismatchListResponse,
    MismatchFilters
} from '../../types/energy.types';

/**
 * Fetch list of mismatches for a substation.
 * 
 * @param filters - Substation ID + optional filters (status, severity)
 * @returns React Query result with mismatch list
 */
export const useMismatches = (
    filters: MismatchFilters
): UseQueryResult<MismatchListResponse> => {
    return useQuery({
        queryKey: ['mismatches', filters],
        queryFn: async () => {
            const { data } = await energyApi.get<MismatchListResponse>('/energy/mismatches', {
                params: filters
            });
            return data;
        },
        staleTime: 10000, // 10s cache (mismatches change more frequently)
        enabled: !!filters.substation_id
    });
};

/**
 * Fetch detailed mismatch by ID.
 * 
 * @param mismatchId - Mismatch UUID
 * @returns React Query result with mismatch details
 */
export const useMismatchDetail = (
    mismatchId: string | null
): UseQueryResult<Mismatch> => {
    return useQuery({
        queryKey: ['mismatch', mismatchId],
        queryFn: async () => {
            const { data } = await energyApi.get<Mismatch>(`/energy/mismatches/${mismatchId}`);
            return data;
        },
        enabled: !!mismatchId,
        staleTime: 10000
    });
};
