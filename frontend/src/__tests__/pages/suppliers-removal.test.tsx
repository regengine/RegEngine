import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import SupplierDashboardPage from '@/app/dashboard/suppliers/page';

const mocks = vi.hoisted(() => ({
    facilities: vi.fn(),
    checkRemoval: vi.fn(),
    deleteFacility: vi.fn(),
    user: { role_name: 'owner' } as { role_name?: string } | null,
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ isAuthenticated: true, user: mocks.user }),
}));
vi.mock('@/lib/tenant-context', () => ({ useTenant: () => ({ tenantId: null }) }));
vi.mock('@/hooks/use-dashboard-refresh', () => ({ useDashboardRefresh: vi.fn() }));
vi.mock('@/lib/experimental-features', () => ({ experimentalFeaturesEnabled: () => false }));
vi.mock('@/lib/api-hooks', () => ({ fetchWorkbenchReadinessSummary: vi.fn().mockResolvedValue(null) }));
vi.mock('@/lib/api-client', () => ({
    apiClient: {
        listPortalLinks: () => Promise.resolve({ links: [] }),
        listIntegrationProfiles: () => Promise.resolve({ profiles: [] }),
        listSupplierFacilities: mocks.facilities,
        getSupplierComplianceScore: () => Promise.resolve(null),
        getSupplierComplianceGaps: () => Promise.resolve({ gaps: [] }),
        listSupplierTLCs: () => Promise.resolve({ items: [] }),
        getSupplierGapTimeToFix: () => Promise.resolve({ suppliers: [], internal_target_seconds: 86400, evaluated_at: '' }),
        getSupplierDataQuality: () => Promise.resolve({ suppliers: [], window_days: 30, min_records: 20, late_cte_label: '', evaluated_at: '' }),
        checkFacilityRemoval: mocks.checkRemoval,
        deleteSupplierFacility: mocks.deleteFacility,
    },
}));

beforeEach(() => {
    vi.clearAllMocks();
    mocks.user = { role_name: 'owner' };
    mocks.facilities.mockResolvedValue([]);
});

it('renders empty state without Remove action when there are no facilities', async () => {
    mocks.user = { role_name: 'owner' };
    mocks.facilities.mockResolvedValue([]);

    render(<SupplierDashboardPage />);

    expect(await screen.findByRole('button', { name: 'Add Facility' })).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Invite Supplier' }).length).toBeGreaterThan(0);
    expect(screen.getByText('What will populate after setup')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
});

it('does not render Remove action in empty state for non-owner member', async () => {
    mocks.user = { role_name: 'member' };
    mocks.facilities.mockResolvedValue([]);

    render(<SupplierDashboardPage />);

    expect(await screen.findByRole('button', { name: 'Add Facility' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
});

it('displays error callout and no Remove action when facilities fail to load', async () => {
    mocks.facilities.mockRejectedValue(new Error('Network error'));

    render(<SupplierDashboardPage />);

    expect(await screen.findByText('Unable to load supplier data. Please try again.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
});
