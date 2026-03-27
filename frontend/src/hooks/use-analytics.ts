'use client';

/**
 * React Query hooks for the billing analytics and usage metering API.
 */

import { useQuery } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`);
    if (!res.ok) throw new Error(`Analytics API error: ${res.status}`);
    return res.json();
}

// ── Analytics Hooks ───────────────────────────────────────────────

export function useAnalyticsOverview() {
    return useQuery({
        queryKey: ['analytics', 'overview'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/analytics/overview'),
        staleTime: 30_000,
        refetchInterval: 60_000,
    });
}

export function useMRRHistory(months = 12) {
    return useQuery({
        queryKey: ['analytics', 'mrr-history', months],
        queryFn: () => fetchJSON<unknown>(`/v1/billing/analytics/mrr-history?months=${months}`),
        staleTime: 60_000,
    });
}

export function useCohortAnalysis() {
    return useQuery({
        queryKey: ['analytics', 'cohorts'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/analytics/cohorts'),
        staleTime: 120_000,
    });
}

export function useConversionFunnel() {
    return useQuery({
        queryKey: ['analytics', 'funnel'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/analytics/funnel'),
        staleTime: 60_000,
    });
}

export function useCreditProgramROI() {
    return useQuery({
        queryKey: ['analytics', 'credits'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/analytics/credits'),
        staleTime: 120_000,
    });
}

export function useRevenueForecasts(months = 6) {
    return useQuery({
        queryKey: ['analytics', 'forecasts', months],
        queryFn: () => fetchJSON<unknown>(`/v1/billing/analytics/forecasts?months=${months}`),
        staleTime: 120_000,
    });
}

// ── Usage Hooks ───────────────────────────────────────────────────

export function useUsageSummary(tenantId: string, tierId = 'growth') {
    return useQuery({
        queryKey: ['usage', 'summary', tenantId, tierId],
        queryFn: () => fetchJSON<unknown>(`/v1/billing/usage/${tenantId}/summary?tier_id=${tierId}`),
        enabled: !!tenantId,
        staleTime: 30_000,
    });
}

export function useUsageBreakdown(tenantId: string, tierId = 'growth') {
    return useQuery({
        queryKey: ['usage', 'breakdown', tenantId, tierId],
        queryFn: () => fetchJSON<unknown>(`/v1/billing/usage/${tenantId}/breakdown?tier_id=${tierId}`),
        enabled: !!tenantId,
        staleTime: 60_000,
    });
}

export function useOverageAlerts() {
    return useQuery({
        queryKey: ['usage', 'overage-alerts'],
        queryFn: () => fetchJSON<unknown>('/v1/billing/usage/overage-alerts'),
        staleTime: 30_000,
        refetchInterval: 60_000,
    });
}
