'use client';

/**
 * React Query hooks for FDA 24-Hour SLA Tracking.
 *
 * Connects to the ingestion service's /api/v1/sla/* endpoints
 * to manage FDA records requests and monitor compliance deadlines.
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
export function useSLARequests() {
  const { tenantId } = useTenant();
  return useApiQuery<FDARequestData[]>(
    ['sla-requests', tenantId],
    `/api/v1/sla/requests/${tenantId}`,
    { service: 'ingestion', refetchInterval: POLL_FAST, enabled: !!tenantId },
  );
}

/** SLA compliance dashboard metrics for the current tenant. */
export function useSLADashboard() {
  const { tenantId } = useTenant();
  return useApiQuery<SLADashboardData>(
    ['sla-dashboard', tenantId],
    `/api/v1/sla/dashboard/${tenantId}`,
    { service: 'ingestion', refetchInterval: POLL_FAST, enabled: !!tenantId },
  );
}

/** Active SLA alerts. Polls every 30s. */
export function useSLAAlerts() {
  const { tenantId } = useTenant();
  return useApiQuery<SLAAlertData[]>(
    ['sla-alerts', tenantId],
    `/api/v1/sla/alerts/${tenantId}`,
    { service: 'ingestion', refetchInterval: POLL_SLOW, enabled: !!tenantId },
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
export function useCompleteSLARequest(requestId: string) {
  return useApiMutate<FDARequestData, Record<string, never>>(
    `/api/v1/sla/requests/${requestId}/complete`,
    {
      service: 'ingestion',
      method: 'PATCH',
      invalidateKeys: [['sla-requests'], ['sla-dashboard']],
    },
  );
}
