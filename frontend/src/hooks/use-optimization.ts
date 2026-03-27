'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`, options);
    if (!res.ok) throw new Error(`Optimization API error: ${res.status}`);
    return res.json();
}

export function usePricingRecommendations() {
    return useQuery({
        queryKey: ['optimization', 'pricing'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/optimization/pricing'),
        staleTime: 120_000,
    });
}

export function useRevenueOpportunities(type?: string) {
    const qs = type ? `?opp_type=${type}` : '';
    return useQuery({
        queryKey: ['optimization', 'opportunities', type],
        queryFn: () => fetchJSON<unknown>(`/v1/billing/optimization/opportunities${qs}`),
        staleTime: 30_000,
    });
}

export function useWinBackCampaigns() {
    return useQuery({
        queryKey: ['optimization', 'campaigns'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/optimization/campaigns'),
        staleTime: 30_000,
    });
}

export function useCustomerHealth() {
    return useQuery({
        queryKey: ['optimization', 'health'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/optimization/health'),
        staleTime: 60_000,
    });
}

export function useExpansionMetrics() {
    return useQuery({
        queryKey: ['optimization', 'expansion'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/optimization/expansion'),
        staleTime: 60_000,
    });
}

export function usePipelineSummary() {
    return useQuery({
        queryKey: ['optimization', 'pipeline'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/optimization/pipeline'),
        staleTime: 30_000,
    });
}
