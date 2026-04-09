import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { IngestURLRequest, ValidationRequest } from '@/types/api';
import type { LabelBatchInitRequest } from '@/types/labels';
import type { SystemStatusResponse, SystemMetricsResponse } from '@/lib/api-client';
import { POLL_HEALTH_MS as POLL_HEALTH, POLL_METRICS_MS as POLL_METRICS } from '@/lib/polling-config';

// Demo fallback data shown when backend services are unreachable.
// Lets the dashboard render a realistic preview instead of all "—".
// `_demo` marks data as synthetic; `_reason` tells the UI *why* we fell back.
type DemoReason = 'auth' | 'unreachable';

const DEMO_METRICS_BASE: SystemMetricsResponse = {
  total_tenants: 1,
  total_documents: 347,
  active_jobs: 0,
  compliance_score: 72,
  compliance_grade: 'C',
  events_ingested: 1_284,
  chain_length: 856,
  chain_valid: true,
  open_alerts: 3,
};

function makeDemoMetrics(reason: DemoReason): SystemMetricsResponse & { _demo: true; _reason: DemoReason } {
  return { ...DEMO_METRICS_BASE, _demo: true, _reason: reason };
}

function makeDemoStatus(reason: DemoReason): SystemStatusResponse & { _demo: true; _reason: DemoReason } {
  const msg = reason === 'auth'
    ? 'Log in to see live data'
    : 'Backend not running — showing demo data';
  return {
    _demo: true,
    _reason: reason,
    overall_status: 'degraded',
    services: [
      { name: 'admin', status: 'unhealthy', details: { error: msg } },
      { name: 'ingestion', status: 'unhealthy', details: { error: msg } },
      { name: 'compliance', status: 'unhealthy', details: { error: msg } },
    ],
  };
}

/** Check if an error is a 401/403 auth failure vs a network/server error */
function isAuthError(error: unknown): boolean {
  if (!error) return false;
  // Axios errors have response.status
  const axiosStatus = (error as { response?: { status?: number } }).response?.status;
  if (axiosStatus === 401 || axiosStatus === 403) return true;
  // Fallback: check error message
  if (error instanceof Error) {
    return error.message.includes('401') || error.message.includes('403');
  }
  return false;
}

// Health Checks
export const useAdminHealth = () => {
  return useQuery({
    queryKey: ['admin', 'health'],
    queryFn: () => apiClient.getAdminHealth(),
    refetchInterval: POLL_HEALTH,
  });
};

export const useIngestionHealth = () => {
  return useQuery({
    queryKey: ['ingestion', 'health'],
    queryFn: () => apiClient.getIngestionHealth(),
    refetchInterval: POLL_HEALTH,
  });
};

export const useComplianceHealth = () => {
  return useQuery({
    queryKey: ['compliance', 'health'],
    queryFn: () => apiClient.getComplianceHealth(),
    refetchInterval: POLL_HEALTH,
  });
};

// System Status & Metrics — fall back to demo data when backend is unreachable.
// Distinguishes "not logged in" (401) from "backend down" (network/503) so the
// UI can show the right message.
export const useSystemStatus = () => {
  const query = useQuery({
    queryKey: ['system', 'status'],
    queryFn: () => apiClient.getSystemStatus(),
    refetchInterval: POLL_HEALTH,
    retry: 1,
  });
  const reason: DemoReason = isAuthError(query.error) ? 'auth' : 'unreachable';
  return {
    ...query,
    data: query.data ?? (query.error ? makeDemoStatus(reason) : undefined),
  };
};

export const useSystemMetrics = () => {
  const query = useQuery({
    queryKey: ['system', 'metrics'],
    queryFn: () => apiClient.getSystemMetrics(),
    refetchInterval: POLL_METRICS,
    retry: 1,
  });
  const reason: DemoReason = isAuthError(query.error) ? 'auth' : 'unreachable';
  return {
    ...query,
    data: query.data ?? (query.error ? makeDemoMetrics(reason) : undefined),
  };
};

export const useAPIKeys = (adminKey: string, enabled = true) => {
  return useQuery({
    queryKey: ['admin', 'keys', adminKey],
    queryFn: () => apiClient.listAPIKeys(adminKey),
    enabled: enabled && !!adminKey,
  });
};

export const useCreateAPIKey = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ adminKey, name, description, tenantId }: { adminKey: string; name: string; description?: string; tenantId?: string }) =>
      apiClient.createAPIKey(adminKey, { name, description, tenantId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'keys'] });
    },
  });
};

export const useGenerateAPIKey = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ adminKey, tenantId }: { adminKey: string; tenantId?: string }) => apiClient.generateAPIKey(adminKey, tenantId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'keys'] });
    },
  });
};

export const useRevokeAPIKey = () => {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ adminKey, keyId }: { adminKey: string; keyId: string }) =>
      apiClient.revokeAPIKey(adminKey, keyId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['admin', 'keys'] });
    },
  });
};

// Ingestion
export const useIngestURL = () => {
  return useMutation({
    mutationFn: ({ apiKey, url, sourceSystem }: { apiKey: string; url: string; sourceSystem?: string }) =>
      apiClient.ingestURL(apiKey, url, sourceSystem),
  });
};

export const useIngestFile = () => {
  return useMutation({
    mutationFn: ({ apiKey, file, sourceSystem }: { apiKey: string; file: File; sourceSystem?: string }) =>
      apiClient.ingestFile(apiKey, file, sourceSystem),
  });
};

export const useCreateTenant = () => {
  return useMutation({
    mutationFn: ({ adminKey, name }: { adminKey: string; name: string }) =>
      apiClient.createTenant(adminKey, name),
  });
};

// Compliance
export const useIndustries = () => {
  return useQuery({
    queryKey: ['compliance', 'industries'],
    queryFn: () => apiClient.getIndustries(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
};

export const useChecklists = (industry?: string) => {
  return useQuery({
    queryKey: ['compliance', 'checklists', industry],
    queryFn: () => apiClient.getChecklists(industry),
    staleTime: 2 * 60 * 1000, // 2 minutes
  });
};

export const useChecklist = (checklistId: string, enabled = true) => {
  return useQuery({
    queryKey: ['compliance', 'checklist', checklistId],
    queryFn: () => apiClient.getChecklist(checklistId),
    enabled: enabled && !!checklistId,
    staleTime: 5 * 60 * 1000,
  });
};

export const useValidateConfig = () => {
  return useMutation({
    mutationFn: (request: ValidationRequest) => apiClient.validateConfig(request),
  });
};

// Labels
export const useInitializeLabelBatch = () => {
  return useMutation({
    mutationFn: ({ request, tenantId }: { request: LabelBatchInitRequest; tenantId?: string }) =>
      apiClient.initializeLabelBatch(request, tenantId),
  });
};

export const useLabelsHealth = () => {
  return useQuery({
    queryKey: ['labels', 'health'],
    queryFn: () => apiClient.getLabelsHealth(),
    refetchInterval: POLL_HEALTH,
  });
};
