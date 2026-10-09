import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
        },
    });
    return ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

describe('use-review ID encoding', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('encodes the item ID in the approve path', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            headers: new Headers({ 'Content-Type': 'text/plain' }),
            json: async () => ({}),
        });

        const { useApproveReviewItem } = await import('@/hooks/use-review');
        const wrapper = createWrapper();
        const { result } = renderHook(() => useApproveReviewItem(), { wrapper });

        await act(async () => {
            result.current.mutate('item/01?x');
        });

        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalled());
        const [url] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(url).toBe('/api/review/item%2F01%3Fx/approve');
    });

    it('encodes the item ID in the reject path', async () => {
        fetchWithCsrfMock.mockResolvedValue({
            ok: true,
            headers: new Headers({ 'Content-Type': 'text/plain' }),
            json: async () => ({}),
        });

        const { useRejectReviewItem } = await import('@/hooks/use-review');
        const wrapper = createWrapper();
        const { result } = renderHook(() => useRejectReviewItem(), { wrapper });

        await act(async () => {
            result.current.mutate('item/01?x');
        });

        await waitFor(() => expect(fetchWithCsrfMock).toHaveBeenCalled());
        const [url] = fetchWithCsrfMock.mock.calls[0] as [string, RequestInit];
        expect(url).toBe('/api/review/item%2F01%3Fx/reject');
    });
});
