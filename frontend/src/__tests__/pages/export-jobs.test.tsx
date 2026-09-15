/** Release-disabled export scheduling must remain local and non-networked. */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ExportJobsPage from '@/app/dashboard/export-jobs/page';

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

vi.mock('next/navigation', () => ({
    useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
    usePathname: () => '/dashboard/export-jobs',
    useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ apiKey: null, isAuthenticated: true }),
}));

vi.mock('lucide-react', () => {
    const stub = (props: React.SVGProps<SVGSVGElement>) => <svg {...props} />;
    return {
        Archive: stub,
        Download: stub,
        ShieldCheck: stub,
        Clock: stub,
        PlusCircle: stub,
        Link2Off: stub,
        Database: stub,
        Upload: stub,
        ArrowRight: stub,
        CheckCircle2: stub,
        // The shared design-system primitives (Callout, StatusBadge, StatTile,
        // DataTable, Field, Button) build their icon maps at module scope, so
        // every icon they reference must exist on this mock or the import
        // throws before a single assertion runs.
        AlertCircle: stub,
        AlertTriangle: stub,
        ArrowDown: stub,
        ArrowDownRight: stub,
        ArrowUp: stub,
        ArrowUpDown: stub,
        ArrowUpRight: stub,
        HelpCircle: stub,
        Info: stub,
        Loader2: stub,
        Minus: stub,
        RefreshCw: stub,
        Search: stub,
        X: stub,
        XCircle: stub,
    };
});

describe('ExportJobsPage release boundary', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubGlobal('fetch', vi.fn());
    });

    it('renders the FDA Export page', () => {
        render(<ExportJobsPage />, { wrapper: createWrapper() });

        expect(screen.getByRole('heading', { name: 'FDA Export' })).toBeInTheDocument();
    });

    it('renders the local unavailable state and disables scheduling', async () => {
        render(<ExportJobsPage />, { wrapper: createWrapper() });

        expect(await screen.findByText(/Scheduled export jobs aren.t available/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /save export job/i })).toBeDisabled();
    });

    it('never calls the retired anonymous customer-readiness BFF', async () => {
        render(<ExportJobsPage />, { wrapper: createWrapper() });

        await screen.findByText(/Scheduled export jobs aren.t available/i);
        expect(global.fetch).not.toHaveBeenCalled();
    });
});
