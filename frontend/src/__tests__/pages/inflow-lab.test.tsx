import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import DashboardInflowLabPage from '@/app/dashboard/inflow-lab/page';

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
                return jsonResponse({ records: serviceRecords.filter((record) => record.event.traceability_lot_code === partialLot) });
            }
            return jsonResponse({});
        });
        vi.stubGlobal('fetch', mockFetch);
    });

    it('renders the dashboard Inflow Lab workspace and reports a healthy proxy connection', async () => {
        render(<DashboardInflowLabPage />);

        expect(screen.getByRole('heading', { name: 'Inflow Lab' })).toBeInTheDocument();
        expect(screen.getByText('Mock environment')).toBeInTheDocument();
        expect(screen.getByText('Boundary active')).toBeInTheDocument();
        expect(screen.getByText('Sandbox diagnosis')).toBeInTheDocument();
        expect(screen.getByText('Mock Inflow Lab')).toBeInTheDocument();
        expect(screen.getByText('Authenticated feed')).toBeInTheDocument();
        expect(screen.getByText('Production evidence')).toBeInTheDocument();
        expect(screen.getByText('Authenticated persisted records only')).toBeInTheDocument();

        await waitFor(() => {
            expect(screen.getAllByText('Connection ready').length).toBeGreaterThan(0);
        });
        expect(screen.getAllByText('1 of 2 lots test complete').length).toBeGreaterThan(0);
    });

    it('keeps tab navigation interactive and opens lineage from a selected lot', async () => {
        const user = userEvent.setup();
        render(<DashboardInflowLabPage />);

        await user.click(screen.getByRole('button', { name: 'Lots' }));
        const partialLotCard = await screen.findByRole('button', { name: new RegExp(partialLot) });
        expect(within(partialLotCard).getByText('exception')).toBeInTheDocument();

        await user.click(partialLotCard);

        expect(screen.getByRole('button', { name: 'Lineage' })).toHaveAttribute('aria-pressed', 'true');
        expect(await screen.findByText(`Lineage for ${partialLot}`)).toBeInTheDocument();
        expect(screen.getByText(/Capture missing KDE evidence for initial packing, shipping, DC receiving before this lot is counted as test complete/i)).toBeInTheDocument();
    });

    it('shows export preview copy that keeps partial lots outside production evidence', async () => {
        const user = userEvent.setup();
        render(<DashboardInflowLabPage />);

        await user.click(screen.getByRole('button', { name: 'Lots' }));
        await user.click(await screen.findByRole('button', { name: new RegExp(partialLot) }));
        await user.click(screen.getByRole('button', { name: 'Exports' }));

        expect(screen.getByText(/Selected lot is an exception/i)).toBeInTheDocument();
        expect(screen.getByText(/Includes 1 test-complete lots\. 1 exception lots are flagged for review/i)).toBeInTheDocument();
        expect(screen.getByText(/Production evidence is generated only from authenticated persisted records/i)).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Preview CSV' })).toHaveAttribute(
            'href',
            expect.stringContaining('/api/inflow-lab/api/mock/regengine/export/fda-request'),
        );
    });

    it('makes the feeder-to-production path explicit from the dashboard lab', async () => {
        const user = userEvent.setup();
        render(<DashboardInflowLabPage />);

        await user.click(screen.getByRole('button', { name: 'Data feeder' }));

        expect(screen.getByText('Paste or upload inbound CSV')).toBeInTheDocument();
        expect(screen.getByText(/public stateless sandbox evaluator/i)).toBeInTheDocument();
        expect(screen.getByText(/without being stored or promoted to production ingestion/i)).toBeInTheDocument();
        expect(screen.getByText('Path to production')).toBeInTheDocument();
        expect(screen.getByText('Diagnose free')).toBeInTheDocument();
        expect(screen.getByText('Save as test run')).toBeInTheDocument();
        expect(screen.getAllByText('Generate production evidence').length).toBeGreaterThan(0);
        expect(screen.getByText('Use authenticated persisted records only')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Convert to import mapping' })).toHaveAttribute('href', '/ingest');
        expect(screen.getByRole('link', { name: 'Monitor live feed' })).toHaveAttribute('href', '/dashboard/integrations');
        expect(screen.getByRole('link', { name: 'Generate production evidence' })).toHaveAttribute('href', '/dashboard/export-jobs');
    });

    it('saves evaluated feeder data as a test run without promoting it to evidence', async () => {
        const user = userEvent.setup();
        render(<DashboardInflowLabPage />);

        await user.click(screen.getByRole('button', { name: 'Data feeder' }));
        await user.click(screen.getByRole('button', { name: 'Evaluate data' }));

        expect(await screen.findByText('1 events evaluated')).toBeInTheDocument();
        await user.click(screen.getByRole('button', { name: 'Save test run' }));

        const savedRun = JSON.parse(window.localStorage.getItem('regengine:inflow-lab:last-feeder-run') || '{}');
        expect(savedRun).toMatchObject({
            source: 'inflow-lab-data-feeder',
            csv: expect.stringContaining('traceability_lot_code'),
            result: sandboxEvaluation,
        });
        expect(savedRun.saved_at).toEqual(expect.any(String));
        expect(window.sessionStorage.getItem('regengine:sandbox-handoff')).toBeNull();
        expect(screen.getByText(/Saved /)).toBeInTheDocument();
    });
});
