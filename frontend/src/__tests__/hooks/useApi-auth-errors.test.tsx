import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

const mocks = vi.hoisted(() => ({
    getSystemMetrics: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
    apiClient: {
        getSystemMetrics: (...args: unknown[]) => mocks.getSystemMetrics(...args),
    },
}));

import { useSystemMetrics, useSystemStatus } from '@/hooks/use-api';

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

function authError(status: number) {
    const err = new Error(status === 401 ? 'Unauthorized' : 'Forbidden') as Error & {
        response: { status: number };
    };
    err.response = { status };
    return err;
}

describe('use-api adversarial: auth failures must not render as demo zeros', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.unstubAllGlobals();
    });

    it('surfaces a 401 from getSystemMetrics instead of zeroed demo data', async () => {
        mocks.getSystemMetrics.mockRejectedValue(authError(401));
        const { result } = renderHook(() => useSystemMetrics(), {
            wrapper: createWrapper(),
        });
        await waitFor(() => expect(result.current.isError).toBe(true));
        expect(result.current.data).toBeUndefined();
        expect(result.current.error).toBeTruthy();
    });

    it('surfaces a 403 from getSystemMetrics instead of zeroed demo data', async () => {
        mocks.getSystemMetrics.mockRejectedValue(authError(403));
        const { result } = renderHook(() => useSystemMetrics(), {
            wrapper: createWrapper(),
        });
        await waitFor(() => expect(result.current.isError).toBe(true));
        expect(result.current.data).toBeUndefined();
    });

    it('returns no placeholder data for a 503 — real metrics only', async () => {
        const err = new Error('Service Unavailable') as Error & {
            response: { status: number };
        };
        err.response = { status: 503 };
        mocks.getSystemMetrics.mockRejectedValue(err);
        const { result } = renderHook(() => useSystemMetrics(), {
            wrapper: createWrapper(),
        });
        await waitFor(() => expect(result.current.isError).toBe(true));
        expect(result.current.data).toBeUndefined();
        expect(result.current.error).toBeTruthy();
    });

    it('surfaces proxy 401s from health checks instead of demo degraded status', async () => {
        vi.stubGlobal('fetch', vi.fn(async () => ({
            ok: false,
            status: 401,
            statusText: 'Unauthorized',
        })));
        const { result } = renderHook(() => useSystemStatus(), {
            wrapper: createWrapper(),
        });
        await waitFor(() => expect(result.current.isError).toBe(true));
        expect(result.current.data).toBeUndefined();
    });
});
