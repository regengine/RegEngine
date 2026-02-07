import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuditHistoryTimeline } from '../AuditHistoryTimeline';
import { vi } from 'vitest';

global.fetch = vi.fn();

const createWrapper = () => {
    const queryClient = new QueryClient({
        defaultOptions: {
            queries: { retry: false },
        },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
};

describe('AuditHistoryTimeline', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders empty state when no history exists', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ verified: 0, corrupted: 0 }),
        });

        render(<AuditHistoryTimeline substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText(/no verification history/i)).toBeInTheDocument();
        });
    });

    it('displays verification success events', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ verified: 100, corrupted: 0 }),
        });

        render(<AuditHistoryTimeline substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText(/chain verified/i)).toBeInTheDocument();
            expect(screen.getByText(/100 snapshots/i)).toBeInTheDocument();
        });
    });

    it('displays corruption detection events with warning', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ verified: 95, corrupted: 5 }),
        });

        render(<AuditHistoryTimeline substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText(/corruption detected/i)).toBeInTheDocument();
            expect(screen.getByText(/failed: 5/i)).toBeInTheDocument();
        });
    });

    it('shows relative timestamps', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ verified: 100, corrupted: 0 }),
        });

        render(<AuditHistoryTimeline substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            // Should show "X seconds ago" or similar using date-fns
            expect(screen.getByText(/ago/i)).toBeInTheDocument();
        });
    });

    it('handles API errors gracefully', async () => {
        (global.fetch as any).mockRejectedValueOnce(new Error('Network error'));

        render(<AuditHistoryTimeline substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        // Should render without crashing and show empty state
        await waitFor(() => {
            expect(screen.queryByText(/chain verified/i)).not.toBeInTheDocument();
        });
    });
});
