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
        mockFetch.mockImplementation((input: RequestInfo | URL) => {
            const url = String(input);
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
        expect(screen.getByText('Test environment')).toBeInTheDocument();

        await waitFor(() => {
            expect(screen.getAllByText('Connection ready').length).toBeGreaterThan(0);
        });
        expect(screen.getAllByText('1 of 2 lots export ready').length).toBeGreaterThan(0);
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
        expect(screen.getByText(/Capture missing KDE evidence for initial packing, shipping, DC receiving/i)).toBeInTheDocument();
    });

    it('shows export readiness copy that keeps partial lots visible but outside the ready package', async () => {
        const user = userEvent.setup();
        render(<DashboardInflowLabPage />);

        await user.click(screen.getByRole('button', { name: 'Lots' }));
        await user.click(await screen.findByRole('button', { name: new RegExp(partialLot) }));
        await user.click(screen.getByRole('button', { name: 'Exports' }));

        expect(screen.getByText(/Selected lot is an exception/i)).toBeInTheDocument();
        expect(screen.getByText(/Includes 1 ready lots\. 1 exception lots are flagged for review, not counted as ready/i)).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Download CSV' })).toHaveAttribute(
            'href',
            expect.stringContaining('/api/inflow-lab/api/mock/regengine/export/fda-request'),
        );
    });
});
