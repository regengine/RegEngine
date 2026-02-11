'use client';

/**
 * React Query hooks for the enterprise contracts API.
 */

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`, options);
    if (!res.ok) throw new Error(`Contracts API error: ${res.status}`);
    return res.json();
}

// ── Query Hooks ───────────────────────────────────────────────────

export function useContracts(stage?: string) {
    const params = stage ? `?stage=${stage}` : '';
    return useQuery({
        queryKey: ['contracts', 'list', stage],
        queryFn: () => fetchJSON<any>(`/v1/billing/contracts${params}`),
        staleTime: 30_000,
    });
}

export function useContract(contractId: string) {
    return useQuery({
        queryKey: ['contracts', contractId],
        queryFn: () => fetchJSON<any>(`/v1/billing/contracts/${contractId}`),
        enabled: !!contractId,
    });
}

export function useDealPipeline() {
    return useQuery({
        queryKey: ['contracts', 'pipeline'],
        queryFn: () => fetchJSON<any>('/v1/billing/contracts/pipeline'),
        staleTime: 30_000,
        refetchInterval: 60_000,
    });
}

export function useSLAStatus() {
    return useQuery({
        queryKey: ['contracts', 'sla-status'],
        queryFn: () => fetchJSON<any>('/v1/billing/contracts/sla-status'),
        staleTime: 30_000,
    });
}

export function useRenewals(days = 90) {
    return useQuery({
        queryKey: ['contracts', 'renewals', days],
        queryFn: () => fetchJSON<any>(`/v1/billing/contracts/renewals?days=${days}`),
        staleTime: 60_000,
    });
}

// ── Mutation Hooks ────────────────────────────────────────────────

export function useCreateContract() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: (data: { tenant_id: string; tenant_name: string; tier_id: string; term_years?: number }) =>
            fetchJSON<any>('/v1/billing/contracts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            }),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['contracts'] }),
    });
}

export function useAdvanceStage() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ contractId, newStage }: { contractId: string; newStage: string }) =>
            fetchJSON<any>(`/v1/billing/contracts/${contractId}/stage`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ new_stage: newStage }),
            }),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['contracts'] }),
    });
}

export function useGenerateQuote() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: ({ contractId, ...data }: { contractId: string; discount_codes?: string[]; custom_discount_pct?: number }) =>
            fetchJSON<any>(`/v1/billing/contracts/${contractId}/quote`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            }),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['contracts'] }),
    });
}
