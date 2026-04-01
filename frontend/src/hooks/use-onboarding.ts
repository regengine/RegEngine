'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';

export function useOnboardingStatus(tenantId: string | null | undefined) {
  return useQuery({
    queryKey: ['onboarding-status', tenantId],
    queryFn: () => apiClient.getOnboardingStatus(tenantId!),
    enabled: !!tenantId,
    staleTime: 60_000,
  });
}

export function useUpdateOnboarding(tenantId: string | null | undefined) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (settings: Record<string, unknown>) =>
      apiClient.updateTenantSettings(tenantId!, settings),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['onboarding-status', tenantId] });
    },
  });
}
