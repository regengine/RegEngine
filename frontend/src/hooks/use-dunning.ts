'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`, options);
    if (!res.ok) throw new Error(`Dunning API error: ${res.status}`);
    return res.json();
}

export function useDunningCases(status?: string, stage?: string) {
    const params = new URLSearchParams();
    if (status) params.set('status', status);
    if (stage) params.set('stage', stage);
    const qs = params.toString() ? `?${params}` : '';
    return useQuery({
        queryKey: ['dunning', 'list', status, stage],
        queryFn: () => fetchJSON<unknown>(`/v1/billing/dunning${qs}`),
        staleTime: 30_000,
    });
}

export function useDunningSummary() {
    return useQuery({
        queryKey: ['dunning', 'summary'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/dunning/summary'),
        staleTime: 30_000,
    });
}

export function useRetryPayment() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (caseId: string) =>
            fetchJSON<unknown>(`/v1/billing/dunning/${caseId}/retry`, { method: 'POST' }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['dunning'] }),
    });
}

export function useEscalateCase() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (caseId: string) =>
            fetchJSON<unknown>(`/v1/billing/dunning/${caseId}/escalate`, { method: 'POST' }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['dunning'] }),
    });
}
