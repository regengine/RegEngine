import { beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { CuratorReview } from '@/components/dashboard/curator-review';

const fetchWithCsrfMock = vi.hoisted(() => vi.fn());
const mockUseAuth = vi.hoisted(() => vi.fn());

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: (...args: any[]) => fetchWithCsrfMock(...args),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/components/ui/badge', () => ({
    Badge: ({ children, ...props }: any) => <span {...props}>{children}</span>,
}));

vi.mock('@/components/ui/button', () => ({
    Button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
}));

vi.mock('@/components/ui/card', () => ({
    Card: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardHeader: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardTitle: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardContent: ({ children, ...props }: any) => <div {...props}>{children}</div>,
}));

vi.mock('@/components/ui/spinner', () => ({
    Spinner: () => <div>Loading...</div>,
}));

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false, gcTime: Infinity },
            mutations: { retry: false, gcTime: Infinity },
        },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

describe('CuratorReview', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('does not fetch the review queue without admin capability', () => {
        mockUseAuth.mockReturnValue({
            hasAdminSession: false,
        });

        render(<CuratorReview />, { wrapper: createWrapper() });

        expect(screen.getByText(/workspace admin or sysadmin access is required/i)).toBeInTheDocument();
        expect(fetchWithCsrfMock).not.toHaveBeenCalled();
    });

    it('loads and approves items through same-origin review routes without browser admin headers', async () => {
        mockUseAuth.mockReturnValue({
            hasAdminSession: true,
        });

        fetchWithCsrfMock
            .mockResolvedValueOnce({
                ok: true,
                headers: new Headers({ 'Content-Type': 'application/json' }),
                json: async () => ([
                    {
                        id: 'rev-1',
                        confidence_score: 0.92,
                        source_text: 'Lot TLC-1 matched source text',
                        extracted_data: { lot_code: 'TLC-1' },
                        status: 'PENDING',
                        created_at: '2026-05-07T00:00:00.000Z',
                        updated_at: '2026-05-07T00:00:00.000Z',
                        tenant_id: 'tenant-123',
                    },
                ]),
            })
            .mockResolvedValueOnce({
                ok: true,
                headers: new Headers({ 'Content-Type': 'application/json' }),
                json: async () => ({ ok: true }),
            })
            .mockResolvedValueOnce({
                ok: true,
                headers: new Headers({ 'Content-Type': 'application/json' }),
                json: async () => ([]),
            });

        const user = userEvent.setup();
        render(<CuratorReview />, { wrapper: createWrapper() });

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalledWith(
                '/api/review/items',
                expect.objectContaining({
                    credentials: 'include',
                    headers: { 'Content-Type': 'application/json' },
                }),
            );
        });

        const approveButton = await screen.findByRole('button', { name: 'Approve' });
        await user.click(approveButton);

        await waitFor(() => {
            expect(fetchWithCsrfMock).toHaveBeenCalledTimes(3);
        });

        const [url, init] = fetchWithCsrfMock.mock.calls[1] as [string, RequestInit];
        const headers = new Headers(init.headers);

        expect(url).toBe('/api/review/rev-1/approve');
        expect(init.method).toBe('POST');
        expect(init.credentials).toBe('include');
        expect(headers.get('Content-Type')).toBe('application/json');
        expect(headers.get('X-Admin-Key')).toBeNull();
    });
});
