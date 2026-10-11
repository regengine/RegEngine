'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/lib/auth-context';
import type {
  TraceResult,
  MassBalanceResult,
  RecallDrill,
  RecallReadiness,
  FSMADashboard,
  CreateRecallDrillRequest,
  RecallSchedule,
  KDEQualityMetrics,
} from '@/types/fsma';

const GRAPH_API_BASE = typeof window !== 'undefined'
  ? '/api/fsma'  // Browser: use Next.js API proxy
  : (process.env.NEXT_PUBLIC_GRAPH_API_URL
      || (process.env.VERCEL ? '' : 'http://localhost:8200/v1/fsma'));

// Helper to make authenticated API calls.
// Credentials are in HTTP-only cookies — the proxy injects them server-side.
async function fsmaFetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const url = `${GRAPH_API_BASE}${endpoint}`;

  const response = await fetchWithCsrf(url, {
    ...options,
    credentials: 'include', // Send HTTP-only cookies
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Request failed' }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// ============== Traceability Hooks ==============

export function useForwardTrace(tlc: string, enabled = true) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'trace', 'forward', tlc],
    queryFn: () => fsmaFetch<TraceResult>(`/traceability/trace/forward/${encodeURIComponent(tlc)}`),
    enabled: enabled && !!tlc && isAuthenticated,
    staleTime: 30 * 1000, // 30 seconds
  });
}

export function useBackwardTrace(tlc: string, enabled = true) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'trace', 'backward', tlc],
    queryFn: () => fsmaFetch<TraceResult>(`/traceability/trace/backward/${encodeURIComponent(tlc)}`),
    enabled: enabled && !!tlc && isAuthenticated,
    staleTime: 30 * 1000,
  });
}

export function useTimeline(tlc: string, enabled = true) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'timeline', tlc],
    queryFn: () => fsmaFetch<{ events: TraceResult['events'] }>(`/traceability/timeline/${encodeURIComponent(tlc)}`),
    enabled: enabled && !!tlc && isAuthenticated,
    staleTime: 30 * 1000,
  });
}

export function useExportTrace() {
  return useMutation({
    mutationFn: async ({ tlc, direction }: { tlc: string; direction: 'forward' | 'backward' }) => {
      const response = await fetchWithCsrf(
        `${GRAPH_API_BASE}/export/trace/${encodeURIComponent(tlc)}?direction=${direction}`,
        {
          credentials: 'include',
        }
      );
      if (!response.ok) throw new Error('Export failed');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `trace_${direction}_${tlc}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    },
  });
}


export function useExportRecallContacts() {
  return useMutation({
    mutationFn: async (tlc: string) => {
      const response = await fetchWithCsrf(
        `${GRAPH_API_BASE}/export/recall-contacts/${encodeURIComponent(tlc)}`,
        {
          credentials: 'include',
        }
      );
      if (!response.ok) throw new Error('Export failed');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `recall_contacts_${tlc}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    },
  });
}

// ============== Mass Balance Hooks ==============

export function useMassBalance(tlc: string, enabled = true) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'mass-balance', tlc],
    queryFn: () => fsmaFetch<MassBalanceResult>(`/science/mass-balance/${encodeURIComponent(tlc)}`),
    enabled: enabled && !!tlc && isAuthenticated,
    staleTime: 60 * 1000,
  });
}

// ============== Recall Drill Hooks ==============

export function useRecallDrills(limit = 10) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'recall', 'history', limit],
    queryFn: () => fsmaFetch<{ drills: RecallDrill[] }>(`/recall/history?limit=${limit}`),
    enabled: isAuthenticated,
    refetchInterval: 10 * 1000, // Refresh every 10 seconds for active drills
  });
}

export function useRecallDrill(drillId: string, enabled = true) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'recall', 'drill', drillId],
    queryFn: () => fsmaFetch<RecallDrill>(`/recall/drill/${encodeURIComponent(drillId)}`),
    enabled: enabled && !!drillId && isAuthenticated,
    refetchInterval: 5 * 1000, // Refresh every 5 seconds for active drills
  });
}

export function useCreateRecallDrill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateRecallDrillRequest) =>
      fsmaFetch<RecallDrill>('/recall/drill', {
        method: 'POST',
        body: JSON.stringify(request),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fsma', 'recall'] });
    },
  });
}

export function useCancelRecallDrill() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (drillId: string) =>
      fsmaFetch<{ success: boolean }>(`/recall/drill/${encodeURIComponent(drillId)}`, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fsma', 'recall'] });
    },
  });
}

