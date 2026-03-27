'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`, options);
    if (!res.ok) throw new Error(`Tax API error: ${res.status}`);
    return res.json();
}

export function useTaxJurisdictions(country?: string) {
    const qs = country ? `?country=${country}` : '';
    return useQuery({
        queryKey: ['tax', 'jurisdictions', country],
        queryFn: () => fetchJSON<unknown>(`/v1/billing/tax/jurisdictions${qs}`),
        staleTime: 60_000,
    });
}

export function useTaxExemptions(tenantId?: string) {
    const qs = tenantId ? `?tenant_id=${tenantId}` : '';
    return useQuery({
        queryKey: ['tax', 'exemptions', tenantId],
        queryFn: () => fetchJSON<unknown>(`/v1/billing/tax/exemptions${qs}`),
        staleTime: 30_000,
    });
}

export function useTaxReport(period?: string) {
    const qs = period ? `?period=${period}` : '';
    return useQuery({
        queryKey: ['tax', 'report', period],
        queryFn: () => fetchJSON<unknown>(`/v1/billing/tax/report${qs}`),
        staleTime: 30_000,
    });
}

export function useCalculateTax() {
    return useMutation({
        mutationFn: (data: { tenant_id: string; jurisdiction_id: string; subtotal_cents: number }) =>
            fetchJSON<unknown>('/v1/billing/tax/calculate', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            }),
    });
}
