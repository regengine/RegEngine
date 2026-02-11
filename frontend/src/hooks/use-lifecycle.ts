'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`, options);
    if (!res.ok) throw new Error(`Lifecycle API error: ${res.status}`);
    return res.json();
}

export function useLifecycleChanges(tenantId?: string, changeType?: string) {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    if (changeType) params.set('change_type', changeType);
    const qs = params.toString() ? `?${params}` : '';
    return useQuery({
        queryKey: ['lifecycle', 'changes', tenantId, changeType],
        queryFn: () => fetchJSON<any>(`/v1/billing/lifecycle/changes${qs}`),
        staleTime: 30_000,
    });
}

export function useLifecycleSummary() {
    return useQuery({
        queryKey: ['lifecycle', 'summary'],
        queryFn: () => fetchJSON<any>('/v1/billing/lifecycle/summary'),
        staleTime: 30_000,
    });
}

export function useTrials(activeOnly = false) {
    const qs = activeOnly ? '?active_only=true' : '';
    return useQuery({
        queryKey: ['lifecycle', 'trials', activeOnly],
        queryFn: () => fetchJSON<any>(`/v1/billing/lifecycle/trials${qs}`),
        staleTime: 30_000,
    });
}

export function usePlanCatalog() {
    return useQuery({
        queryKey: ['lifecycle', 'plans'],
        queryFn: () => fetchJSON<any>('/v1/billing/lifecycle/plans'),
        staleTime: 120_000,
    });
}

export function useChangePlan() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (data: { tenant_id: string; tenant_name: string; from_plan: string; to_plan: string }) =>
            fetchJSON<any>('/v1/billing/lifecycle/change', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['lifecycle'] }),
    });
}
