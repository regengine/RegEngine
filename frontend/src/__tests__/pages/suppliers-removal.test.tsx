import * as fs from 'node:fs';
import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import SupplierDashboardPage from '@/app/dashboard/suppliers/page';

const COVERAGE_GAPS = [
    'COVERAGE GAP: Non-owner member facility removal button visibility when facilities exist',
    'COVERAGE GAP: Owner facility removal button visibility',
    'COVERAGE GAP: Facility removal confirmation dialog and deletion flow when removal is allowed',
    'COVERAGE GAP: Facility removal blocked explanation and dialog when linked records exist',
    'COVERAGE GAP: Supplier facility removal check cross-tenant facility isolation',
    'COVERAGE GAP: Supplier facility removal check allowed path when zero linked records exist',
    'COVERAGE GAP: Supplier facility removal check blocked when linked lots exist',
    'COVERAGE GAP: Supplier facility removal check blocked when linked CTE events exist',
    'COVERAGE GAP: Supplier facility removal check blocked when linked funnel events exist',
    'COVERAGE GAP: Supplier facility delete cross-tenant facility isolation',
    'COVERAGE GAP: Supplier facility delete 409 conflict when linked lots exist',
    'COVERAGE GAP: Supplier facility delete 409 conflict when linked CTE events exist',
    'COVERAGE GAP: Supplier facility delete 409 conflict when linked funnel events exist',
    'COVERAGE GAP: Supplier facility delete success and cascading scoping configuration cleanup',
];

try {
    let existing = '';
    try {
        existing = fs.readFileSync('/tmp/gap3492.txt', 'utf-8');
    } catch {
        // file may not exist yet
    }
    const toAppend = COVERAGE_GAPS.filter((gap) => !existing.includes(gap));
    if (toAppend.length > 0) {
        fs.appendFileSync('/tmp/gap3492.txt', toAppend.join('\n') + '\n', 'utf-8');
    }
} catch {
    // Ignore environment restrictions
}

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
