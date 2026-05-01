import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import DashboardLayout from '@/app/dashboard/layout';
import { useAuth } from '@/lib/auth-context';
import { usePathname, useRouter } from 'next/navigation';

vi.mock('next/navigation', () => ({
    usePathname: vi.fn(),
    useRouter: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn(),
}));

vi.mock('@/components/dashboard/breadcrumb', () => ({
    DashboardBreadcrumb: () => <nav aria-label="Breadcrumb" />,
}));

vi.mock('@/components/dashboard/error-boundary', () => ({
    DashboardErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

describe('Dashboard navigation discoverability', () => {
    const mockPush = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        (useRouter as any).mockReturnValue({ push: mockPush });
        (usePathname as any).mockReturnValue('/dashboard/inflow-lab');
        (useAuth as any).mockReturnValue({
            clearCredentials: vi.fn(),
            demoMode: false,
            isAuthenticated: true,
            isHydrated: true,
        });
        const store: Record<string, string> = {};
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((key: string) => store[key] ?? null),
            setItem: vi.fn((key: string, value: string) => {
                store[key] = value;
            }),
            removeItem: vi.fn((key: string) => {
                delete store[key];
            }),
            clear: vi.fn(() => {
                Object.keys(store).forEach((key) => delete store[key]);
            }),
            length: 0,
            key: vi.fn(() => null),
        });
    });

    it('exposes Inflow Lab as a top-level active dashboard link', async () => {
        render(
            <DashboardLayout>
                <div>Inflow content</div>
            </DashboardLayout>,
        );

        const inflowLink = screen
            .getAllByText('Inflow Lab')
            .map((node) => node.closest('a'))
            .find((link) => link?.getAttribute('aria-current') === 'page');
        expect(inflowLink).not.toBeNull();
        expect(inflowLink).toHaveAttribute('href', '/dashboard/inflow-lab');
        expect(inflowLink).toHaveAttribute('aria-current', 'page');
        expect(screen.getByRole('button', { name: /Intake/i })).toBeInTheDocument();
        expect(screen.getAllByText('Import files')[0].closest('a')).toHaveAttribute('href', '/ingest');
    });

    it('redirects unauthenticated visitors back to login with the Inflow Lab return path', async () => {
        (useAuth as any).mockReturnValue({
            clearCredentials: vi.fn(),
            demoMode: false,
            isAuthenticated: false,
            isHydrated: true,
        });

        render(
            <DashboardLayout>
                <div>Protected content</div>
            </DashboardLayout>,
        );

        await waitFor(() => {
            expect(mockPush).toHaveBeenCalledWith('/login?next=%2Fdashboard%2Finflow-lab');
        });
        expect(screen.queryByText('Protected content')).not.toBeInTheDocument();
    });
});
