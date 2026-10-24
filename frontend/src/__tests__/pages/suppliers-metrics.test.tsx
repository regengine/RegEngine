import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import SupplierDashboardPage from '@/app/dashboard/suppliers/page';

const mocks = vi.hoisted(() => ({
    facilities: vi.fn(),
    score: vi.fn(),
    gaps: vi.fn(),
    tlcs: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ isAuthenticated: true }) }));
vi.mock('@/lib/tenant-context', () => ({ useTenant: () => ({ tenantId: null }) }));
vi.mock('@/hooks/use-dashboard-refresh', () => ({ useDashboardRefresh: vi.fn() }));
vi.mock('@/lib/experimental-features', () => ({ experimentalFeaturesEnabled: () => false }));
vi.mock('@/lib/api-hooks', () => ({ fetchWorkbenchReadinessSummary: vi.fn() }));
vi.mock('@/lib/api-client', () => ({
    apiClient: {
        listPortalLinks: () => Promise.resolve({ links: [] }),
        listIntegrationProfiles: () => Promise.resolve({ profiles: [] }),
        listSupplierFacilities: mocks.facilities,
        getSupplierComplianceScore: mocks.score,
        getSupplierComplianceGaps: mocks.gaps,
        listSupplierTLCs: mocks.tlcs,
        getSupplierGapTimeToFix: () => Promise.resolve({ suppliers: [], at_risk_threshold_seconds: 86400, evaluated_at: '' }),
    },
}));

const facility = (id: string, name: string) => ({
    id, name, street: '1 Main', city: 'Salinas', state: 'CA', postal_code: '93901', roles: [],
});

beforeEach(() => {
    vi.clearAllMocks();
    mocks.facilities.mockResolvedValue([facility('f1', 'test'), facility('f2', 'Packhouse')]);
    // f1: no FTL categories scoped -> backend score 0 + one ftl_not_scoped gap.
    mocks.score.mockImplementation((id: string) => Promise.resolve(
        id === 'f1'
            ? { score: 0, required_ctes: 0, coverage_ratio: 0, freshness_ratio: 0, integrity_ratio: 1, covered_ctes: 0, stale_ctes: 0, missing_ctes: 0, total_events: 0, evaluated_at: '' }
            : { score: 56, required_ctes: 2, coverage_ratio: 0.5, freshness_ratio: 0.5, integrity_ratio: 1, covered_ctes: 1, stale_ctes: 0, missing_ctes: 1, total_events: 1, evaluated_at: '' },
    ));
    mocks.gaps.mockImplementation((id: string) => Promise.resolve({
        gaps: id === 'f1'
            ? [{ facility_id: 'f1', facility_name: 'test', cte_type: null, severity: 'high', issue: 'No FTL categories scoped for this facility', reason: 'ftl_not_scoped', last_seen: null }]
            : [{ facility_id: 'f2', facility_name: 'Packhouse', cte_type: 'shipping', severity: 'high', issue: 'Missing required shipping event', reason: 'required_cte_missing', last_seen: null }],
        total: 1, high: 1, medium: 0, low: 0, evaluated_at: '',
    }));
    // f1's lot-code call fails (missing count); f2 has 3 lot codes.
    mocks.tlcs.mockImplementation((id: string) => (
        id === 'f1'
            ? Promise.reject(new Error('boom'))
            : Promise.resolve({ items: [{ id: 't1', facility_id: 'f2', tlc_code: 'L1', status: 'active', event_count: 1, created_at: '2026-10-01T00:00:00Z' }], total: 3 })
    ));
});

it('never renders NaN and defaults a missing lot-code count', async () => {
    render(<SupplierDashboardPage />);
    await screen.findByText('Missing required shipping event');

    expect(document.body.textContent).not.toMatch(/NaN/);
    const tile = screen.getByText('Lot Codes Tracked').parentElement as HTMLElement;
    expect(within(tile).getByText('3')).toBeInTheDocument();
    expect(screen.getByText('No lot code data yet')).toBeInTheDocument();
    expect(screen.getByText('3 lot codes')).toBeInTheDocument();
});

it('shows "No data yet" for lot codes when no facility has a count', async () => {
    mocks.tlcs.mockRejectedValue(new Error('boom'));
    render(<SupplierDashboardPage />);
    await waitFor(() => expect(screen.getAllByText('No lot code data yet')).toHaveLength(2));
    const tile = screen.getByText('Lot Codes Tracked').parentElement as HTMLElement;
    expect(within(tile).getByText('No data yet')).toBeInTheDocument();
    expect(document.body.textContent).not.toMatch(/NaN/);
});

it('keeps status and gap count in agreement and links each gap to its requirement', async () => {
    render(<SupplierDashboardPage />);
    await screen.findByText('No FTL categories scoped for this facility');

    // The "test" facility is still listed (no facility is hidden).
    expect(screen.getByText('test')).toBeInTheDocument();
    expect(screen.queryByText(/Non-Compliant \(0\)/)).not.toBeInTheDocument();
    expect(screen.getByText('Not scoped')).toBeInTheDocument();
    expect(screen.getAllByText('1 gap')).toHaveLength(2);

    expect(screen.getByRole('link', { name: /FDA Food Traceability List/ })).toHaveAttribute(
        'href',
        'https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list',
    );
    expect(screen.getByRole('link', { name: /21 CFR §1\.1340/ })).toHaveAttribute(
        'href',
        'https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1340',
    );
});
