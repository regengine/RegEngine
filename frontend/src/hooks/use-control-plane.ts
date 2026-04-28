'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth-context';
import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { POLL_CONTROL_PLANE_MS, POLL_DATA_MS, POLL_METRICS_MS } from '@/lib/polling-config';

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
    throw new Error(error.detail || `HTTP ${response.status}`);
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

// ---------------------------------------------------------------------------
// Exception Queue Hooks
// ---------------------------------------------------------------------------

export interface ExceptionCase {
  case_id: string;
  severity: string;
  status: string;
  linked_event_ids: string[];
  owner_user_id: string | null;
  due_date: string | null;
  source_supplier: string | null;
  source_facility_reference: string | null;
  rule_category: string | null;
  recommended_remediation: string | null;
  resolution_summary: string | null;
  created_at: string;
  updated_at: string;
}

export function useExceptions(
  tenantId: string,
  filters?: {
    severity?: string;
    status?: string;
    source_supplier?: string;
  }
) {
  const { apiKey } = useAuth();
  const params = new URLSearchParams({ tenant_id: tenantId });
  if (filters?.severity) params.set('severity', filters.severity);
  if (filters?.status) params.set('status', filters.status);
  if (filters?.source_supplier) params.set('source_supplier', filters.source_supplier);

  return useQuery({
    queryKey: ['exceptions', tenantId, filters],
    queryFn: () => cpFetch<{ cases: ExceptionCase[]; total: number }>(
      `/api/v1/exceptions?${params}`,
    ).then(unwrapCp),
    enabled: !!tenantId && !!apiKey,
    refetchInterval: POLL_CONTROL_PLANE_MS,
  });
}

export function useException(tenantId: string, caseId: string) {
  const { apiKey } = useAuth();
  return useQuery({
    queryKey: ['exceptions', tenantId, caseId],
    queryFn: () => cpFetch<ExceptionCase>(
      `/api/v1/exceptions/${caseId}?tenant_id=${tenantId}`
    ).then(unwrapCp),
    enabled: !!apiKey && !!tenantId && !!caseId,
  });
}

export function useBlockingExceptionCount(tenantId: string) {
  const { apiKey } = useAuth();
  return useQuery({
    queryKey: ['exceptions', 'blocking', tenantId],
    queryFn: () => cpFetch<{ blocking_count: number }>(
      `/api/v1/exceptions/stats/blocking?tenant_id=${tenantId}`,
    ).then(unwrapCp),
    enabled: !!tenantId && !!apiKey,
    refetchInterval: POLL_DATA_MS,
  });
}

export function useAssignException(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, ownerUserId }: { caseId: string; ownerUserId: string }) =>
      cpFetch(`/api/v1/exceptions/${caseId}/assign?tenant_id=${tenantId}`, {
        method: 'PATCH',
        body: JSON.stringify({ owner_user_id: ownerUserId }),
      }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exceptions'] }),
  });
}

export function useResolveException(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, resolutionSummary, resolvedBy }: {
      caseId: string; resolutionSummary: string; resolvedBy: string;
    }) => cpFetch(`/api/v1/exceptions/${caseId}/resolve?tenant_id=${tenantId}`, {
      method: 'PATCH',
      body: JSON.stringify({ resolution_summary: resolutionSummary, resolved_by: resolvedBy }),
    }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exceptions'] }),
  });
}

export function useWaiveException(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ caseId, waiverReason, waiverApprovedBy }: {
      caseId: string; waiverReason: string; waiverApprovedBy: string;
    }) => cpFetch(`/api/v1/exceptions/${caseId}/waive?tenant_id=${tenantId}`, {
      method: 'PATCH',
      body: JSON.stringify({ waiver_reason: waiverReason, waiver_approved_by: waiverApprovedBy }),
    }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['exceptions'] }),
  });
}

// ---------------------------------------------------------------------------
// Request-Response Workflow Hooks
// ---------------------------------------------------------------------------

export interface RequestCase {
  request_case_id: string;
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
  const { apiKey } = useAuth();
  return useQuery({
    queryKey: ['requests', tenantId],
    queryFn: () => cpFetch<{ cases: RequestCase[]; total: number }>(
      `/api/v1/requests?tenant_id=${tenantId}`,
    ).then(unwrapCp),
    enabled: !!tenantId && !!apiKey,
    refetchInterval: POLL_METRICS_MS,
  });
}

