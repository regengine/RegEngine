import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SupplierDashboardPage from '@/app/dashboard/suppliers/page';

const mocks = vi.hoisted(() => ({
    facilities: vi.fn(),
    checkRemoval: vi.fn(),
    deleteFacility: vi.fn(),
    user: { id: 'u-1', email: 'u1@example.com', role_name: 'owner' } as { id: string; email: string; role_name?: string } | null,
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ isAuthenticated: true, user: mocks.user }),
}));
vi.mock('@/lib/tenant-context', () => ({ useTenant: () => ({ tenantId: 't-1' }) }));
vi.mock('@/hooks/use-dashboard-refresh', () => ({ useDashboardRefresh: vi.fn() }));
vi.mock('@/lib/experimental-features', () => ({ experimentalFeaturesEnabled: () => false }));
vi.mock('@/lib/api-hooks', () => ({ fetchWorkbenchReadinessSummary: vi.fn().mockResolvedValue(null) }));
vi.mock('@/lib/api-client', () => ({
    apiClient: {
        listPortalLinks: () => Promise.resolve({ links: [] }),
        listIntegrationProfiles: () => Promise.resolve({ profiles: [] }),
        listSupplierFacilities: mocks.facilities,
        getSupplierComplianceScore: () => Promise.resolve({
            score: 100, required_ctes: 1, coverage_ratio: 1, freshness_ratio: 1, integrity_ratio: 1, covered_ctes: 1, stale_ctes: 0, missing_ctes: 0, total_events: 1, evaluated_at: '',
        }),
        getSupplierComplianceGaps: () => Promise.resolve({ gaps: [], total: 0, high: 0, medium: 0, low: 0, evaluated_at: '' }),
        listSupplierTLCs: () => Promise.resolve({ items: [], total: 0 }),
        checkFacilityRemoval: mocks.checkRemoval,
        deleteSupplierFacility: mocks.deleteFacility,
    },
}));

const facility = (id: string, name: string) => ({
    id,
    name,
    street: 'street-1',
    city: 'city-1',
    state: 'ST',
    postal_code: '00000',
    roles: [],
});

beforeEach(() => {
    vi.clearAllMocks();
    mocks.user = { id: 'u-1', email: 'u1@example.com', role_name: 'owner' };
    mocks.facilities.mockResolvedValue([facility('f-1', 'fac-1')]);
});

it('does not render Remove button for non-owner member', async () => {
    mocks.user = { id: 'u-2', email: 'u2@example.com', role_name: 'member' };
    render(<SupplierDashboardPage />);
    await screen.findByText('fac-1');

    expect(screen.getByRole('button', { name: 'FDA Export' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Remove' })).not.toBeInTheDocument();
});

it('renders Remove button for owner', async () => {
    mocks.user = { id: 'u-1', email: 'u1@example.com', role_name: 'owner' };
    render(<SupplierDashboardPage />);
    await screen.findByText('fac-1');

    expect(screen.getByRole('button', { name: 'Remove' })).toBeInTheDocument();
});

it('opens confirm dialog with facility details and allows removal when zero linked records', async () => {
    const user = userEvent.setup();
    mocks.user = { id: 'u-1', email: 'u1@example.com', role_name: 'owner' };
    mocks.checkRemoval.mockResolvedValue({
        facility_id: 'f-1',
        facility_name: 'fac-1',
        allowed: true,
        linked_counts: { lots: 0, events: 0, records: 0, scoping_config: 2 },
        lots_count: 0,
        cte_events_count: 0,
        funnel_events_count: 0,
        scoping_config_count: 2,
        address: {
            street: 'street-1',
            city: 'city-1',
            state: 'ST',
            postal_code: '00000',
        },
    });
    mocks.deleteFacility.mockResolvedValue({ status: 'deleted', id: 'f-1' });

    render(<SupplierDashboardPage />);
    await screen.findByText('fac-1');

    const removeBtn = screen.getByRole('button', { name: 'Remove' });
    await user.click(removeBtn);

    expect(mocks.checkRemoval).toHaveBeenCalledWith('f-1');

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByRole('heading', { name: 'Remove facility?' })).toBeInTheDocument();
    expect(within(dialog).getByText('fac-1')).toBeInTheDocument();
    expect(within(dialog).getByText(/street-1, city-1, ST 00000/)).toBeInTheDocument();
    expect(within(dialog).getByText(/2 FTL scoping category configuration\(s\)/)).toBeInTheDocument();

    const confirmBtn = within(dialog).getByRole('button', { name: 'Remove facility' });
    await user.click(confirmBtn);

    expect(mocks.deleteFacility).toHaveBeenCalledWith('f-1');
    await waitFor(() => {
        expect(screen.queryByText('fac-1')).not.toBeInTheDocument();
    });
});

it('shows explanation with linked counts and no remove button when removal is blocked', async () => {
    const user = userEvent.setup();
    mocks.user = { id: 'u-1', email: 'u1@example.com', role_name: 'owner' };
    mocks.checkRemoval.mockResolvedValue({
        facility_id: 'f-1',
        facility_name: 'fac-1',
        allowed: false,
        linked_counts: { lots: 3, events: 5, records: 2, scoping_config: 1 },
        lots_count: 3,
        cte_events_count: 5,
        funnel_events_count: 2,
        scoping_config_count: 1,
        address: {
            street: 'street-1',
            city: 'city-1',
            state: 'ST',
            postal_code: '00000',
        },
    });

    render(<SupplierDashboardPage />);
    await screen.findByText('fac-1');

    const removeBtn = screen.getByRole('button', { name: 'Remove' });
    await user.click(removeBtn);

    expect(mocks.checkRemoval).toHaveBeenCalledWith('f-1');

    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('Facility Cannot Be Removed')).toBeInTheDocument();
    expect(within(dialog).getByText('3')).toBeInTheDocument();
    expect(within(dialog).getByText('5')).toBeInTheDocument();
    expect(within(dialog).getByText('2')).toBeInTheDocument();

    expect(within(dialog).queryByRole('button', { name: 'Remove facility' })).not.toBeInTheDocument();
    expect(within(dialog).getByRole('button', { name: 'Done' })).toBeInTheDocument();
});
