'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`, options);
    if (!res.ok) throw new Error(`Partners API error: ${res.status}`);
    return res.json();
}

export function usePartners(tier?: string) {
    const qs = tier ? `?tier=${tier}` : '';
    return useQuery({
        queryKey: ['partners', 'list', tier],
        queryFn: () => fetchJSON<any>(`/v1/billing/partners${qs}`),
        staleTime: 30_000,
    });
}

export function usePartner(partnerId: string) {
    return useQuery({
        queryKey: ['partners', partnerId],
        queryFn: () => fetchJSON<any>(`/v1/billing/partners/${partnerId}`),
        enabled: !!partnerId,
    });
}

export function usePartnerSummary() {
    return useQuery({
        queryKey: ['partners', 'summary'],
        queryFn: () => fetchJSON<any>('/v1/billing/partners/summary'),
        staleTime: 30_000,
    });
}

export function useReferrals(partnerId?: string) {
    const qs = partnerId ? `?partner_id=${partnerId}` : '';
    return useQuery({
        queryKey: ['partners', 'referrals', partnerId],
        queryFn: () => fetchJSON<any>(`/v1/billing/partners/referrals${qs}`),
        staleTime: 30_000,
    });
}

export function usePayouts(partnerId?: string) {
    const qs = partnerId ? `?partner_id=${partnerId}` : '';
    return useQuery({
        queryKey: ['partners', 'payouts', partnerId],
        queryFn: () => fetchJSON<any>(`/v1/billing/partners/payouts${qs}`),
        staleTime: 30_000,
    });
}

export function useRegisterPartner() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (data: { name: string; company: string; email: string }) =>
            fetchJSON<any>('/v1/billing/partners', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['partners'] }),
    });
}

export function useRecordReferral() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: ({ partnerId, ...data }: { partnerId: string; tenant_id: string; tenant_name: string; tier_id: string; monthly_value_cents: number }) =>
            fetchJSON<any>(`/v1/billing/partners/${partnerId}/referral`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['partners'] }),
    });
}
