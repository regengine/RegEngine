'use client';

import { useQuery } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`);
    if (!res.ok) throw new Error(`Forecasting API error: ${res.status}`);
    return res.json();
}

export function useMRRHistory() {
    return useQuery({
        queryKey: ['forecasting', 'mrr-history'],
        queryFn: () => fetchJSON<any>('/v1/billing/forecasting/mrr/history'),
        staleTime: 60_000,
    });
}

export function useMRRForecast(months = 6) {
    return useQuery({
        queryKey: ['forecasting', 'mrr-forecast', months],
        queryFn: () => fetchJSON<any>(`/v1/billing/forecasting/mrr/forecast?months=${months}`),
        staleTime: 60_000,
    });
}

export function useChurnScores(risk?: string) {
    const qs = risk ? `?risk=${risk}` : '';
    return useQuery({
        queryKey: ['forecasting', 'churn', risk],
        queryFn: () => fetchJSON<any>(`/v1/billing/forecasting/churn/scores${qs}`),
        staleTime: 30_000,
    });
}

export function useChurnOverview() {
    return useQuery({
        queryKey: ['forecasting', 'churn-overview'],
        queryFn: () => fetchJSON<any>('/v1/billing/forecasting/churn/overview'),
        staleTime: 30_000,
    });
}

export function useCLVEstimates() {
    return useQuery({
        queryKey: ['forecasting', 'clv'],
        queryFn: () => fetchJSON<any>('/v1/billing/forecasting/clv'),
        staleTime: 60_000,
    });
}

export function useCLVSummary() {
    return useQuery({
        queryKey: ['forecasting', 'clv-summary'],
        queryFn: () => fetchJSON<any>('/v1/billing/forecasting/clv/summary'),
        staleTime: 60_000,
    });
}

export function useRetentionMatrix() {
    return useQuery({
        queryKey: ['forecasting', 'retention'],
        queryFn: () => fetchJSON<any>('/v1/billing/forecasting/cohorts/retention'),
        staleTime: 120_000,
    });
}

export function useRevenueAnomalies() {
    return useQuery({
        queryKey: ['forecasting', 'anomalies'],
        queryFn: () => fetchJSON<any>('/v1/billing/forecasting/anomalies'),
        staleTime: 30_000,
    });
}

export function useExecutiveSummary() {
    return useQuery({
        queryKey: ['forecasting', 'executive'],
        queryFn: () => fetchJSON<any>('/v1/billing/forecasting/summary'),
        staleTime: 30_000,
    });
}
