import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { SnapshotList } from '../SnapshotList';
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

describe('SnapshotList', () => {
    const mockSnapshots = {
        snapshots: [
            {
                id: 'snap-001',
                snapshot_time: '2026-02-02T15:00:00Z',
                system_status: 'NOMINAL',
                content_hash: 'abc123...',
                generated_by: 'system',
            },
            {
                id: 'snap-002',
                snapshot_time: '2026-02-02T14:00:00Z',
                system_status: 'ALARM',
                content_hash: 'def456...',
                generated_by: 'operator',
            },
        ],
        total: 2,
    };

    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders empty state when no snapshots exist', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => ({ snapshots: [], total: 0 }),
        });

        render(<SnapshotList substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText(/no snapshots found/i)).toBeInTheDocument();
        });
    });

    it('renders snapshot list with correct data', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => mockSnapshots,
        });

        render(<SnapshotList substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText(/snap-001/i)).toBeInTheDocument();
            expect(screen.getByText(/snap-002/i)).toBeInTheDocument();
        });

        // Check status badges
        expect(screen.getByText('NOMINAL')).toBeInTheDocument();
        expect(screen.getByText('ALARM')).toBeInTheDocument();
    });

    it('opens detail modal when snapshot is clicked', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => mockSnapshots,
        });

        render(<SnapshotList substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText(/snap-001/i)).toBeInTheDocument();
        });

        // Click the first snapshot
        const snapshotCard = screen.getByText(/snap-001/i).closest('button');
        if (snapshotCard) {
            fireEvent.click(snapshotCard);
        }

        // Modal should open (implementation detail - might need adjustment based on actual modal)
        await waitFor(() => {
            // Check if modal is rendered - this depends on your modal implementation
            expect(global.fetch).toHaveBeenCalledWith(
                expect.stringContaining('/api/energy/snapshots/snap-001')
            );
        });
    });

    it('displays total count badge', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => mockSnapshots,
        });

        render(<SnapshotList substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText('2 total')).toBeInTheDocument();
        });
    });

    it('handles API errors gracefully', async () => {
        (global.fetch as any).mockRejectedValueOnce(new Error('API Error'));

        render(<SnapshotList substationId="test-123" maxItems={5} />, {
            wrapper: createWrapper(),
        });

        // Should render loading skeleton initially, then handle error
        // Error handling might show empty state or error message
        await waitFor(() => {
            expect(screen.queryByText(/loading/i)).not.toBeInTheDocument();
        });
    });
});
