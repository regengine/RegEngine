import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { VerificationWidget } from '../VerificationWidget';
import { vi } from 'vitest';

// Mock fetch
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

describe('VerificationWidget', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('renders loading state initially', () => {
        (global.fetch as any).mockImplementation(() => new Promise(() => { }));

        render(<VerificationWidget substationId="test-123" />, {
            wrapper: createWrapper(),
        });

        expect(screen.getByText(/chain integrity/i)).toBeInTheDocument();
    });

    it('displays verification success when all checks pass', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                content_hash_valid: true,
                signature_valid: true,
                chain_linked: true,
                snapshot_id: 'snap-123',
                verified_at: new Date().toISOString(),
            }),
        });

        render(<VerificationWidget substationId="test-123" />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText(/content hash/i)).toBeInTheDocument();
        });

        // Should show green check marks for all verifications
        const checkMarks = screen.getAllByText('✓');
        expect(checkMarks.length).toBeGreaterThan(0);
    });

    it('displays alert when corruption is detected', async () => {
        (global.fetch as any).mockResolvedValueOnce({
            ok: true,
            json: async () => ({
                content_hash_valid: false,
                signature_valid: true,
                chain_linked: true,
                snapshot_id: 'snap-123',
                verified_at: new Date().toISOString(),
            }),
        });

        render(<VerificationWidget substationId="test-123" />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText(/chain corruption detected/i)).toBeInTheDocument();
        });
    });

    it('handles API errors gracefully', async () => {
        (global.fetch as any).mockRejectedValueOnce(new Error('Network error'));

        render(<VerificationWidget substationId="test-123" />, {
            wrapper: createWrapper(),
        });

        await waitFor(() => {
            expect(screen.getByText(/failed to verify/i)).toBeInTheDocument();
        });
    });

    it('auto-refreshes every 60 seconds', async () => {
        vi.useFakeTimers();

        (global.fetch as any).mockResolvedValue({
            ok: true,
            json: async () => ({
                content_hash_valid: true,
                signature_valid: true,
                chain_linked: true,
                snapshot_id: 'snap-123',
                verified_at: new Date().toISOString(),
            }),
        });

        render(<VerificationWidget substationId="test-123" />, {
            wrapper: createWrapper(),
        });

        // Initial fetch
        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledTimes(1);
        });

        // Fast-forward 60 seconds
        vi.advanceTimersByTime(60000);

        await waitFor(() => {
            expect(global.fetch).toHaveBeenCalledTimes(2);
        });

        vi.useRealTimers();
    });
});
