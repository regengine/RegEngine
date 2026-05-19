'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import type {
    AgentReviewDecisionInput,
    AgentReviewDecisionResponse,
    AgentReviewDecisionStatus,
    AgentReviewItemsQuery,
    AgentReviewListResponse,
} from '@/types/agent-review';

export const AGENT_REVIEW_QUERY_KEY = ['agent-reviews'] as const;
const AGENT_REVIEW_ITEMS_PATH = '/api/admin/v1/agent-reviews/items';

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
    return `${AGENT_REVIEW_ITEMS_PATH}${queryString ? `?${queryString}` : ''}`;
}

export function buildAgentReviewDecisionUrl(artifactId: string): string {
    return `${AGENT_REVIEW_ITEMS_PATH}/${encodeURIComponent(artifactId)}/review`;
}

async function parseAgentReviewError(response: Response): Promise<Error> {
    const errorBody = await response.json().catch(() => null);
    const message =
        typeof errorBody?.error === 'string'
            ? errorBody.error
            : typeof errorBody?.detail === 'string'
                ? errorBody.detail
                : `Agent review request failed: ${response.status} ${response.statusText}`;
    return new Error(message);
}

async function readJsonResponse<T>(response: Response): Promise<T | null> {
    const contentType = response.headers.get('content-type') ?? '';
    if (!contentType.includes('application/json')) return null;
    return response.json() as Promise<T>;
}

export async function fetchAgentReviewItems(query: AgentReviewItemsQuery = {}): Promise<AgentReviewListResponse> {
    const response = await fetchWithCsrf(buildAgentReviewItemsUrl(query), {
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
        },
    });

    if (!response.ok) {
        throw await parseAgentReviewError(response);
    }

    return response.json() as Promise<AgentReviewListResponse>;
}

type RawAgentReviewDecisionResponse = Partial<AgentReviewDecisionResponse> & {
    status?: AgentReviewDecisionStatus;
};

function normalizeAgentReviewDecisionResponse(
    artifactId: string,
    status: AgentReviewDecisionStatus,
    payload: RawAgentReviewDecisionResponse | null,
): AgentReviewDecisionResponse {
    return {
        artifact_id: payload?.artifact_id ?? artifactId,
        review_id: payload?.review_id ?? null,
        review_status: payload?.review_status ?? payload?.status ?? status,
        reviewed_by: payload?.reviewed_by ?? null,
        reviewed_at: payload?.reviewed_at ?? null,
    };
}

export async function submitAgentReviewDecision({
    artifactId,
    ...request
}: AgentReviewDecisionInput): Promise<AgentReviewDecisionResponse> {
    const response = await fetchWithCsrf(buildAgentReviewDecisionUrl(artifactId), {
        method: 'POST',
        credentials: 'include',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(request),
    });

    if (!response.ok) {
        throw await parseAgentReviewError(response);
    }

    const payload = await readJsonResponse<RawAgentReviewDecisionResponse>(response);
    return normalizeAgentReviewDecisionResponse(artifactId, request.status, payload);
}

export function useAgentReviewItems(query: AgentReviewItemsQuery, enabled = true) {
    return useQuery({
        queryKey: [...AGENT_REVIEW_QUERY_KEY, query],
        queryFn: () => fetchAgentReviewItems(query),
        enabled,
        staleTime: 15 * 1000,
    });
}

export function useAgentReviewDecision() {
    const queryClient = useQueryClient();

    return useMutation({
        mutationFn: submitAgentReviewDecision,
        onSuccess: () => {
            queryClient.invalidateQueries({ queryKey: AGENT_REVIEW_QUERY_KEY });
        },
    });
}