export function useCreateRequestCase(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (data: {
      requesting_party: string;
      scope_type: string;
      scope_description?: string;
      affected_lots?: string[];
      affected_products?: string[];
      affected_facilities?: string[];
      response_hours?: number;
    }) => cpFetch(`/api/v1/requests?tenant_id=${tenantId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests'] }),
  });
}

export function useAssemblePackage(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ requestCaseId, generatedBy }: { requestCaseId: string; generatedBy: string }) =>
      cpFetch(`/api/v1/requests/${requestCaseId}/assemble?tenant_id=${tenantId}&generated_by=${generatedBy}`, {
        method: 'POST',
      }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests'] }),
  });
}

export function useSubmitPackage(tenantId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ requestCaseId, ...data }: {
      requestCaseId: string; submitted_to?: string; submitted_by: string;
      submission_method?: string; submission_notes?: string;
    }) => cpFetch(`/api/v1/requests/${requestCaseId}/submit?tenant_id=${tenantId}`, {
      method: 'POST',
      body: JSON.stringify(data),
    }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['requests'] }),
  });
}

export function usePackageHistory(tenantId: string, requestCaseId: string) {
  const { apiKey } = useAuth();
  return useQuery({
    queryKey: ['requests', tenantId, requestCaseId, 'packages'],
    queryFn: () => cpFetch<{ packages: Record<string, unknown>[]; total: number }>(
      `/api/v1/requests/${requestCaseId}/packages?tenant_id=${tenantId}`
    ).then(unwrapCp),
    enabled: !!apiKey && !!tenantId && !!requestCaseId,
  });
}

// ---------------------------------------------------------------------------
// Rules Engine Hooks
// ---------------------------------------------------------------------------

export interface RuleDefinition {
  rule_id: string;
  title: string;
  severity: string;
  category: string;
  citation_reference: string | null;
  remediation_suggestion: string | null;
}

export interface RuleEvaluation {
  result: string;
  why_failed: string | null;
  rule_title: string;
  severity: string;
  citation_reference: string | null;
  remediation_suggestion: string | null;
  category: string;
}

export function useRules() {
  const { apiKey } = useAuth();
  return useQuery({
    queryKey: ['rules'],
    queryFn: () => cpFetch<{ rules: RuleDefinition[]; total: number }>(
      `/api/v1/rules`,
    ).then(unwrapCp),
    enabled: !!apiKey,
    staleTime: 5 * 60_000,
  });
}

export function useEventEvaluations(tenantId: string, eventId: string) {
  const { apiKey } = useAuth();
  return useQuery({
    queryKey: ['evaluations', tenantId, eventId],
    queryFn: () => cpFetch<{ evaluations: RuleEvaluation[]; total: number }>(
      `/api/v1/rules/evaluations/${eventId}?tenant_id=${tenantId}`
    ).then(unwrapCp),
    enabled: !!apiKey && !!tenantId && !!eventId,
  });
}

export function useSeedRules() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => cpFetch(`/api/v1/rules/seed`, { method: 'POST' }).then(r => r.data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['rules'] }),
  });
}

// ---------------------------------------------------------------------------
// Canonical Records Hooks
// ---------------------------------------------------------------------------

export interface CanonicalEvent {
  event_id: string;
  event_type: string;
  traceability_lot_code: string;
  product_reference: string | null;
  quantity: number;
  unit_of_measure: string;
  from_facility_reference: string | null;
  to_facility_reference: string | null;
  event_timestamp: string;
  source_system: string;
  status: string;
  confidence_score: number;
  schema_version: string;
  created_at: string;
}

export interface CanonicalEventDetail extends CanonicalEvent {
  raw_payload: Record<string, unknown>;
  normalized_payload: Record<string, unknown>;
  provenance_metadata: Record<string, unknown>;
  rule_evaluations: RuleEvaluation[];
  exception_cases: ExceptionCase[];
  amendment_chain?: Record<string, unknown>[];
}

export function useCanonicalEvents(
  tenantId: string,
  filters?: { tlc?: string; event_type?: string; source_system?: string; limit?: number }
) {
  const { apiKey } = useAuth();
  const params = new URLSearchParams({ tenant_id: tenantId });
  if (filters?.tlc) params.set('tlc', filters.tlc);
  if (filters?.event_type) params.set('event_type', filters.event_type);
  if (filters?.source_system) params.set('source_system', filters.source_system);
  if (filters?.limit) params.set('limit', String(filters.limit));

  return useQuery({
    queryKey: ['records', tenantId, filters],
    queryFn: () => cpFetch<{ events: CanonicalEvent[]; total: number }>(
      `/api/v1/records?${params}`,
    ).then(unwrapCp),
    enabled: !!tenantId && !!apiKey,
    refetchInterval: POLL_DATA_MS,
  });
}

export function useCanonicalEvent(tenantId: string, eventId: string) {
  const { apiKey } = useAuth();
  return useQuery({
    queryKey: ['records', tenantId, eventId],
    queryFn: () => cpFetch<CanonicalEventDetail>(
      `/api/v1/records/${eventId}?tenant_id=${tenantId}`
    ).then(unwrapCp),
    enabled: !!apiKey && !!tenantId && !!eventId,
  });
}

// ---------------------------------------------------------------------------
// Identity Resolution Hooks
// ---------------------------------------------------------------------------

export function useEntities(tenantId: string, entityType?: string) {
  const { apiKey } = useAuth();
  const params = new URLSearchParams({ tenant_id: tenantId });
  if (entityType) params.set('entity_type', entityType);

  return useQuery({
    queryKey: ['identity', tenantId, entityType],
    queryFn: () => cpFetch<{ entities: Record<string, unknown>[]; total: number }>(
      `/api/v1/identity/entities?${params}`,
    ).then(unwrapCp),
    enabled: !!tenantId && !!apiKey,
    staleTime: 60_000,
  });
}

export function useIdentityReviews(tenantId: string) {
  const { apiKey } = useAuth();
  return useQuery({
    queryKey: ['identity', 'reviews', tenantId],
    queryFn: () => cpFetch<{ reviews: Record<string, unknown>[]; total: number }>(
      `/api/v1/identity/reviews?tenant_id=${tenantId}`,
    ).then(unwrapCp),
    enabled: !!tenantId && !!apiKey,
    refetchInterval: POLL_DATA_MS,
  });
}
