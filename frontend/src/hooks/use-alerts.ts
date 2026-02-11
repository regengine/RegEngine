'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const BILLING_API = process.env.NEXT_PUBLIC_BILLING_API_URL || 'http://localhost:8800';

async function fetchJSON<T>(path: string, options?: RequestInit): Promise<T> {
    const res = await fetch(`${BILLING_API}${path}`, options);
    if (!res.ok) throw new Error(`Alerts API error: ${res.status}`);
    return res.json();
}

export function useAlertRules() {
    return useQuery({
        queryKey: ['alerts', 'rules'],
        queryFn: () => fetchJSON<any>('/v1/billing/alerts/rules'),
        staleTime: 30_000,
    });
}

export function useAlertEvents(alertType?: string, severity?: string) {
    const params = new URLSearchParams();
    if (alertType) params.set('alert_type', alertType);
    if (severity) params.set('severity', severity);
    const qs = params.toString() ? `?${params}` : '';
    return useQuery({
        queryKey: ['alerts', 'events', alertType, severity],
        queryFn: () => fetchJSON<any>(`/v1/billing/alerts/events${qs}`),
        staleTime: 15_000,
    });
}

export function useAlertsSummary() {
    return useQuery({
        queryKey: ['alerts', 'summary'],
        queryFn: () => fetchJSON<any>('/v1/billing/alerts/summary'),
        staleTime: 30_000,
    });
}

export function useWebhookLog() {
    return useQuery({
        queryKey: ['alerts', 'webhooks'],
        queryFn: () => fetchJSON<any>('/v1/billing/alerts/webhooks'),
        staleTime: 30_000,
    });
}

export function useAcknowledgeAlert() {
    const qc = useQueryClient();
    return useMutation({
        mutationFn: (eventId: string) =>
            fetchJSON<any>(`/v1/billing/alerts/events/${eventId}/acknowledge`, { method: 'POST' }),
        onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
    });
}
