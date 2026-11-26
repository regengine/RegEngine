/**
 * WI-11 (2026-11-04): the request each converted call site sends is the one it
 * sent before the conversion. Each test pins the exact URL and init shape.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

import { apiClient, rawFetch, requestPublicJson } from '@/lib/api-client';
import { StatusBoard } from '@/app/status/StatusBoard';
import { ComplianceStatusWidget } from '@/components/dashboard/compliance-status-widget';
import { useSystemStatus } from '@/hooks/use-api';

function jsonResponse(body: unknown, init: { status?: number } = {}): Response {
    return new Response(JSON.stringify(body), {
        status: init.status ?? 200,
        headers: { 'Content-Type': 'application/json' },
    });
}

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
    fetchMock = vi.fn().mockImplementation(async () => jsonResponse({ ok: true }));
    vi.stubGlobal('fetch', fetchMock);
});

afterEach(() => {
    vi.unstubAllGlobals();
});

describe('rawFetch', () => {
    it('passes the URL and init through untouched', async () => {
        const init = { cache: 'no-store' as const, headers: { 'X-Probe': '1' } };
        await rawFetch('/api/health', init);
        expect(fetchMock).toHaveBeenCalledTimes(1);
        const [url, passed] = fetchMock.mock.calls[0];
        expect(url).toBe('/api/health');
        expect(passed).toBe(init);
    });
});

describe('requestPublicJson (supplier portal helper)', () => {
    it('sends Content-Type only with a body and parses JSON', async () => {
        fetchMock.mockResolvedValueOnce(jsonResponse({ hello: 'world' }));
        const data = await requestPublicJson<{ hello: string }>('/api/portal/x', {
            method: 'POST',
            body: JSON.stringify({ a: 1 }),
        });
        expect(data).toEqual({ hello: 'world' });
        const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
        expect(url).toBe('/api/portal/x');
        expect(init.method).toBe('POST');
        expect(init.headers).toEqual({ 'Content-Type': 'application/json' });
        expect(init.credentials).toBeUndefined();
    });

    it('sends no Content-Type without a body and throws { status, data } on errors', async () => {
        fetchMock.mockResolvedValueOnce(jsonResponse({ detail: 'nope' }, { status: 403 }));
        await expect(requestPublicJson('/api/portal/y')).rejects.toEqual({ status: 403, data: { detail: 'nope' } });
        const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
        expect(init.headers).toEqual({});
    });
});

describe('StatusBoard', () => {
    it('reads /api/health with cache: no-store and nothing else', async () => {
        fetchMock.mockResolvedValue(
            jsonResponse({
                status: 'healthy',
                timestamp: new Date().toISOString(),
                services: [],
                summary: { healthy: 0, total: 0 },
            }),
        );
        render(<StatusBoard />);
        await waitFor(() => expect(fetchMock).toHaveBeenCalled());
        expect(fetchMock.mock.calls[0]).toEqual(['/api/health', { cache: 'no-store' }]);
    });
});

describe('ComplianceStatusWidget', () => {
    it('reads the tenant status path with default init', async () => {
        fetchMock.mockResolvedValue(
            jsonResponse({
                tenant_id: 'tenant-123',
                status: 'COMPLIANT',
                status_emoji: '',
                status_label: 'Compliant',
                active_alert_count: 0,
                critical_alert_count: 0,
                active_alerts: [],
            }),
        );
        render(<ComplianceStatusWidget tenantId="tenant-123" />);
        await waitFor(() => expect(fetchMock).toHaveBeenCalled());
        const [url, init] = fetchMock.mock.calls[0];
        expect(url).toBe('/api/v1/compliance/status/tenant-123');
        expect(init).toBeUndefined();
    });
});

describe('useSystemStatus', () => {
    it('probes the three service health endpoints with credentials and a timeout signal', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ status: 'healthy' }));
        const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } });
        const wrapper = ({ children }: { children: ReactNode }) => (
            <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
        );
        const { result } = renderHook(() => useSystemStatus(), { wrapper });
        await waitFor(() => expect(result.current.data).toBeDefined());
        const calls = fetchMock.mock.calls.map(([url, init]) => [url, (init as RequestInit).credentials, (init as RequestInit).signal instanceof AbortSignal]);
        expect(calls).toEqual([
            ['/api/admin/health', 'include', true],
            ['/api/ingestion/health', 'include', true],
            ['/api/compliance/health', 'include', true],
        ]);
    });
});

describe('apiClient.getSystemStatus (sysadmin page)', () => {
    it('calls the same-origin admin proxy with cookies and no bearer placeholder', async () => {
        fetchMock.mockResolvedValue(jsonResponse({ overall_status: 'healthy', services: [] }));
        apiClient.setAccessToken(null);
        await apiClient.getSystemStatus();
        const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
        expect(url).toBe('/api/admin/v1/system/status');
        expect(init.method).toBe('GET');
        expect(init.credentials).toBe('include');
        expect((init.headers as Record<string, string>).Authorization).toBeUndefined();
    });
});
