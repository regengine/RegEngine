/**
 * Mismatch Resolution Mutation
 * 
 * WRITE operation - mutation barrier enforced.
 * This is the ONLY write operation in Phase 1C.
 * 
 * CRITICAL: Mutation is gated by verification state.
 * Cannot execute when system integrity is compromised.
 */

import { useMutation, useQueryClient, UseMutationResult } from '@tanstack/react-query';
import { energyApi } from '../client';
import type { ResolveMismatchRequest, Mismatch } from '../../types/energy.types';
import { useVerifyLatestSnapshot } from '../queries/useVerification';

/**
 * Resolve a mismatch with attestation.
 * 
 * VERIFICATION GATE: This mutation will throw if verification status !== 'valid'.
 * Ensures UI cannot mutate when backend has declared truth compromised.
 * 
 * This mutation:
 * 1. Checks verification status (GATE - must be 'valid')
 * 2. Submits resolution + attestation to backend
 * 3. Backend creates snapshot (automatic)
 * 4. Invalidates mismatch queries to trigger refetch
 * 
 * @param substationId - Substation ID for verification check
 * @returns React Query mutation hook
 */
export const useResolveMismatch = (
    substationId: string
): UseMutationResult<
    Mismatch,
    Error,
    { mismatchId: string; request: ResolveMismatchRequest }
> => {
    const queryClient = useQueryClient();
    const { data: verificationData } = useVerifyLatestSnapshot(substationId);

    return useMutation({
        mutationFn: async ({ mismatchId, request }) => {
            // 🔒 VERIFICATION GATE (structural enforcement)
            // Only 'valid' status allows mutations - all other states blocked
            if (verificationData?.status !== 'valid') {
                throw new Error(
                    `INTEGRITY_VIOLATION: Mutations disabled until verification is healthy. ` +
                    `Current status: ${verificationData?.status || 'unknown'}. ` +
                    `System integrity must pass verification before attestations are allowed.`
                );
            }

            // Proceed with mutation (verification passed)
            const { data } = await energyApi.post<Mismatch>(
                `/energy/mismatches/${mismatchId}/resolve`,
                request
            );
            return data;
        },
        onSuccess: (data, variables) => {
            // Invalidate mismatch queries to trigger refetch
            queryClient.invalidateQueries({ queryKey: ['mismatches'] });
            queryClient.invalidateQueries({ queryKey: ['mismatch', variables.mismatchId] });

            // Invalidate snapshot queries (backend created new snapshot)
            queryClient.invalidateQueries({ queryKey: ['snapshots'] });

            // Invalidate verification (new snapshot = new verification state)
            queryClient.invalidateQueries({ queryKey: ['verification'] });
        }
    });
};
