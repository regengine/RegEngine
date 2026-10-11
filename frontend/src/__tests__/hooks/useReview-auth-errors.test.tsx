import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

import { useReviewItems } from '@/hooks/use-review';

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

describe('use-review adversarial: queue errors must carry status', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('keeps the server message but tags 401 for re-login handling', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: false,
            status: 401,
            statusText: 'Unauthorized',
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({ error: 'Session expired' }),
        });
        const { result } = renderHook(() => useReviewItems(true), {
            wrapper: createWrapper(),
        });
        await waitFor(() => expect(result.current.isError).toBe(true));
        const err = result.current.error as Error & {
            status?: number; response?: { status?: number };
        };
        expect(err.message).toBe('Session expired');
        expect(err.status ?? err.response?.status).toBe(401);
    });

    it('tags 403 when the server body has no message', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: false,
            status: 403,
            statusText: 'Forbidden',
            headers: new Headers({ 'content-type': 'application/json' }),
            json: async () => ({}),
        });
        const { result } = renderHook(() => useReviewItems(true), {
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
