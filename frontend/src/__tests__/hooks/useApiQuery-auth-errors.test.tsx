import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
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

import { useApiQuery } from '@/hooks/use-api-query';

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

function denied(status: number) {
    return {
        ok: false,
        status,
        statusText: status === 401 ? 'Unauthorized' : 'Forbidden',
        json: async () => ({ error: 'denied' }),
    };
}

describe('useApiQuery adversarial: auth errors must carry status', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({ isAuthenticated: true });
        mockUseTenant.mockReturnValue({ tenantId: 'tenant-123' });
    });

    it('exposes 401 on the query error for session-expiry handling', async () => {
        fetchWithCsrfMock.mockResolvedValue(denied(401));
        const { result } = renderHook(() => useApiQuery(['a'], '/api/v1/demo'), {
            wrapper: createWrapper(),
        });
        await waitFor(() => expect(result.current.isError).toBe(true));
        const err = result.current.error as Error & {
            status?: number; response?: { status?: number };
        };
        expect(err.message).toContain('401');
        expect(err.status ?? err.response?.status).toBe(401);
    });

    it('exposes 403 on the query error for forbidden handling', async () => {
        fetchWithCsrfMock.mockResolvedValue(denied(403));
        const { result } = renderHook(() => useApiQuery(['b'], '/api/v1/demo'), {
            wrapper: createWrapper(),
        });
        await waitFor(() => expect(result.current.isError).toBe(true));
        const err = result.current.error as Error & {
            status?: number; response?: { status?: number };
        };
        expect(err.message).toContain('403');
        expect(err.status ?? err.response?.status).toBe(403);
    });
});
