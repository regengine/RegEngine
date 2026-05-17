import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
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

    it('exposes Inflow Lab as a top-level active dashboard link while collapsed submenu links stay unmounted', async () => {
        const user = userEvent.setup();

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

        const intakeButton = screen.getByRole('button', { name: /Intake/i });
        expect(intakeButton).toHaveAttribute('aria-expanded', 'false');
        expect(screen.queryByRole('link', { name: /Import files/i })).not.toBeInTheDocument();

        await user.click(intakeButton);

        expect(intakeButton).toHaveAttribute('aria-expanded', 'true');
        expect(screen.getByRole('link', { name: /Import files/i })).toHaveAttribute('href', '/ingest');
        expect(screen.getByRole('link', { name: /Integration registry/i })).toHaveAttribute(
            'href',
            '/dashboard/integrations',
        );
    });

    it('keeps the mobile quick navigation visible without horizontal scrolling and uses 44px targets', () => {
        render(
            <DashboardLayout>
                <div>Inflow content</div>
            </DashboardLayout>,
        );

        const quickNav = screen.getByRole('navigation', { name: /Dashboard quick navigation/i });
        expect(quickNav).toHaveClass('grid', 'grid-cols-5', 'overflow-hidden');
        expect(quickNav).not.toHaveClass('overflow-x-auto');

        const expectedLinks = [
            ['Overview', '/dashboard'],
            ['Inflow Lab', '/dashboard/inflow-lab'],
            ['Compliance', '/dashboard/compliance'],
            ['Alerts', '/dashboard/alerts'],
            ['FDA Export', '/dashboard/export-jobs'],
        ];

        expectedLinks.forEach(([name, href]) => {
            const link = screen.getAllByRole('link', { name: new RegExp(name, 'i') }).find((node) => {
                return node.closest('nav')?.getAttribute('aria-label') === 'Dashboard quick navigation';
            });

            expect(link).toBeDefined();
            expect(link).toHaveAttribute('href', href);
            expect(link).toHaveClass('min-h-[44px]', 'min-w-0');
        });
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