export function useRecallReadiness() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'recall', 'readiness'],
    queryFn: () => fsmaFetch<RecallReadiness>('/recall/readiness'),
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useRecallSLA() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'recall', 'sla'],
    queryFn: () => fsmaFetch<{ sla_percent: number; avg_response_hours: number }>('/recall/sla'),
    enabled: isAuthenticated,
    staleTime: 60 * 1000,
  });
}

// ============== Schedule Hooks ==============

export function useRecallSchedules() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'recall', 'schedules'],
    queryFn: () => fsmaFetch<{ schedules: RecallSchedule[] }>('/recall/schedules'),
    enabled: isAuthenticated,
    staleTime: 60 * 1000,
  });
}

export function useCreateRecallSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (schedule: Omit<RecallSchedule, 'id' | 'last_run'>) =>
      fsmaFetch<RecallSchedule>('/recall/schedule', {
        method: 'POST',
        body: JSON.stringify(schedule),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fsma', 'recall', 'schedules'] });
    },
  });
}

// ============== Data Quality Hooks ==============

// #2980: the four `drift/*` hooks (useDriftAlerts, useDriftHealth,
// useSupplierHealth, useAcknowledgeAlert) were removed. No backend has ever
// registered a drift router, so they 404'd in every environment under every
// flag — see src/__tests__/hooks/use-fsma-unbacked-endpoints.test.ts, which
// pins both the wizard/* and drift/* surfaces as absent. DriftAlertsWidget
// and /admin/alerts, their only consumers, were deleted with them.

export function useKDEQuality() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'metrics', 'quality'],
    queryFn: () => fsmaFetch<KDEQualityMetrics>('/metrics/quality'),
    enabled: isAuthenticated,
    staleTime: 60 * 1000,
  });
}

// ============== Dashboard Hooks ==============

export function useFSMADashboard() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'dashboard'],
    queryFn: () => fsmaFetch<FSMADashboard>('/metrics/dashboard'),
    enabled: isAuthenticated,
    refetchInterval: 30 * 1000,
  });
}

export function useFSMAHealth() {
  return useQuery({
    queryKey: ['fsma', 'health'],
    queryFn: async () => {
      const response = await fetchWithCsrf(`${GRAPH_API_BASE}/metrics/health`);
      if (!response.ok) throw new Error('FSMA service unhealthy');
      return response.json();
    },
    refetchInterval: 30 * 1000,
  });
}

// ============== Gaps & Orphans ==============

export function useTraceGaps(limit = 50) {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'gaps', limit],
    queryFn: () => fsmaFetch<{ gaps: Array<{ event_id: string; missing_kdes: string[]; facility: string }> }>(
      `/gaps?limit=${limit}`
    ),
    enabled: isAuthenticated,
    staleTime: 2 * 60 * 1000,
  });
}

export function useOrphanedLots() {
  const { isAuthenticated } = useAuth();
  return useQuery({
    queryKey: ['fsma', 'gaps', 'orphans'],
    queryFn: () => fsmaFetch<{ orphans: Array<{ tlc: string; last_event: string; days_stagnant: number }> }>(
      '/gaps/orphans'
    ),
    enabled: isAuthenticated,
    staleTime: 5 * 60 * 1000,
  });
}

export function useExportComplianceReport() {
  return useMutation({
    mutationFn: async () => {
      const response = await fetchWithCsrf(`${GRAPH_API_BASE}/export/gaps`, {
        credentials: 'include',
      });
      if (!response.ok) throw new Error('Export failed');
      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `fsma_compliance_gaps_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    },
  });
}

// ─── Phase 29: Compliance Score ───────────────────────────────────────────────

export interface ComplianceScoreResult {
  tenant_id: string;
  overall_score: number | null;
  obligation_coverage: number | null;
  control_effectiveness: number | null;
  evidence_freshness: number | null;
  total_obligations: number;
  controls_mapped: number;
  evidence_items: number;
  is_demo: boolean;
  generated_at: string;
}

/**
 * Fetch the tenant-scoped FSMA compliance score.
 * Returns null measurements when the graph has no tenant data; outages raise an error.
 */
export function useComplianceScore() {
  const { isAuthenticated } = useAuth();
  return useQuery<ComplianceScoreResult>({
    queryKey: ['fsma', 'compliance-score'],
    queryFn: () => fsmaFetch<ComplianceScoreResult>('/compliance/score'),
    enabled: isAuthenticated,
    staleTime: 60_000, // 60s — score is expensive to compute
    retry: 1,
  });
}
