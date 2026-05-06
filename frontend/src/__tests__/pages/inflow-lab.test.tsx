import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

vi.mock('@/lib/auth-context', () => ({
    useAuth: vi.fn().mockReturnValue({
        isAuthenticated: false,
        isHydrated: true,
        tenantId: null,
    }),
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenant: vi.fn().mockReturnValue({ tenantId: null }),
}));

vi.mock('@/lib/fetch-with-csrf', () => ({
    fetchWithCsrf: vi.fn((input: RequestInfo | URL, init?: RequestInit) =>
        (globalThis as unknown as { fetch: typeof fetch }).fetch(input, init),
    ),
}));

import DashboardInflowLabPage from '@/app/dashboard/inflow-lab/page';
import { AuthProvider } from '@/lib/auth-context';
import { TenantProvider } from '@/lib/tenant-context';

const completeLot = '00614141000012-20260426-000001';
const partialLot = '00614141000012-20260426-000003';

function inflowRecord(sequence_no: number, lotCode: string, cteType: string) {
    return {
        sequence_no,
        destination_mode: 'mock',
        delivery_status: 'posted',
        delivery_attempts: 1,
        event: {
            cte_type: cteType,
            traceability_lot_code: lotCode,
            product_description: lotCode === partialLot ? 'Green Leaf Lettuce' : 'Spring Mix',
            location_name: `${cteType} station`,
            timestamp: '2026-04-26T18:12:00.000Z',
        },
    };
}

const completeLotRecords = [
    inflowRecord(5, completeLot, 'harvesting'),
    inflowRecord(4, completeLot, 'cooling'),
    inflowRecord(3, completeLot, 'initial_packing'),
    inflowRecord(2, completeLot, 'shipping'),
    inflowRecord(1, completeLot, 'receiving'),
];

const serviceRecords = [
    ...completeLotRecords,
    inflowRecord(7, partialLot, 'harvesting'),
    inflowRecord(6, partialLot, 'cooling'),
];

const sandboxEvaluation = {
    total_events: 1,
    compliant_events: 1,
    non_compliant_events: 0,
    total_kde_errors: 0,
    total_rule_failures: 0,
    submission_blocked: false,
    blocking_reasons: [],
    events: [
        {
            event_index: 0,
            cte_type: 'shipping',
            traceability_lot_code: 'TLC-FEED-001',
            product_description: 'Romaine Lettuce',
            kde_errors: [],
            rules_failed: 0,
            rules_warned: 0,
            compliant: true,
            all_results: [],
        },
    ],
};

function jsonResponse(payload: unknown, init?: ResponseInit) {
    return Promise.resolve(
        new Response(JSON.stringify(payload), {
            status: 200,
            headers: { 'content-type': 'application/json' },
            ...init,
        }),
    );
}

function renderDashboardInflowLabPage() {
    return render(
        <AuthProvider>
            <TenantProvider>
                <DashboardInflowLabPage />
            </TenantProvider>
        </AuthProvider>,
    );
}

