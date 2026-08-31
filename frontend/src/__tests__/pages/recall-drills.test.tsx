/** Release-disabled recall automation must remain local and non-networked. */

import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RecallDrillsPage from '@/app/dashboard/recall-drills/page';

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
    usePathname: () => '/dashboard/recall-drills',
    useSearchParams: () => new URLSearchParams(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ apiKey: null, isAuthenticated: true }),
}));

vi.mock('lucide-react', () => {
    const stub = (props: React.SVGProps<SVGSVGElement>) => <svg {...props} />;
    return {
        PlayCircle: stub,
        ShieldAlert: stub,
        TimerReset: stub,
        FileText: stub,
        Link2Off: stub,
    };
});

describe('RecallDrillsPage release boundary', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubGlobal('fetch', vi.fn());
    });

    it('renders the Recall Drills page', () => {
        render(<RecallDrillsPage />, { wrapper: createWrapper() });

        expect(screen.getByRole('heading', { name: 'Recall Drills' })).toBeInTheDocument();
    });

    it('renders the local unavailable state and disables automation', async () => {
        render(<RecallDrillsPage />, { wrapper: createWrapper() });

        expect(await screen.findByText(/Automated drill scheduling is still in development/i)).toBeInTheDocument();
        expect(screen.getByRole('button', { name: /start drill/i })).toBeDisabled();
    });

    it('never calls the retired anonymous customer-readiness BFF', async () => {
        render(<RecallDrillsPage />, { wrapper: createWrapper() });

        await screen.findByText(/Automated drill scheduling is still in development/i);
        expect(global.fetch).not.toHaveBeenCalled();
    });
});
