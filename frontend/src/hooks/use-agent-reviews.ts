'use client';

import { useQuery } from '@tanstack/react-query';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import type { AgentReviewItemsQuery, AgentReviewListResponse } from '@/types/agent-review';

function appendIfPresent(params: URLSearchParams, key: string, value: string | number | undefined) {
    if (value === undefined || value === null || value === '') return;
    params.set(key, String(value));
}

export function buildAgentReviewItemsUrl(query: AgentReviewItemsQuery = {}): string {
    const params = new URLSearchParams();

    appendIfPresent(params, 'tenant_id', query.tenantId?.trim());
    appendIfPresent(params, 'ingestion_run_id', query.ingestionRunId?.trim());

    if (query.reviewStatus && query.reviewStatus !== 'all') {
        params.set('review_status', query.reviewStatus);
    }
    if (query.artifactType && query.artifactType !== 'all') {
        params.set('artifact_type', query.artifactType);
    }

    appendIfPresent(params, 'created_after', query.createdAfter);
    appendIfPresent(params, 'created_before', query.createdBefore);
    appendIfPresent(params, 'limit', query.limit ?? 50);
    appendIfPresent(params, 'offset', query.offset ?? 0);

    const queryString = params.toString();
    return `/api/admin/v1/agent-reviews/items${queryString ? `?${queryString}` : ''}`;
}

export async function fetchAgentReviewItems(query: AgentReviewItemsQuery = {}): Promise<AgentReviewListResponse> {
    const response = await fetchWithCsrf(buildAgentReviewItemsUrl(query), {
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
        },
    });

    if (!response.ok) {
        const errorBody = await response.json().catch(() => null);
        const message =
            typeof errorBody?.error === 'string'
                ? errorBody.error
                : typeof errorBody?.detail === 'string'
                    ? errorBody.detail
                    : `Agent review request failed: ${response.status} ${response.statusText}`;
        throw new Error(message);
    }

    return response.json() as Promise<AgentReviewListResponse>;
}

export function useAgentReviewItems(query: AgentReviewItemsQuery, enabled = true) {
    return useQuery({
        queryKey: ['agent-reviews', query],
        queryFn: () => fetchAgentReviewItems(query),
        enabled,
        staleTime: 15 * 1000,
    });
}
