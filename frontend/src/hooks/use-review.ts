'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { ReviewItem } from '@/types/review';

export function useReviewItems(adminKey: string, status: string = 'PENDING') {
    return useQuery({
        queryKey: ['admin', 'review', status],
        queryFn: () => apiClient.getReviewItems(adminKey, status),
        enabled: !!adminKey,
        staleTime: 10 * 1000, // 10 seconds
    });
}

export function useApproveReviewItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ adminKey, itemId }: { adminKey: string; itemId: string }) =>
            apiClient.approveReviewItem(adminKey, itemId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'review'] });
        },
    });
}

export function useRejectReviewItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ adminKey, itemId }: { adminKey: string; itemId: string }) =>
            apiClient.rejectReviewItem(adminKey, itemId),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'review'] });
        },
    });
}
