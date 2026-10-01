'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth-context';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { POLL_METRICS_MS } from '@/lib/polling-config';

// ---------------------------------------------------------------------------
// API Helper — uses the ingestion proxy at /api/ingestion
// The proxy reads credentials from HTTP-only cookies — no client-side API key needed.
// ---------------------------------------------------------------------------

const INGESTION_API = '/api/ingestion';

/** Wrapper result that tracks whether data came from the API or demo fallback */
export interface CpResult<T> {
  data: T;
  isDemo: boolean;
}

function withQuery(endpoint: string, params: URLSearchParams): string {
  const query = params.toString();
  return query ? `${endpoint}?${query}` : endpoint;
}

async function cpFetch<T>(
  endpoint: string,
  options?: RequestInit,
): Promise<CpResult<T>> {
  const url = `${INGESTION_API}${endpoint}`;
  const response = await fetchWithCsrf(url, {
    ...options,
    credentials: 'include', // Send HTTP-only cookies to same-origin proxy
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    // Backend errors arrive as {detail} (FastAPI HTTPException) or as the
    // monolith envelope {error: {type, message}} — read both so callers'
    // toasts show the domain message instead of a bare "HTTP 400".
    throw new Error(error.detail || error?.error?.message || `HTTP ${response.status}`);
  }

  const data = await response.json();
  return { data, isDemo: false };
}

/** Unwrap CpResult for backward compat — hooks still return the data shape pages expect */
function unwrapCp<T>(result: CpResult<T>): T & { __isDemo?: boolean } {
  const data = result.data;
  if (data && typeof data === 'object') {
    (data as Record<string, unknown>).__isDemo = result.isDemo;
  }
  return data as T & { __isDemo?: boolean };
}

export interface RequestCase {
  request_case_id: string;
  signoffs?: { signoff_type: string; signed_by: string; signed_at: string; notes?: string }[];
  request_received_at: string;
  response_due_at: string;
  requesting_party: string;
  scope_type: string;
  scope_description: string | null;
  package_status: string;
  affected_lots: string[];
  affected_products: string[];
  affected_facilities: string[];
  total_records: number;
  gap_count: number;
  active_exception_count: number;
  hours_remaining?: number;
  is_overdue?: boolean;
  countdown_display?: string;
}

export function useRequestCases(tenantId: string) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['requests', tenantId],
    queryFn: () => cpFetch<{ cases: RequestCase[]; total: number }>(
      `/api/v1/requests?include_submitted=true`,
    ).then(unwrapCp),
    enabled: !!tenantId && isAuthenticated,
    refetchInterval: POLL_METRICS_MS,
  });
}

export function useCreateRequestCase(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ['requests', tenantId, 'create'],
    mutationFn: (data: {
      requesting_party: string;
      scope_type: string;
      scope_description?: string;
      affected_lots?: string[];
      affected_products?: string[];
      affected_facilities?: string[];
      response_hours?: number;
    }) => cpFetch(`/api/v1/requests`, {
      method: 'POST',
      body: JSON.stringify(data),
    }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests'] }),
  });
}

export function useApproveScope(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ['requests', tenantId, 'scope'],
    mutationFn: ({ requestCaseId }: { requestCaseId: string }) =>
      cpFetch(`/api/v1/requests/${requestCaseId}/scope`, {
        method: 'PATCH',
        body: JSON.stringify({}),
      }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests'] }),
  });
}

export function useCollectRecords(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ['requests', tenantId, 'collect'],
    mutationFn: ({ requestCaseId }: { requestCaseId: string }) =>
      cpFetch(`/api/v1/requests/${requestCaseId}/collect`, {
        method: 'POST',
      }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests'] }),
  });
}

export function useRunGapAnalysis(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ['requests', tenantId, 'gap-analysis'],
    mutationFn: ({ requestCaseId }: { requestCaseId: string }) =>
      cpFetch(`/api/v1/requests/${requestCaseId}/gap-analysis`, {
        method: 'POST',
      }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests'] }),
  });
}

export function useAssemblePackage(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ['requests', tenantId, 'assemble'],
    mutationFn: ({ requestCaseId, generatedBy }: { requestCaseId: string; generatedBy: string }) =>
      cpFetch(
        withQuery(
          `/api/v1/requests/${requestCaseId}/assemble`,
          new URLSearchParams({ generated_by: generatedBy }),
        ),
        {
        method: 'POST',
        },
      ).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests'] }),
  });
}

export function useSubmitPackage(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationKey: ['requests', tenantId, 'submit'],
    mutationFn: ({ requestCaseId, ...data }: {
      requestCaseId: string; submitted_to?: string; submitted_by: string;
      submission_method?: string; submission_notes?: string;
    }) => cpFetch(`/api/v1/requests/${requestCaseId}/submit`, {
      method: 'POST',
      body: JSON.stringify(data),
    }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests'] }),
  });
}

export function usePackageHistory(tenantId: string, requestCaseId: string) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['requests', tenantId, requestCaseId, 'packages'],
    queryFn: () => cpFetch<{ packages: Record<string, unknown>[]; total: number }>(
      `/api/v1/requests/${requestCaseId}/packages`
    ).then(unwrapCp),
    enabled: isAuthenticated && !!tenantId && !!requestCaseId,
  });
}

export function useRequestCase(tenantId: string, requestCaseId: string) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['requests', tenantId, requestCaseId, 'detail'],
    queryFn: () => cpFetch<RequestCase>(`/api/v1/requests/${encodeURIComponent(requestCaseId)}`).then(unwrapCp),
    enabled: !!tenantId && !!requestCaseId && isAuthenticated,
  });
}
export type SignoffType = 'scope_approval' | 'package_review' | 'final_approval' | 'submission_authorization';
export function useRequestSignoff(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ requestCaseId, ...body }: { requestCaseId: string; signoff_type: SignoffType; signed_by: string; notes: string }) =>
      cpFetch(`/api/v1/requests/${encodeURIComponent(requestCaseId)}/signoff`, { method: 'POST', body: JSON.stringify(body) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests', tenantId] }),
  });
}
