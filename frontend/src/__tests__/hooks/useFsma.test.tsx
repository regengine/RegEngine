import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

import {
    useAcknowledgeAlert,
    useComplianceScore,
    useDriftAlerts,
    useExportComplianceReport,
    useFSMADashboard,
    useForwardTrace,
} from '@/hooks/use-fsma';

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: Infinity },
            mutations: { retry: false, gcTime: Infinity },
        },
    });
    return ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

describe('use-fsma hooks', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({
            isAuthenticated: true,
        });
    });

    afterEach(() => {
        vi.restoreAllMocks();
        vi.unstubAllGlobals();
    });

    it('fetches the dashboard through the same-origin proxy when authenticated without placeholder credentials', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                system_health: 'HEALTHY',
                total_lots: 12,
                total_facilities: 4,
            }),
        });

        const wrapper = createWrapper();
        const { result } = renderHook(() => useFSMADashboard(), { wrapper });

        await waitFor(() => expect(result.current.isSuccess).toBe(true));

        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/fsma/metrics/dashboard',
            expect.objectContaining({
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            }),
        );
    });

    it('keeps authenticated trace queries enabled without a placeholder apiKey', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                facilities: [],
                events: [],
                total_facilities: 0,
                total_events: 0,
                query_time_ms: 18,
            }),
        });

        const wrapper = createWrapper();
        const { result } = renderHook(() => useForwardTrace('LOT-123', true), { wrapper });

        await waitFor(() => expect(result.current.isSuccess).toBe(true));

        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/fsma/traceability/trace/forward/LOT-123',
            expect.objectContaining({
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            }),
        );
    });

    it('does not run protected FSMA queries when the user is not authenticated', () => {
        mockUseAuth.mockReturnValue({
            isAuthenticated: false,
        });

        const wrapper = createWrapper();
        const { result } = renderHook(() => useDriftAlerts(20), { wrapper });

        expect(result.current.fetchStatus).toBe('idle');
        expect(fetchWithCsrfMock).not.toHaveBeenCalled();
    });

    it('uses cookie-backed exports without sending X-RegEngine-API-Key headers', async () => {
        const createObjectURL = vi.fn(() => 'blob:fsma-report');
        const revokeObjectURL = vi.fn();
        const originalCreateElement = document.createElement.bind(document);
        const anchor = originalCreateElement('a');
        const click = vi.fn();
        const appendChild = vi.spyOn(document.body, 'appendChild');
        const removeChild = vi.spyOn(document.body, 'removeChild');
        vi.stubGlobal('URL', {
            ...window.URL,
            createObjectURL,
            revokeObjectURL,
        });
        anchor.click = click;
        vi.spyOn(document, 'createElement').mockImplementation(((tagName: string, options?: ElementCreationOptions) => {
            if (tagName.toLowerCase() === 'a') {
                return anchor;
            }
            return originalCreateElement(tagName, options);
        }) as typeof document.createElement);

        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            blob: async () => new Blob(['report']),
        });

        const wrapper = createWrapper();
        const { result } = renderHook(() => useExportComplianceReport(), { wrapper });

        await act(async () => {
            await result.current.mutateAsync();
        });

        const [, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/fsma/export/gaps',
            expect.objectContaining({ credentials: 'include' }),
        );
        expect(new Headers(init.headers).get('X-RegEngine-API-Key')).toBeNull();
        expect(click).toHaveBeenCalled();
        expect(appendChild).toHaveBeenCalled();
        expect(removeChild).toHaveBeenCalled();
        expect(createObjectURL).toHaveBeenCalled();
        expect(revokeObjectURL).toHaveBeenCalled();
    });

    it('uses auth state instead of placeholder apiKey values in the compliance score hook enablement', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({
                tenant_id: 'tenant-123',
                overall_score: 91,
                obligation_coverage: 95,
                control_effectiveness: 88,
                evidence_freshness: 90,
                total_obligations: 10,
                controls_mapped: 9,
                evidence_items: 12,
                is_demo: false,
                generated_at: '2026-05-07T00:00:00.000Z',
            }),
        });

        const wrapper = createWrapper();
        const { result } = renderHook(() => useComplianceScore(), { wrapper });

        await waitFor(() => expect(result.current.isSuccess).toBe(true));
        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/fsma/compliance/score',
            expect.objectContaining({
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            }),
        );
    });

    it('acknowledges drift alerts through the proxy without browser credentials headers', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({ success: true }),
        });

        const wrapper = createWrapper();
        const { result } = renderHook(() => useAcknowledgeAlert(), { wrapper });

        await act(async () => {
            await result.current.mutateAsync('alert-1');
        });

        const [, init] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/fsma/drift/alerts/alert-1/acknowledge',
            expect.objectContaining({
                method: 'POST',
                credentials: 'include',
            }),
        );
        expect(new Headers(init.headers).get('X-RegEngine-API-Key')).toBeNull();
    });
});
