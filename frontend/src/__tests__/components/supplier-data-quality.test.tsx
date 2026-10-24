import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { SupplierDataQuality, SupplierQualityMetric, SupplierQualityRecordsResponse } from '@/types/api';

const mocks = vi.hoisted(() => ({
    getSupplierDataQualityRecords: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
    apiClient: {
        getSupplierDataQualityRecords: (...args: unknown[]) => mocks.getSupplierDataQualityRecords(...args),
    },
}));

import { DataQuality, DRILLDOWN_PAGE_SIZE } from '@/app/dashboard/suppliers/data-quality';

const LATE_LABEL = 'Our measure, based on the agreed sending time with this supplier; not a regulatory requirement';

const metric = (overrides: Partial<SupplierQualityMetric>): SupplierQualityMetric => ({
    key: 'missing_kde',
    status: 'ok',
    numerator: 0,
    denominator: 0,
    share: null,
    reason: null,
    ...overrides,
});

const summary = (metrics: SupplierQualityMetric[]): SupplierDataQuality => ({ supplier_key: 'fac-1', metrics });

const fourMetrics = summary([
    metric({ key: 'missing_kde', status: 'ok', numerator: 5, denominator: 40, share: 0.125 }),
    metric({ key: 'unlinked_lot', status: 'not_enough_data', numerator: 2, denominator: 7, share: null }),
    metric({ key: 'late_cte', status: 'unavailable', numerator: null, denominator: null, reason: 'No agreed sending time is recorded for this supplier, so late records cannot be measured.' }),
    metric({ key: 'epcis_failed', status: 'unavailable', numerator: null, denominator: null, reason: 'No EPCIS file record.' }),
]);

function renderQuality(data: SupplierDataQuality | null = fourMetrics, unavailable = false) {
    return render(
        <DataQuality
            facilityId="fac-1"
            summary={data ?? undefined}
            unavailable={unavailable}
            windowDays={30}
            minRecords={20}
            lateCteLabel={LATE_LABEL}
        />,
    );
}

const page = (overrides: Partial<SupplierQualityRecordsResponse>): SupplierQualityRecordsResponse => ({
    supplier_key: 'fac-1',
    metric: 'missing_kde',
    window_days: 30,
    total: 0,
    limit: DRILLDOWN_PAGE_SIZE,
    offset: 0,
    items: [],
    ...overrides,
});

describe('DataQuality', () => {
    beforeEach(() => {
        mocks.getSupplierDataQualityRecords.mockReset();
    });

    it('shows count of denominator and a share for each metric, with no combined score', () => {
        renderQuality();
        expect(screen.getByText('5 of 40 records (12.5%)')).toBeInTheDocument();
        expect(screen.queryByText(/score/i)).not.toBeInTheDocument();
        expect(screen.getByText('Data quality, records received in the last 30 days')).toBeInTheDocument();
    });

    it('shows Not enough data below the minimum instead of a share', () => {
        renderQuality();
        expect(screen.getByText(/2 of 7 lot codes/)).toBeInTheDocument();
        expect(screen.getByText('Not enough data (fewer than 20)')).toBeInTheDocument();
        expect(screen.queryByText(/28\.6%/)).not.toBeInTheDocument();
    });

    it('shows unavailable metrics with their reason and the late CTE label', () => {
        renderQuality();
        expect(screen.getByText(/Unavailable\. No agreed sending time is recorded/)).toBeInTheDocument();
        expect(screen.getByText(/Unavailable\. No EPCIS file record\./)).toBeInTheDocument();
        expect(screen.getByText(LATE_LABEL)).toBeInTheDocument();
    });

    it('offers drill down only for computable metrics with flagged records', () => {
        renderQuality();
        expect(screen.getAllByRole('button', { name: 'View records' })).toHaveLength(2);
    });

    it('hides drill down when nothing is flagged', () => {
        renderQuality(summary([metric({ key: 'missing_kde', numerator: 0, denominator: 30, share: 0 })]));
        expect(screen.queryByRole('button', { name: 'View records' })).not.toBeInTheDocument();
    });

    it('loads the exact records for a metric and pages with Show more', async () => {
        mocks.getSupplierDataQualityRecords
            .mockResolvedValueOnce(
                page({
                    total: 2,
                    items: [
                        {
                            record_id: 'rec-1',
                            lot_id: null,
                            lot_code: 'TLC-1',
                            cte_type: 'shipping',
                            event_time: null,
                            received_at: null,
                            missing_kdes: ['reference_document', 'quantity'],
                        },
                    ],
                }),
            )
            .mockResolvedValueOnce(
                page({
                    total: 2,
                    offset: 1,
                    items: [
                        {
                            record_id: 'rec-2',
                            lot_id: null,
                            lot_code: 'TLC-2',
                            cte_type: 'receiving',
                            event_time: null,
                            received_at: null,
                            missing_kdes: ['tlc_source_reference'],
                        },
                    ],
                }),
            );
        renderQuality();

        fireEvent.click(screen.getAllByRole('button', { name: 'View records' })[0]);
        await waitFor(() => expect(screen.getByText('rec-1')).toBeInTheDocument());
        expect(screen.getByText('Missing: reference_document, quantity')).toBeInTheDocument();
        expect(mocks.getSupplierDataQualityRecords).toHaveBeenCalledWith('fac-1', 'missing_kde', {
            windowDays: 30,
            limit: DRILLDOWN_PAGE_SIZE,
            offset: 0,
        });

        fireEvent.click(screen.getByRole('button', { name: 'Show more (1 of 2)' }));
        await waitFor(() => expect(screen.getByText('rec-2')).toBeInTheDocument());
        expect(mocks.getSupplierDataQualityRecords).toHaveBeenLastCalledWith('fac-1', 'missing_kde', {
            windowDays: 30,
            limit: DRILLDOWN_PAGE_SIZE,
            offset: 1,
        });
        expect(screen.queryByRole('button', { name: /Show more/ })).not.toBeInTheDocument();
    });

    it('lists unlinked lot codes', async () => {
        mocks.getSupplierDataQualityRecords.mockResolvedValueOnce(
            page({
                metric: 'unlinked_lot',
                total: 1,
                items: [
                    {
                        record_id: null,
                        lot_id: 'lot-9',
                        lot_code: 'TLC-9',
                        cte_type: null,
                        event_time: null,
                        received_at: null,
                        missing_kdes: [],
                    },
                ],
            }),
        );
        renderQuality();
        fireEvent.click(screen.getAllByRole('button', { name: 'View records' })[1]);
        await waitFor(() => expect(screen.getByText('Lot TLC-9')).toBeInTheDocument());
        expect(mocks.getSupplierDataQualityRecords).toHaveBeenCalledWith('fac-1', 'unlinked_lot', expect.anything());
    });

    it('says so when the records request fails', async () => {
        mocks.getSupplierDataQualityRecords.mockRejectedValueOnce(new Error('boom'));
        renderQuality();
        fireEvent.click(screen.getAllByRole('button', { name: 'View records' })[0]);
        await waitFor(() => expect(screen.getByText('Records could not be loaded')).toBeInTheDocument());
    });

    it('shows unavailable when the summary request failed', () => {
        renderQuality(null, true);
        expect(screen.getByText('Data quality unavailable')).toBeInTheDocument();
    });

    it('shows No data for a facility missing from the response', () => {
        renderQuality(null, false);
        expect(screen.getByText('Data quality: No data')).toBeInTheDocument();
    });
});
