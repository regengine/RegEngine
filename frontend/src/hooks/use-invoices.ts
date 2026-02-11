'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`, options);
    if (!res.ok) throw new Error(`Invoices API error: ${res.status}`);
    return res.json();
}

export function useInvoices(tenantId?: string, status?: string) {
    const params = new URLSearchParams();
    if (tenantId) params.set('tenant_id', tenantId);
    if (status) params.set('status', status);
    const qs = params.toString() ? `?${params}` : '';
    return useQuery({
        queryKey: ['invoices', 'list', tenantId, status],
        queryFn: () => fetchJSON<any>(`/v1/billing/invoices${qs}`),
        staleTime: 30_000,
    });
}

export function useInvoice(invoiceId: string) {
    return useQuery({
        queryKey: ['invoices', invoiceId],
        queryFn: () => fetchJSON<any>(`/v1/billing/invoices/${invoiceId}`),
        enabled: !!invoiceId,
    });
}

export function useAgingReport() {
    return useQuery({
        queryKey: ['invoices', 'aging'],
        queryFn: () => fetchJSON<any>('/v1/billing/invoices/aging'),
        staleTime: 60_000,
    });
}

export function useRevenueSummary() {
    return useQuery({
        queryKey: ['invoices', 'revenue-summary'],
        queryFn: () => fetchJSON<any>('/v1/billing/invoices/revenue-summary'),
        staleTime: 30_000,
    });
}

export function usePayments(tenantId?: string) {
    const qs = tenantId ? `?tenant_id=${tenantId}` : '';
    return useQuery({
        queryKey: ['invoices', 'payments', tenantId],
        queryFn: () => fetchJSON<any>(`/v1/billing/invoices/payments${qs}`),
        staleTime: 30_000,
    });
}

export function useCreateInvoice() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (data: { tenant_id: string; tenant_name: string; tier_id: string }) =>
            fetchJSON<any>('/v1/billing/invoices', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data),
            }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['invoices'] }),
    });
}

export function usePayInvoice() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: ({ invoiceId, amount_cents }: { invoiceId: string; amount_cents: number }) =>
            fetchJSON<any>(`/v1/billing/invoices/${invoiceId}/pay`, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount_cents }),
            }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['invoices'] }),
    });
}
