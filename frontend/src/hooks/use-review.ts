'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { encodePathSegment } from '@/lib/api-path';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import type { ReviewItem } from '@/types/review';

async function reviewFetch<T>(path: string, options: RequestInit = {}): Promise<T> {
    const response = await fetchWithCsrf(path, {
        ...options,
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => null);
        const message =
            errorBody && typeof errorBody.error === 'string'
                ? errorBody.error
                : `Review request failed: ${response.status} ${response.statusText}`;
        throw new Error(message);
    }

    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('application/json')) {
        return undefined as T;
    }

    return response.json() as Promise<T>;
}

export function useReviewItems(enabled: boolean = true) {
    return useQuery({
        queryKey: ['admin', 'review', 'PENDING'],
        queryFn: () => reviewFetch<ReviewItem[]>('/api/review/items'),
        enabled,
        staleTime: 10 * 1000,
    });
}

export function useApproveReviewItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (itemId: string) =>
            reviewFetch<void>(`/api/review/${encodePathSegment(itemId)}/approve`, {
                method: 'POST',
                body: JSON.stringify({}),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'review'] });
        },
    });
}

export function useRejectReviewItem() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (itemId: string) =>
            reviewFetch<void>(`/api/review/${encodePathSegment(itemId)}/reject`, {
                method: 'POST',
                body: JSON.stringify({}),
            }),
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: ['admin', 'review'] });
        },
    });
}
