import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import AuditReviewPage from '@/app/audit/page';
import DashboardLayout from '@/app/dashboard/layout';
import DashboardInflowLabPage from '@/app/dashboard/inflow-lab/page';
import DashboardScanPage from '@/app/dashboard/scan/page';
import FSMAFieldCapturePage from '@/app/fsma/field-capture/page';
import { ToolsLandingClient } from '@/app/tools/components/ToolsLandingClient';
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

vi.mock('@/app/tools/inflow-lab/components/DashboardInflowLab', () => ({
    DashboardInflowLab: () => <div data-testid="inflow-lab-dashboard" />,
}));

vi.mock('@/components/mobile/FieldCaptureClient', () => ({
    FieldCaptureClient: () => <div data-testid="field-capture-client" />,
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenant: vi.fn(() => ({ tenantId: 'tenant-1' })),
}));

describe('experimental feature gating (flag off)', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '');
        (useRouter as any).mockReturnValue({ push: vi.fn() });
        (usePathname as any).mockReturnValue('/dashboard');
        (useAuth as any).mockReturnValue({
            clearCredentials: vi.fn(),
            demoMode: false,
            isAuthenticated: true,
            isHydrated: true,
            tenantId: 'tenant-1',
            user: { id: 'u1', email: 'user@example.com', is_sysadmin: false, status: 'active' },
        });
    });

    afterEach(() => {
        vi.unstubAllEnvs();
    });

    it('renders a feature-not-enabled state instead of the audit page', () => {
        render(<AuditReviewPage />);
        expect(screen.getByTestId('feature-not-enabled')).toBeInTheDocument();
        expect(screen.getByText(/Audit review is not enabled/i)).toBeInTheDocument();
    });

    it('renders a feature-not-enabled state instead of the dashboard Inflow Lab', () => {
        render(<DashboardInflowLabPage />);
        expect(screen.getByTestId('feature-not-enabled')).toBeInTheDocument();
        expect(screen.queryByTestId('inflow-lab-dashboard')).not.toBeInTheDocument();
    });

    it('renders a feature-not-enabled state instead of the field capture scanner', () => {
        render(<FSMAFieldCapturePage />);
        expect(screen.getByTestId('feature-not-enabled')).toBeInTheDocument();
        expect(screen.queryByTestId('field-capture-client')).not.toBeInTheDocument();
    });

    it('renders a feature-not-enabled state instead of the scan launcher', () => {
        render(<DashboardScanPage />);
        expect(screen.getByTestId('feature-not-enabled')).toBeInTheDocument();
    });

    it('hides experimental items from the dashboard nav', () => {
        render(
            <DashboardLayout>
                <div>content</div>
            </DashboardLayout>,
        );
        expect(screen.queryByText('Inflow Lab')).not.toBeInTheDocument();
        expect(screen.queryByText('Readiness')).not.toBeInTheDocument();
        expect(screen.queryByText('Scan')).not.toBeInTheDocument();
        // Stable items remain
        expect(screen.getAllByText('Compliance').length).toBeGreaterThan(0);
    });

    it('hides experimental tools from the tools landing grid', () => {
        render(<ToolsLandingClient />);
        expect(screen.queryByText('Inflow Lab')).not.toBeInTheDocument();
        expect(screen.getByText('FTL Coverage Checker')).toBeInTheDocument();
    });
});

describe('experimental feature gating (flag on)', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', 'true');
        (useRouter as any).mockReturnValue({ push: vi.fn() });
        (usePathname as any).mockReturnValue('/dashboard');
        (useAuth as any).mockReturnValue({
            clearCredentials: vi.fn(),
            demoMode: false,
            isAuthenticated: true,
            isHydrated: true,
            tenantId: 'tenant-1',
            user: { id: 'u1', email: 'user@example.com', is_sysadmin: false, status: 'active' },
        });
    });

    afterEach(() => {
        vi.unstubAllEnvs();
    });

    it('keeps experimental items in the dashboard nav', () => {
        render(
            <DashboardLayout>
                <div>content</div>
            </DashboardLayout>,
        );
        expect(screen.getAllByText('Inflow Lab').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Readiness').length).toBeGreaterThan(0);
        expect(screen.getAllByText('Scan').length).toBeGreaterThan(0);
    });

    it('renders the real dashboard Inflow Lab page', () => {
        render(<DashboardInflowLabPage />);
        expect(screen.getByTestId('inflow-lab-dashboard')).toBeInTheDocument();
        expect(screen.queryByTestId('feature-not-enabled')).not.toBeInTheDocument();
    });

    it('renders the real field capture scanner', () => {
        render(<FSMAFieldCapturePage />);
        expect(screen.getByTestId('field-capture-client')).toBeInTheDocument();
        expect(screen.queryByTestId('feature-not-enabled')).not.toBeInTheDocument();
    });

    it('shows experimental tools on the tools landing grid', () => {
        render(<ToolsLandingClient />);
        expect(screen.getByText('Inflow Lab')).toBeInTheDocument();
    });
});
