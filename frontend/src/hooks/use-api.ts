import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { IngestURLRequest, ValidationRequest } from '@/types/api';
import type { LabelBatchInitRequest } from '@/types/labels';

// Configurable polling intervals (ms) — override via env vars
const POLL_HEALTH = Number(process.env.NEXT_PUBLIC_POLL_HEALTH_MS) || 30_000;
const POLL_METRICS = Number(process.env.NEXT_PUBLIC_POLL_METRICS_MS) || 15_000;

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

// System Status & Metrics
export const useSystemStatus = () => {
  return useQuery({
    queryKey: ['system', 'status'],
    queryFn: () => apiClient.getSystemStatus(),
    refetchInterval: POLL_HEALTH,
  });
};

export const useSystemMetrics = () => {
  return useQuery({
    queryKey: ['system', 'metrics'],
    queryFn: () => apiClient.getSystemMetrics(),
    refetchInterval: POLL_METRICS,
  });
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
