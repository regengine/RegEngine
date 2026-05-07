import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());
const mockUseTenant = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => mockUseTenant(),
}));

vi.mock('@/lib/api-config', () => ({
    getServiceURL: () => '/api/ingestion',
}));

import { useApiContext, useApiMutate, useApiQuery } from '@/hooks/use-api-query';

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

describe('use-api-query hooks', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({
            apiKey: null,
            isAuthenticated: true,
        });
        mockUseTenant.mockReturnValue({
            tenantId: 'tenant-123',
        });
    });

    it('fetches through the same-origin proxy when authenticated even if apiKey is null', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({ ok: true }),
        });

        const wrapper = createWrapper();
        const { result } = renderHook(
            () => useApiQuery(['demo'], '/api/v1/demo'),
            { wrapper },
        );

        await waitFor(() => expect(result.current.isSuccess).toBe(true));

        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/ingestion/api/v1/demo',
            expect.objectContaining({
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
            }),
        );
    });

    it('stays disabled when the user is not authenticated', () => {
        mockUseAuth.mockReturnValue({
            apiKey: null,
            isAuthenticated: false,
        });

        const wrapper = createWrapper();
        const { result } = renderHook(
            () => useApiQuery(['demo'], '/api/v1/demo'),
            { wrapper },
        );

        expect(result.current.fetchStatus).toBe('idle');
        expect(fetchWithCsrfMock).not.toHaveBeenCalled();
    });

    it('returns auth state and tenant context without inventing a placeholder apiKey', () => {
        const { result } = renderHook(() => useApiContext());

        expect(result.current.apiKey).toBe('');
        expect(result.current.isAuthenticated).toBe(true);
        expect(result.current.tenantId).toBe('tenant-123');
    });

    it('uses cookie-backed fetches for authenticated mutations', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            json: async () => ({ created: true }),
        });

        const wrapper = createWrapper();
        const { result } = renderHook(
            () => useApiMutate<{ created: boolean }, { name: string }>('/api/v1/demo', { method: 'POST' }),
            { wrapper },
        );

        await act(async () => {
            result.current.mutate({ name: 'Acme' });
        });

        await waitFor(() => expect(result.current.isSuccess).toBe(true));

        expect(fetchWithCsrfMock).toHaveBeenCalledWith(
            '/api/ingestion/api/v1/demo',
            expect.objectContaining({
                method: 'POST',
                credentials: 'include',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ name: 'Acme' }),
            }),
        );
    });
});
