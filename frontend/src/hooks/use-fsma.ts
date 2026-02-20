'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import type {
  TraceResult,
  MassBalanceResult,
  RecallDrill,
  RecallReadiness,
  FSMADashboard,
  DriftAlert,
  SupplierHealth,
  CreateRecallDrillRequest,
  RecallSchedule,
  KDEQualityMetrics,
  FTLCategoriesResponse,
  WizardApplicabilityResult,
  WizardExemptionResult,
} from '@/types/fsma';

const GRAPH_API_BASE = typeof window !== 'undefined'
  ? '/api/fsma'  // Browser: use Next.js API proxy
  : (process.env.NEXT_PUBLIC_GRAPH_API_URL || 'http://localhost:8200/v1/fsma');

// Helper to make authenticated API calls
async function fsmaFetch<T>(
  endpoint: string,
  apiKey: string,
  options?: RequestInit
): Promise<T> {
  // For browser, GRAPH_API_BASE is '/api/fsma' and endpoint starts with '/'
  // For server, GRAPH_API_BASE is 'http://localhost:8200/v1/fsma'
  // The endpoint already starts with '/', so we just concatenate
  const url = typeof window !== 'undefined'
    ? `${GRAPH_API_BASE}${endpoint}`  // Browser: /api/fsma/dashboard
    : `${GRAPH_API_BASE}${endpoint}`; // Server: http://localhost:8200/v1/fsma/dashboard

  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-RegEngine-API-Key': apiKey,
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

export function useForwardTrace(tlc: string, apiKey: string, enabled = true) {
  return useQuery({
    queryKey: ['fsma', 'trace', 'forward', tlc],
    queryFn: () => fsmaFetch<TraceResult>(`/traceability/trace/forward/${encodeURIComponent(tlc)}`, apiKey),
    enabled: enabled && !!tlc && !!apiKey,
    staleTime: 30 * 1000, // 30 seconds
  });
}

export function useBackwardTrace(tlc: string, apiKey: string, enabled = true) {
  return useQuery({
    queryKey: ['fsma', 'trace', 'backward', tlc],
    queryFn: () => fsmaFetch<TraceResult>(`/traceability/trace/backward/${encodeURIComponent(tlc)}`, apiKey),
    enabled: enabled && !!tlc && !!apiKey,
    staleTime: 30 * 1000,
  });
}

export function useTimeline(tlc: string, apiKey: string, enabled = true) {
  return useQuery({
    queryKey: ['fsma', 'timeline', tlc],
    queryFn: () => fsmaFetch<{ events: TraceResult['events'] }>(`/traceability/timeline/${encodeURIComponent(tlc)}`, apiKey),
    enabled: enabled && !!tlc && !!apiKey,
    staleTime: 30 * 1000,
  });
}

export function useExportTrace(apiKey: string) {
  return useMutation({
    mutationFn: async ({ tlc, direction }: { tlc: string; direction: 'forward' | 'backward' }) => {
      const response = await fetch(
        `${GRAPH_API_BASE}/export/trace/${encodeURIComponent(tlc)}?direction=${direction}`,
        {
          headers: {
            'X-RegEngine-API-Key': apiKey,
          },
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


export function useExportRecallContacts(apiKey: string) {
  return useMutation({
    mutationFn: async (tlc: string) => {
      const response = await fetch(
        `${GRAPH_API_BASE}/export/recall-contacts/${encodeURIComponent(tlc)}`,
        {
          headers: {
            'X-RegEngine-API-Key': apiKey,
          },
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

export function useMassBalance(tlc: string, apiKey: string, enabled = true) {
  return useQuery({
    queryKey: ['fsma', 'mass-balance', tlc],
    queryFn: () => fsmaFetch<MassBalanceResult>(`/science/mass-balance/${encodeURIComponent(tlc)}`, apiKey),
    enabled: enabled && !!tlc && !!apiKey,
    staleTime: 60 * 1000,
  });
}

// ============== Recall Drill Hooks ==============

export function useRecallDrills(apiKey: string, limit = 10) {
  return useQuery({
    queryKey: ['fsma', 'recall', 'history', limit],
    queryFn: () => fsmaFetch<{ drills: RecallDrill[] }>(`/recall/history?limit=${limit}`, apiKey),
    enabled: !!apiKey,
    refetchInterval: 10 * 1000, // Refresh every 10 seconds for active drills
  });
}

export function useRecallDrill(drillId: string, apiKey: string, enabled = true) {
  return useQuery({
    queryKey: ['fsma', 'recall', 'drill', drillId],
    queryFn: () => fsmaFetch<RecallDrill>(`/recall/drill/${drillId}`, apiKey),
    enabled: enabled && !!drillId && !!apiKey,
    refetchInterval: 5 * 1000, // Refresh every 5 seconds for active drills
  });
}

export function useCreateRecallDrill(apiKey: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (request: CreateRecallDrillRequest) =>
      fsmaFetch<RecallDrill>('/recall/drill', apiKey, {
        method: 'POST',
        body: JSON.stringify(request),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fsma', 'recall'] });
    },
  });
}

export function useCancelRecallDrill(apiKey: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (drillId: string) =>
      fsmaFetch<{ success: boolean }>(`/recall/drill/${drillId}`, apiKey, {
        method: 'DELETE',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fsma', 'recall'] });
    },
  });
}

export function useRecallReadiness(apiKey: string) {
  return useQuery({
    queryKey: ['fsma', 'recall', 'readiness'],
    queryFn: () => fsmaFetch<RecallReadiness>('/recall/readiness', apiKey),
    enabled: !!apiKey,
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useRecallSLA(apiKey: string) {
  return useQuery({
    queryKey: ['fsma', 'recall', 'sla'],
    queryFn: () => fsmaFetch<{ sla_percent: number; avg_response_hours: number }>('/recall/sla', apiKey),
    enabled: !!apiKey,
    staleTime: 60 * 1000,
  });
}

// ============== Schedule Hooks ==============

export function useRecallSchedules(apiKey: string) {
  return useQuery({
    queryKey: ['fsma', 'recall', 'schedules'],
    queryFn: () => fsmaFetch<{ schedules: RecallSchedule[] }>('/recall/schedules', apiKey),
    enabled: !!apiKey,
    staleTime: 60 * 1000,
  });
}

export function useCreateRecallSchedule(apiKey: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (schedule: Omit<RecallSchedule, 'id' | 'last_run'>) =>
      fsmaFetch<RecallSchedule>('/recall/schedule', apiKey, {
        method: 'POST',
        body: JSON.stringify(schedule),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fsma', 'recall', 'schedules'] });
    },
  });
}

// ============== Data Quality Hooks ==============

export function useDriftAlerts(apiKey: string, limit = 20) {
  return useQuery({
    queryKey: ['fsma', 'drift', 'alerts', limit],
    queryFn: () => fsmaFetch<{ alerts: DriftAlert[] }>(`/drift/alerts?limit=${limit}`, apiKey),
    enabled: !!apiKey,
    refetchInterval: 30 * 1000,
  });
}

export function useDriftHealth(apiKey: string) {
  return useQuery({
    queryKey: ['fsma', 'drift', 'health'],
    queryFn: () => fsmaFetch<{
      trace_completeness_rate: number;
      average_ingest_latency_ms: number;
      error_rate_percent: number;
      status: string;
      alerts: Array<{
        id: string;
        severity: string;
        metric: string;
        current_value?: number;
        threshold?: number;
        message: string;
        timestamp: string;
        source: string;
      }>;
    }>('/drift/health', apiKey),
    enabled: !!apiKey,
    refetchInterval: 30 * 1000,
  });
}

export function useSupplierHealth(apiKey: string) {
  return useQuery({
    queryKey: ['fsma', 'drift', 'suppliers'],
    queryFn: () => fsmaFetch<{ suppliers: SupplierHealth[] }>('/drift/suppliers', apiKey),
    enabled: !!apiKey,
    staleTime: 2 * 60 * 1000,
  });
}

export function useKDEQuality(apiKey: string) {
  return useQuery({
    queryKey: ['fsma', 'metrics', 'quality'],
    queryFn: () => fsmaFetch<KDEQualityMetrics>('/metrics/quality', apiKey),
    enabled: !!apiKey,
    staleTime: 60 * 1000,
  });
}

export function useAcknowledgeAlert(apiKey: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (alertId: string) =>
      fsmaFetch<{ success: boolean }>(`/drift/alerts/${alertId}/acknowledge`, apiKey, {
        method: 'POST',
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['fsma', 'drift', 'alerts'] });
    },
  });
}

// ============== Dashboard Hooks ==============

export function useFSMADashboard(apiKey: string) {
  return useQuery({
    queryKey: ['fsma', 'dashboard'],
    queryFn: () => fsmaFetch<FSMADashboard>('/metrics/dashboard', apiKey),
    enabled: !!apiKey,
    refetchInterval: 30 * 1000,
  });
}

export function useFSMAHealth() {
  return useQuery({
    queryKey: ['fsma', 'health'],
    queryFn: async () => {
      const response = await fetch(`${GRAPH_API_BASE}/metrics/health`);
      if (!response.ok) throw new Error('FSMA service unhealthy');
      return response.json();
    },
    refetchInterval: 30 * 1000,
  });
}

// ============== Gaps & Orphans ==============

export function useTraceGaps(apiKey: string, limit = 50) {
  return useQuery({
    queryKey: ['fsma', 'gaps', limit],
    queryFn: () => fsmaFetch<{ gaps: Array<{ event_id: string; missing_kdes: string[]; facility: string }> }>(
      `/gaps?limit=${limit}`,
      apiKey
    ),
    enabled: !!apiKey,
    staleTime: 2 * 60 * 1000,
  });
}

export function useOrphanedLots(apiKey: string) {
  return useQuery({
    queryKey: ['fsma', 'gaps', 'orphans'],
    queryFn: () => fsmaFetch<{ orphans: Array<{ tlc: string; last_event: string; days_stagnant: number }> }>(
      '/gaps/orphans',
      apiKey
    ),
    enabled: !!apiKey,
    staleTime: 5 * 60 * 1000,
  });
}

export function useExportComplianceReport(apiKey: string) {
  return useMutation({
    mutationFn: async () => {
      const response = await fetch(`${GRAPH_API_BASE}/export/gaps`, {
        headers: {
          'X-RegEngine-API-Key': apiKey,
        },
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

// ============================================================================
// V2 Applicability & Exemption Wizard Hooks
// These call public endpoints — no API key required.
// ============================================================================

/**
 * Fetch all 23 FTL categories with CTE/KDE metadata.
 * Results are cached for 24 hours (data is static regulatory content).
 */
export function useFTLCategories() {
  return useQuery<FTLCategoriesResponse>({
    queryKey: ['fsma', 'wizard', 'ftl-categories'],
    queryFn: async () => {
      const url = `${GRAPH_API_BASE}/wizard/ftl-categories`;
      const response = await fetch(url);
      if (!response.ok) throw new Error(`FTL categories fetch failed: ${response.status}`);
      return response.json();
    },
    staleTime: 24 * 60 * 60 * 1000, // 24 hours — regulatory data is stable
    gcTime: 24 * 60 * 60 * 1000,
  });
}

/**
 * Check if a list of selected FTL category IDs makes the user subject to FSMA 204.
 * Only runs when selections is non-empty.
 */
export function useCheckApplicability(selections: string[]) {
  return useQuery<WizardApplicabilityResult>({
    queryKey: ['fsma', 'wizard', 'applicability', selections],
    queryFn: async () => {
      const url = `${GRAPH_API_BASE}/wizard/applicability`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ selections }),
      });
      if (!response.ok) throw new Error(`Applicability check failed: ${response.status}`);
      return response.json();
    },
    enabled: selections.length > 0,
  });
}

/**
 * Evaluate exemption status from wizard yes/no answers.
 * answers is a map of exemption ID → boolean (true = Yes, false = No).
 * Only runs when at least one answer has been provided.
 */
export function useCheckExemptions(answers: Record<string, boolean>) {
  const answerCount = Object.keys(answers).length;
  return useQuery<WizardExemptionResult>({
    queryKey: ['fsma', 'wizard', 'exemptions', answers],
    queryFn: async () => {
      const url = `${GRAPH_API_BASE}/wizard/exemptions`;
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers }),
      });
      if (!response.ok) throw new Error(`Exemption check failed: ${response.status}`);
      return response.json();
    },
    enabled: answerCount > 0,
  });
}

// ─── Phase 29: Compliance Score ───────────────────────────────────────────────

export interface ComplianceScoreResult {
  tenant_id: string;
  overall_score: number;
  obligation_coverage: number;
  control_effectiveness: number;
  evidence_freshness: number;
  total_obligations: number;
  controls_mapped: number;
  evidence_items: number;
  is_demo: boolean;
  generated_at: string;
}

/**
 * Fetch the tenant-scoped FSMA compliance score.
 * Returns a demo payload when the graph has no tenant data yet.
 */
export function useComplianceScore(apiKey: string) {
  return useQuery<ComplianceScoreResult>({
    queryKey: ['fsma', 'compliance-score', apiKey],
    queryFn: () => fsmaFetch<ComplianceScoreResult>('/compliance/score', apiKey),
    enabled: !!apiKey,
    staleTime: 60_000, // 60s — score is expensive to compute
    retry: 1,
  });
}
