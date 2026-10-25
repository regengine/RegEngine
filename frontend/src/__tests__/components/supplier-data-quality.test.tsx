import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { SupplierDataQuality, SupplierQualityMetric, SupplierQualityRecordsResponse } from '@/types/api';

const mocks = vi.hoisted(() => ({
    getSupplierDataQualityRecords: vi.fn(),
    setFacilityAgreedSendingHours: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
    apiClient: {
        getSupplierDataQualityRecords: (...args: unknown[]) => mocks.getSupplierDataQualityRecords(...args),
        setFacilityAgreedSendingHours: (...args: unknown[]) => mocks.setFacilityAgreedSendingHours(...args),
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

const FACILITY_ID = crypto.randomUUID();
const MIN_RECORDS = 20;
const WINDOW_DAYS = 30;
const uuids = (length: number) => Array.from({ length }, () => crypto.randomUUID());
// Generated inputs: records clear MIN_RECORDS, lots fall one short of it.
// Every other record and lot is flagged, so counts come from these arrays.
const RECORD_IDS = uuids(MIN_RECORDS * 2);
const FLAGGED_RECORD_IDS = RECORD_IDS.filter((_, index) => index % 2 === 0);
const LOT_IDS = uuids(MIN_RECORDS - 1);
const UNLINKED_LOT_IDS = LOT_IDS.filter((_, index) => index % 2 === 0);
const MISSING = { numerator: FLAGGED_RECORD_IDS.length, denominator: RECORD_IDS.length };
const UNLINKED = { numerator: UNLINKED_LOT_IDS.length, denominator: LOT_IDS.length };
const LATE_RECORD_IDS = uuids(MIN_RECORDS);
const LATE_FLAGGED_IDS = LATE_RECORD_IDS.filter((_, index) => index % 2 === 0);
const LATE = { numerator: LATE_FLAGGED_IDS.length, denominator: LATE_RECORD_IDS.length };
// Any positive whole number of hours; derived rather than picked.
const AGREED_HOURS = MIN_RECORDS;
const LATE_REASON = crypto.randomUUID();
const EPCIS_REASON = crypto.randomUUID();
const missingShare = MISSING.numerator / MISSING.denominator;
const formatShare = (share: number) => `${Math.round(share * 1000) / 10}%`;

const summary = (metrics: SupplierQualityMetric[], agreedSendingHours: number | null = null): SupplierDataQuality => ({
    supplier_key: FACILITY_ID,
    agreed_sending_hours: agreedSendingHours,
    metrics,
});

const fourMetrics = summary([
    metric({ key: 'missing_kde', status: 'ok', ...MISSING, share: missingShare }),
    metric({ key: 'unlinked_lot', status: 'not_enough_data', ...UNLINKED, share: null }),
    metric({ key: 'late_cte', status: 'not_enough_data', numerator: null, denominator: null, reason: LATE_REASON }),
    metric({ key: 'epcis_failed', status: 'unavailable', numerator: null, denominator: null, reason: EPCIS_REASON }),
]);

const lateMeasured = summary(
    [metric({ key: 'late_cte', status: 'ok', ...LATE, share: LATE.numerator / LATE.denominator })],
    AGREED_HOURS,
);

function renderQuality(data: SupplierDataQuality | null = fourMetrics, unavailable = false, onSendingHoursSaved?: () => void) {
    return render(
        <DataQuality
            facilityId={FACILITY_ID}
            summary={data ?? undefined}
            unavailable={unavailable}
            windowDays={WINDOW_DAYS}
            minRecords={MIN_RECORDS}
            lateCteLabel={LATE_LABEL}
            onSendingHoursSaved={onSendingHoursSaved}
        />,
    );
}

const page = (overrides: Partial<SupplierQualityRecordsResponse>): SupplierQualityRecordsResponse => ({
    supplier_key: FACILITY_ID,
    metric: 'missing_kde',
    window_days: WINDOW_DAYS,
    total: 0,
    limit: DRILLDOWN_PAGE_SIZE,
    offset: 0,
    items: [],
    ...overrides,
});

describe('DataQuality', () => {
    beforeEach(() => {
        mocks.getSupplierDataQualityRecords.mockReset();
        mocks.setFacilityAgreedSendingHours.mockReset();
    });

    it('shows count of denominator and a share for each metric, with no combined score', () => {
        renderQuality();
        expect(screen.getByText(`${MISSING.numerator} of ${MISSING.denominator} records (${formatShare(missingShare)})`)).toBeInTheDocument();
        expect(screen.queryByText(/score/i)).not.toBeInTheDocument();
        expect(screen.getByText(`Data quality, records received in the last ${WINDOW_DAYS} days`)).toBeInTheDocument();
    });

    it('shows Not enough data below the minimum instead of a share', () => {
        renderQuality();
        expect(screen.getByText(new RegExp(`${UNLINKED.numerator} of ${UNLINKED.denominator} lot codes`))).toBeInTheDocument();
        expect(screen.getByText(`Not enough data (fewer than ${MIN_RECORDS})`)).toBeInTheDocument();
        expect(screen.queryByText(formatShare(UNLINKED.numerator / UNLINKED.denominator))).not.toBeInTheDocument();
    });

    it('shows unavailable metrics with their reason and the late CTE label', () => {
        renderQuality();
        expect(screen.getByText(`Not enough data. ${LATE_REASON}`)).toBeInTheDocument();
        expect(screen.getByText(`Unavailable. ${EPCIS_REASON}`)).toBeInTheDocument();
        expect(screen.getByText(LATE_LABEL)).toBeInTheDocument();
    });

    it('shows a computed EPCIS share with its tenant wide reason and no drill down', () => {
        const receipts = uuids(MIN_RECORDS);
        const rejected = receipts.filter((_, index) => index % 2 === 0);
        const share = rejected.length / receipts.length;
        const tenantReason = crypto.randomUUID();
        renderQuality(
            summary([
                metric({
                    key: 'epcis_failed',
                    status: 'ok',
                    numerator: rejected.length,
                    denominator: receipts.length,
                    share,
                    reason: tenantReason,
                }),
            ]),
        );
        expect(screen.getByText('EPCIS (Preview) documents rejected:')).toBeInTheDocument();
        expect(screen.getByText(`${rejected.length} of ${receipts.length} documents (${formatShare(share)})`)).toBeInTheDocument();
        expect(screen.getByText(tenantReason)).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'View records' })).not.toBeInTheDocument();
    });

    it('offers drill down only for computable metrics with flagged records', () => {
        renderQuality();
        expect(screen.getAllByRole('button', { name: 'View records' })).toHaveLength(2);
    });

    it('hides drill down when nothing is flagged', () => {
        renderQuality(summary([metric({ key: 'missing_kde', numerator: 0, denominator: RECORD_IDS.length, share: 0 })]));
        expect(screen.queryByRole('button', { name: 'View records' })).not.toBeInTheDocument();
    });

    it('loads the exact records for a metric and pages with Show more', async () => {
        const [first, second] = uuids(2);
        const total = [first, second].length;
        mocks.getSupplierDataQualityRecords
            .mockResolvedValueOnce(
                page({
                    total,
                    items: [
                        {
                            record_id: first,
                            lot_id: null,
                            lot_code: crypto.randomUUID(),
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
                    total,
                    offset: 1,
                    items: [
                        {
                            record_id: second,
                            lot_id: null,
                            lot_code: crypto.randomUUID(),
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
        await waitFor(() => expect(screen.getByText(first)).toBeInTheDocument());
        expect(screen.getByText('Missing: reference_document, quantity')).toBeInTheDocument();
        expect(mocks.getSupplierDataQualityRecords).toHaveBeenCalledWith(FACILITY_ID, 'missing_kde', {
            windowDays: WINDOW_DAYS,
            limit: DRILLDOWN_PAGE_SIZE,
            offset: 0,
        });

        fireEvent.click(screen.getByRole('button', { name: `Show more (1 of ${total})` }));
        await waitFor(() => expect(screen.getByText(second)).toBeInTheDocument());
        expect(mocks.getSupplierDataQualityRecords).toHaveBeenLastCalledWith(FACILITY_ID, 'missing_kde', {
            windowDays: WINDOW_DAYS,
            limit: DRILLDOWN_PAGE_SIZE,
            offset: 1,
        });
        expect(screen.queryByRole('button', { name: /Show more/ })).not.toBeInTheDocument();
    });

    it('lists unlinked lot codes', async () => {
        const lotCode = crypto.randomUUID();
        mocks.getSupplierDataQualityRecords.mockResolvedValueOnce(
            page({
                metric: 'unlinked_lot',
                total: [lotCode].length,
                items: [
                    {
                        record_id: null,
                        lot_id: crypto.randomUUID(),
                        lot_code: lotCode,
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
        await waitFor(() => expect(screen.getByText(`Lot ${lotCode}`)).toBeInTheDocument());
        expect(mocks.getSupplierDataQualityRecords).toHaveBeenCalledWith(FACILITY_ID, 'unlinked_lot', expect.anything());
    });

    it('says so when the records request fails', async () => {
        mocks.getSupplierDataQualityRecords.mockRejectedValueOnce(new Error(crypto.randomUUID()));
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

    it('shows the late share against the agreed sending time and offers its records', async () => {
        const [lateId] = uuids(1);
        mocks.getSupplierDataQualityRecords.mockResolvedValueOnce(
            page({
                metric: 'late_cte',
                total: [lateId].length,
                items: [
                    {
                        record_id: lateId,
                        lot_id: null,
                        lot_code: crypto.randomUUID(),
                        cte_type: 'shipping',
                        event_time: null,
                        received_at: null,
                        missing_kdes: [],
                    },
                ],
            }),
        );
        renderQuality(lateMeasured);
        expect(
            screen.getByText(`${LATE.numerator} of ${LATE.denominator} records (${formatShare(LATE.numerator / LATE.denominator)})`),
        ).toBeInTheDocument();
        expect(screen.getByText(`Agreed sending time: ${AGREED_HOURS} hours after the event`)).toBeInTheDocument();

        fireEvent.click(screen.getByRole('button', { name: 'View records' }));
        await waitFor(() => expect(screen.getByText(lateId)).toBeInTheDocument());
        expect(mocks.getSupplierDataQualityRecords).toHaveBeenCalledWith(FACILITY_ID, 'late_cte', expect.anything());
    });

    it('offers no late drill down without an agreed sending time', () => {
        renderQuality(summary([fourMetrics.metrics[2]]));
        expect(screen.getByText('Agreed sending time: Not set')).toBeInTheDocument();
        expect(screen.queryByRole('button', { name: 'View records' })).not.toBeInTheDocument();
    });

    it('saves a new agreed sending time and reloads the measures', async () => {
        const onSaved = vi.fn();
        mocks.setFacilityAgreedSendingHours.mockResolvedValueOnce({
            facility_id: FACILITY_ID,
            agreed_sending_hours: AGREED_HOURS,
        });
        renderQuality(summary([fourMetrics.metrics[2]]), false, onSaved);

        fireEvent.click(screen.getByRole('button', { name: 'Set' }));
        fireEvent.change(screen.getByLabelText('Hours after the event'), { target: { value: String(AGREED_HOURS) } });
        fireEvent.click(screen.getByRole('button', { name: 'Save' }));

        await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
        expect(mocks.setFacilityAgreedSendingHours).toHaveBeenCalledWith(FACILITY_ID, AGREED_HOURS);
    });

    it.each(['0', `-${AGREED_HOURS}`, `${AGREED_HOURS}.5`, ''])('refuses %j as an agreed sending time', (draft) => {
        renderQuality(summary([fourMetrics.metrics[2]]));
        fireEvent.click(screen.getByRole('button', { name: 'Set' }));
        fireEvent.change(screen.getByLabelText('Hours after the event'), { target: { value: draft } });
        fireEvent.click(screen.getByRole('button', { name: 'Save' }));
        expect(screen.getByRole('alert')).toHaveTextContent('Enter a whole number of hours above zero');
        expect(mocks.setFacilityAgreedSendingHours).not.toHaveBeenCalled();
    });

    it('clears the agreed sending time with null', async () => {
        const onSaved = vi.fn();
        mocks.setFacilityAgreedSendingHours.mockResolvedValueOnce({ facility_id: FACILITY_ID, agreed_sending_hours: null });
        renderQuality(lateMeasured, false, onSaved);
        fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
        expect(screen.getByLabelText('Hours after the event')).toHaveValue(AGREED_HOURS);
        fireEvent.click(screen.getByRole('button', { name: 'Clear' }));
        await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
        expect(mocks.setFacilityAgreedSendingHours).toHaveBeenCalledWith(FACILITY_ID, null);
    });

    it('says so when saving the agreed sending time fails', async () => {
        const onSaved = vi.fn();
        mocks.setFacilityAgreedSendingHours.mockRejectedValueOnce(new Error(crypto.randomUUID()));
        renderQuality(summary([fourMetrics.metrics[2]]), false, onSaved);
        fireEvent.click(screen.getByRole('button', { name: 'Set' }));
        fireEvent.change(screen.getByLabelText('Hours after the event'), { target: { value: String(AGREED_HOURS) } });
        fireEvent.click(screen.getByRole('button', { name: 'Save' }));
        await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('The agreed sending time could not be saved'));
        expect(onSaved).not.toHaveBeenCalled();
    });
});
