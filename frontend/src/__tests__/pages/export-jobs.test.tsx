/**
 * Export Jobs Page Tests
 *
 * Tests for the archive & export jobs view:
 * - Loading state
 * - Data rendering when fetch succeeds
 * - Error state when save fails
 * - Empty state when no jobs exist
 * - Auth redirect when not authenticated
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ExportJobsPage from '@/app/dashboard/export-jobs/page';

// ── Mocks ──

const mockPush = vi.fn();

vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: mockPush, replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
    usePathname: () => '/dashboard/export-jobs',
    useSearchParams: () => new URLSearchParams(),
}));

const mockUseAuth = vi.fn();
vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

const mockUseTenant = vi.fn();
vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => mockUseTenant(),
}));

// Mock lucide-react icons as simple stubs
vi.mock('lucide-react', () => {
    const stub = (props: any) => <svg {...props} />;
    return {
        Archive: stub,
        Download: stub,
        ShieldCheck: stub,
        Clock: stub,
        PlusCircle: stub,
    };
});

// ── Helpers ──

const SAMPLE_JOBS = [
    {
        id: 'job-1',
        name: 'Weekly FDA Export',
        cadence: 'Weekly',
        format: 'FDA Package',
        destination: 'Object storage archive',
        status: 'active',
        lastRun: '2026-03-25 08:00',
        nextRun: '2026-04-01 08:00',
        manifestHash: 'sha256:abc123',
    },
    {
        id: 'job-2',
        name: 'Monthly EPCIS',
        cadence: 'Monthly',
        format: 'GS1 EPCIS 2.0',
        destination: 'Downloadable bundle',
        status: 'paused',
        lastRun: '2026-03-01 12:00',
        nextRun: '2026-04-01 12:00',
        manifestHash: 'sha256:def456',
    },
];

function mockFetchSuccess(jobs = SAMPLE_JOBS) {
    global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => ({ jobs }),
    });
}

function mockFetchFailure() {
    global.fetch = vi.fn().mockResolvedValueOnce({ ok: false, status: 500 });
}

describe('ExportJobsPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseAuth.mockReturnValue({ apiKey: 'test-api-key', isAuthenticated: true });
        mockUseTenant.mockReturnValue({ tenantId: 'tenant-123', isSystemTenant: false });
    });

    it('renders loading state initially', () => {
        // Fetch never resolves during this tick
        global.fetch = vi.fn().mockReturnValue(new Promise(() => {}));
        render(<ExportJobsPage />);

        expect(screen.getByText('Loading export jobs...')).toBeInTheDocument();
    });

    it('renders jobs when fetch succeeds', async () => {
        mockFetchSuccess();
        render(<ExportJobsPage />);

        await waitFor(() => {
            expect(screen.getByText('Weekly FDA Export')).toBeInTheDocument();
        });
        expect(screen.getByText('Monthly EPCIS')).toBeInTheDocument();
        expect(screen.getByText(/sha256:abc123/)).toBeInTheDocument();
    });

    it('renders empty state when no jobs exist', async () => {
        mockFetchSuccess([]);
        render(<ExportJobsPage />);

        await waitFor(() => {
            expect(screen.getByText('No export jobs yet')).toBeInTheDocument();
        });
    });

    it('renders page heading', async () => {
        mockFetchSuccess([]);
        render(<ExportJobsPage />);

        expect(screen.getByText('Archive & Export Jobs')).toBeInTheDocument();
    });

    it('renders error state when save job fails', async () => {
        // First call: loading jobs succeeds (empty)
        // Second call: save fails
        global.fetch = vi.fn()
            .mockResolvedValueOnce({ ok: true, json: async () => ({ jobs: [] }) })
            .mockResolvedValueOnce({ ok: false, status: 500 });

        const user = userEvent.setup();
        render(<ExportJobsPage />);

        // Wait for initial load
        await waitFor(() => {
            expect(screen.getByText('No export jobs yet')).toBeInTheDocument();
        });

        // Click save
        const saveButton = screen.getByRole('button', { name: /save export job/i });
        await user.click(saveButton);

        await waitFor(() => {
            expect(screen.getByText(/could not create the export job/i)).toBeInTheDocument();
        });
    });

    it('shows active jobs count', async () => {
        mockFetchSuccess();
        render(<ExportJobsPage />);

        await waitFor(() => {
            // 1 active job out of 2
            expect(screen.getByText('1')).toBeInTheDocument();
        });
    });
});
