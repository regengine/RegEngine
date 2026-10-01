'use client';

/**
 * React Query hooks for FDA 24-hour response-objective tracking.
 *
 * Connects to the ingestion service's /api/v1/sla/* endpoints
 * to manage FDA records requests and monitor response deadlines.
 */

import { useApiQuery, useApiMutate } from '@/hooks/use-api-query';
import { useTenant } from '@/lib/tenant-context';

// ---------------------------------------------------------------------------
// Types matching backend Pydantic models (sla_tracking.py)
// ---------------------------------------------------------------------------

export type RequestType = 'records_request' | 'inspection' | 'recall';
export type RequestStatus = 'open' | 'in_progress' | 'completed' | 'overdue';

export interface FDARequestData {
  id: string;
  tenant_id: string;
  request_type: RequestType;
  requested_at: string;
  deadline_at: string;
  status: RequestStatus;
  completed_at: string | null;
  export_ids: string[];
  notes: string | null;
  time_remaining_seconds: number | null;
  response_hours: number | null;
}

export interface SLADashboardData {
  tenant_id: string;
  open_requests: number;
  overdue_requests: number;
  avg_response_hours: number | null;
  compliance_rate_pct: number | null;
  requests: FDARequestData[];
}

export interface SLAAlertData {
  id: string;
  tenant_id: string;
  request_id: string;
  alert_type: 'deadline_approaching' | 'overdue' | 'completed';
  message: string;
  created_at: string;
  acknowledged: boolean;
}

export interface CreateRequestInput {
  tenant_id: string;
  request_type?: RequestType;
  notes?: string;
}

// ---------------------------------------------------------------------------
// Hooks
// ---------------------------------------------------------------------------

const POLL_FAST = 10_000;  // 10 seconds for active requests
const POLL_SLOW = 30_000;  // 30 seconds for alerts

/** List all SLA requests for the current tenant. Polls every 10s. */
export interface SLARequestsEnvelope { tenant_id: string; total: number; skip: number; limit: number; requests: FDARequestData[] }
export interface SLAAlertsEnvelope { tenant_id: string; total: number; skip: number; limit: number; alerts: SLAAlertData[] }
export function decodeSLARequests(value: unknown): SLARequestsEnvelope {
  const data = value as SLARequestsEnvelope;
  if (!data || !Array.isArray(data.requests) || !Number.isInteger(data.total) || data.total < 0 || !Number.isInteger(data.skip) || data.skip < 0 || !Number.isInteger(data.limit) || data.limit < 1 || data.requests.some(row => !row || typeof row.id !== 'string' || !['open', 'in_progress', 'completed', 'overdue'].includes(row.status) || !Array.isArray(row.export_ids) || !Number.isFinite(Date.parse(row.requested_at)) || !Number.isFinite(Date.parse(row.deadline_at)))) throw new Error('Invalid SLA requests response. Retry loading requests.');
  return data;
}
export function decodeSLAAlerts(value: unknown): SLAAlertsEnvelope {
  const data = value as SLAAlertsEnvelope;
  if (!data || !Array.isArray(data.alerts) || data.alerts.some(row => !row || typeof row.id !== 'string' || typeof row.message !== 'string')) throw new Error('Invalid SLA alerts response.');
  return data;
}
export function useSLARequests(skip = 0) {
  const { tenantId } = useTenant();
  return useApiQuery<SLARequestsEnvelope>(
    ['sla-requests', tenantId, skip],
    `/api/v1/sla/requests/${tenantId}?skip=${skip}&limit=50`,
    { service: 'ingestion', refetchInterval: POLL_FAST, enabled: !!tenantId, select: decodeSLARequests },
  );
}

/** Response-objective dashboard metrics for the current tenant. */
export function useSLADashboard() {
  const { tenantId } = useTenant();
  return useApiQuery<SLADashboardData>(
    ['sla-dashboard', tenantId],
    `/api/v1/sla/dashboard/${tenantId}`,
    { service: 'ingestion', refetchInterval: POLL_FAST, enabled: !!tenantId },
  );
}

/** Active SLA alerts. Polls every 30s. */
export function useSLAAlerts(skip = 0) {
  const { tenantId } = useTenant();
  return useApiQuery<SLAAlertsEnvelope>(
    ['sla-alerts', tenantId, skip],
    `/api/v1/sla/alerts/${tenantId}?skip=${skip}&limit=50`,
    { service: 'ingestion', refetchInterval: POLL_SLOW, enabled: !!tenantId, select: decodeSLAAlerts },
  );
}

/** Create a new FDA records request (starts 24-hour clock). */
export function useCreateSLARequest() {
  return useApiMutate<FDARequestData, CreateRequestInput>(
    '/api/v1/sla/requests',
    {
      service: 'ingestion',
      method: 'POST',
      invalidateKeys: [['sla-requests'], ['sla-dashboard']],
    },
  );
}

/** Mark a request as completed. */
export interface CompletionEvidence { export_hash: string; start_date: string; end_date: string; completion_notes: string; acknowledged: boolean }
export function useCompleteSLARequest(requestId: string) {
  return useApiMutate<{ status: string; request: FDARequestData; met_sla: boolean }, CompletionEvidence>(
    `/api/v1/sla/requests/${requestId}/complete`,
    {
      service: 'ingestion',
      method: 'PATCH',
      invalidateKeys: [['sla-requests'], ['sla-dashboard']],
    },
  );
}
