import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { IngestURLRequest, ValidationRequest } from '@/types/api';
import type { LabelBatchInitRequest } from '@/types/labels';

// Health Checks
export const useAdminHealth = () => {
  return useQuery({
    queryKey: ['admin', 'health'],
    queryFn: () => apiClient.getAdminHealth(),
    refetchInterval: 30000,
  });
};

export const useIngestionHealth = () => {
  return useQuery({
    queryKey: ['ingestion', 'health'],
    queryFn: () => apiClient.getIngestionHealth(),
    refetchInterval: 30000,
  });
};

export const useOpportunityHealth = () => {
  return useQuery({
    queryKey: ['opportunity', 'health'],
    queryFn: () => apiClient.getOpportunityHealth(),
    refetchInterval: 30000,
  });
};

export const useComplianceHealth = () => {
  return useQuery({
    queryKey: ['compliance', 'health'],
    queryFn: () => apiClient.getComplianceHealth(),
    refetchInterval: 30000,
  });
};

// API Keys
export const useSystemStatus = () => {
  return useQuery({
    queryKey: ['system', 'status'],
    queryFn: () => apiClient.getSystemStatus(),
    refetchInterval: 30000, // 30s polling
  });
};

export const useSystemMetrics = () => {
  return useQuery({
    queryKey: ['system', 'metrics'],
    queryFn: () => apiClient.getSystemMetrics(),
    refetchInterval: 15000, // 15s polling
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

// Opportunities
export const useArbitrageOpportunities = (params: {
  j1?: string;
  j2?: string;
  concept?: string;
  rel_delta?: number;
  limit?: number;
  since?: string;
}) => {
  return useQuery({
    queryKey: ['opportunities', 'arbitrage', params],
    queryFn: () => apiClient.getArbitrageOpportunities(params),
    staleTime: 1 * 60 * 1000, // 1 minute
    // Arbitrage endpoint allows optional jurisdictions, but we should still have at least one jurisdiction
    enabled: !!params.j1 || !!params.j2,
  });
};

export const useComplianceGaps = (params: {
  j1?: string;
  j2?: string;
  limit?: number;
}) => {
  return useQuery({
    queryKey: ['opportunities', 'gaps', params],
    queryFn: () => apiClient.getComplianceGaps(params),
    staleTime: 1 * 60 * 1000,
    // Only fetch when both jurisdictions are provided (required by backend)
    enabled: !!params.j1 && !!params.j2,
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
    refetchInterval: 30000,
  });
};