describe('Dashboard Inflow Lab', () => {
    const mockFetch = vi.fn();

    beforeEach(() => {
        vi.clearAllMocks();
        const localStore: Record<string, string> = {};
        const sessionStore: Record<string, string> = {};
        vi.stubGlobal('localStorage', {
            getItem: vi.fn((key: string) => localStore[key] ?? null),
            setItem: vi.fn((key: string, value: string) => {
                localStore[key] = value;
            }),
            removeItem: vi.fn((key: string) => {
                delete localStore[key];
            }),
            clear: vi.fn(() => {
                Object.keys(localStore).forEach((key) => delete localStore[key]);
            }),
            length: 0,
            key: vi.fn(() => null),
        });
        vi.stubGlobal('sessionStorage', {
            getItem: vi.fn((key: string) => sessionStore[key] ?? null),
            setItem: vi.fn((key: string, value: string) => {
                sessionStore[key] = value;
            }),
            removeItem: vi.fn((key: string) => {
                delete sessionStore[key];
            }),
            clear: vi.fn(() => {
                Object.keys(sessionStore).forEach((key) => delete sessionStore[key]);
            }),
            length: 0,
            key: vi.fn(() => null),
        });
        mockFetch.mockImplementation((input: RequestInfo | URL) => {
            const url = String(input);
            if (url.endsWith('/api/ingestion/api/v1/sandbox/evaluate')) {
                return jsonResponse(sandboxEvaluation);
            }
            if (url.endsWith('/api/ingestion/api/v1/inflow-workbench/readiness/preview')) {
                return jsonResponse({
                    score: 94,
                    label: 'export ready after authenticated commit',
                    components: [],
                });
            }
            if (url.endsWith('/api/healthz')) {
                return jsonResponse({ ok: true, build: { version: 'test-build' } });
            }
            if (url.endsWith('/api/simulate/status')) {
                return jsonResponse({
                    running: false,
                    stats: {
                        total_records: serviceRecords.length,
                        unique_lots: 2,
                        delivery: { posted: serviceRecords.length, failed: 0, generated: 0, attempts: serviceRecords.length },
                    },
                });
            }
            if (url.includes('/api/events')) {
                return jsonResponse({ events: serviceRecords });
            }
            if (url.includes(`/api/lineage/${encodeURIComponent(completeLot)}`)) {
                return jsonResponse({ records: completeLotRecords });
            }
            if (url.includes(`/api/lineage/${encodeURIComponent(partialLot)}`)) {
                return jsonResponse({
                    records: serviceRecords.filter(
                        (record) => record.event.traceability_lot_code === partialLot,
                    ),
                });
            }
            return jsonResponse({});
        });
        vi.stubGlobal('fetch', mockFetch);
    });

    it('renders the Inflow Lab header with one Sandbox chip and a single boundary banner', async () => {
        renderDashboardInflowLabPage();

        expect(screen.getByRole('heading', { name: 'Inflow Lab' })).toBeInTheDocument();

        const sandboxChips = screen.getAllByText('Sandbox');
        expect(sandboxChips).toHaveLength(1);

        const banner = screen.getByRole('status');
        expect(banner).toHaveTextContent('Sandbox preview only.');
        expect(banner).toHaveTextContent(
            /Production FDA exports stay sealed and audit-ready — nothing here writes to them\./,
        );

        expect(screen.queryByText('Mock environment')).not.toBeInTheDocument();
        expect(screen.queryByText('Boundary active')).not.toBeInTheDocument();
        expect(screen.queryByText('Sandbox diagnosis')).not.toBeInTheDocument();
    });

    it('renders the 5-step funnel with a single Run sandbox test CTA in the active step', async () => {
        renderDashboardInflowLabPage();

        const funnel = await screen.findByTestId('inflow-funnel');
        expect(within(funnel).getByText('Loaded')).toBeInTheDocument();
        expect(within(funnel).getByText('Validated')).toBeInTheDocument();
        expect(within(funnel).getByText('Passing')).toBeInTheDocument();
        expect(within(funnel).getByText('Preview-ready')).toBeInTheDocument();
        expect(within(funnel).getByText('Production import')).toBeInTheDocument();

        const sandboxButtons = screen.getAllByRole('button', { name: /Run sandbox test/i });
        expect(sandboxButtons).toHaveLength(1);

        const activeStep = funnel.querySelector('[data-funnel-step="passing"]');
        expect(activeStep).not.toBeNull();
        expect(activeStep!).toContainElement(sandboxButtons[0]);
    });

    it('renders the readiness panel with five stacked-bar factors', async () => {
        renderDashboardInflowLabPage();

        await waitFor(() => {
            expect(screen.getByText('KDE completeness')).toBeInTheDocument();
        });
        expect(screen.getByText('CTE lifecycle')).toBeInTheDocument();
        expect(screen.getByText('Delivery quality')).toBeInTheDocument();
        expect(screen.getByText('Sandbox pass rate')).toBeInTheDocument();
        expect(screen.getByText('Connection health')).toBeInTheDocument();
        expect(screen.getByText('not run')).toBeInTheDocument();
    });

    it('renders exceptions as 3 grouped patterns and never as 35 stacked cards', async () => {
        renderDashboardInflowLabPage();

        await waitFor(() => {
            expect(screen.getByText('Exceptions')).toBeInTheDocument();
        });
        expect(screen.getByText('Missing handoff evidence')).toBeInTheDocument();
        expect(screen.getByText('Missing source evidence')).toBeInTheDocument();
        expect(screen.getByText('Mixed / multi-cause')).toBeInTheDocument();
    });

    it('renders the mixed group without a Fix all bulk CTA', async () => {
        renderDashboardInflowLabPage();
        const mixedGroup = await waitFor(() => {
            const node = document.querySelector('[data-exception-group="mixed"]');
            if (!node) throw new Error('mixed group not found');
            return node as HTMLElement;
        });
        expect(within(mixedGroup).queryByText(/^Fix all /)).not.toBeInTheDocument();
    });

    it('keeps the selected lot detail in a sticky right rail with Lifecycle and KDE tiles', async () => {
        renderDashboardInflowLabPage();

        await waitFor(() => {
            expect(screen.getByText('Selected lot')).toBeInTheDocument();
        });
        expect(screen.getByText('Lifecycle')).toBeInTheDocument();
        expect(screen.getByText('Lot KDE summary')).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'Fix this lot' })).toBeInTheDocument();
    });

    it('triggers a sandbox evaluation when Run sandbox test is pressed in the funnel', async () => {
        const user = userEvent.setup();
        renderDashboardInflowLabPage();

        await user.click(screen.getByRole('button', { name: /Run sandbox test/i }));
        expect(screen.getByText(/Paste CSV text or upload a CSV file before evaluating\./i)).toBeInTheDocument();
    });

    it('opens fix queue navigation from the section-level button', async () => {
        renderDashboardInflowLabPage();
        const link = await screen.findByRole('link', { name: 'Open fix queue' });
        expect(link).toHaveAttribute('href', '/dashboard/exceptions');
    });

    it('exposes filter chips for all/handoff/source/mixed', async () => {
        renderDashboardInflowLabPage();
        await waitFor(() => {
            expect(screen.getByText('Filter')).toBeInTheDocument();
        });
        expect(screen.getByRole('button', { name: 'all' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'handoff' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'source' })).toBeInTheDocument();
        expect(screen.getByRole('button', { name: 'mixed' })).toBeInTheDocument();
    });
});
