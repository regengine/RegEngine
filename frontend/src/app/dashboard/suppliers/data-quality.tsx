import { useState, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';
import { apiClient } from '@/lib/api-client';
import type {
    SupplierDataQuality,
    SupplierQualityDrilldownMetric,
    SupplierQualityMetric,
    SupplierQualityMetricKey,
    SupplierQualityRecordItem,
} from '@/types/api';

export const DRILLDOWN_PAGE_SIZE = 25;

const METRIC_COPY: Record<SupplierQualityMetricKey, { label: string; unit: string }> = {
    missing_kde: { label: 'Records missing a KDE', unit: 'records' },
    unlinked_lot: { label: 'Lot codes not linked back through the chain', unit: 'lot codes' },
    late_cte: { label: 'Late CTE records', unit: 'records' },
    epcis_failed: { label: 'EPCIS (Preview) documents rejected across your whole account', unit: 'documents' },
};

function isDrilldown(key: SupplierQualityMetricKey): key is SupplierQualityDrilldownMetric {
    return key === 'missing_kde' || key === 'unlinked_lot' || key === 'late_cte';
}

function formatTime(value: string | null): string {
    return value ? new Date(value).toLocaleString() : 'unknown';
}

function formatHours(hours: number): string {
    return `${hours} hour${hours === 1 ? '' : 's'}`;
}

function formatShare(share: number): string {
    return `${Math.round(share * 1000) / 10}%`;
}

interface DrilldownState {
    items: SupplierQualityRecordItem[];
    total: number;
    loading: boolean;
    failed: boolean;
}

function DrilldownList({ metric, state }: { metric: SupplierQualityDrilldownMetric; state: DrilldownState }) {
    if (state.items.length === 0) {
        if (state.loading) return <p className="text-small text-re-text-tertiary">Loading records</p>;
        if (state.failed) return <p className="text-small text-re-text-tertiary">Records could not be loaded</p>;
        return <p className="text-small text-re-text-tertiary">No records</p>;
    }
    return (
        <ul className="space-y-1 text-small text-re-text-secondary" aria-label={`${METRIC_COPY[metric].label} records`}>
            {state.items.map((item) =>
                metric === 'late_cte' ? (
                    <li key={item.record_id ?? item.lot_code} className="flex flex-wrap gap-x-2">
                        <span className="font-mono">{item.record_id}</span>
                        <span>Lot {item.lot_code}</span>
                        {item.cte_type && <span>{item.cte_type}</span>}
                        <span>Event {formatTime(item.event_time)}</span>
                        <span>Received {formatTime(item.received_at)}</span>
                    </li>
                ) : metric === 'missing_kde' ? (
                    <li key={item.record_id ?? item.lot_code} className="flex flex-wrap gap-x-2">
                        <span className="font-mono">{item.record_id}</span>
                        <span>Lot {item.lot_code}</span>
                        {item.cte_type && <span>{item.cte_type}</span>}
                        <span>Missing: {item.missing_kdes.join(', ')}</span>
                    </li>
                ) : (
                    <li key={item.lot_id ?? item.lot_code} className="flex flex-wrap gap-x-2">
                        <span>Lot {item.lot_code}</span>
                        <span className="font-mono text-re-text-tertiary">{item.lot_id}</span>
                    </li>
                ),
            )}
        </ul>
    );
}

/** Read only: the customer (tenant admin) sets the agreed sending time, not the supplier. */
function SendingHoursNote({ hours }: { hours: number | null }) {
    return (
        <div className="flex flex-wrap items-center gap-x-2">
            <span>Agreed sending time: {hours === null ? 'Not set' : `${formatHours(hours)} after the event`}</span>
            <span className="text-re-text-tertiary">Set by your customer</span>
        </div>
    );
}

function MetricRow({
    facilityId,
    metric,
    windowDays,
    minRecords,
    lateCteLabel,
    agreedSendingHours,
}: {
    facilityId: string;
    metric: SupplierQualityMetric;
    windowDays: number;
    minRecords: number;
    lateCteLabel: string;
    agreedSendingHours: number | null;
}) {
    const copy = METRIC_COPY[metric.key];
    const [open, setOpen] = useState(false);
    const [drilldown, setDrilldown] = useState<DrilldownState>({ items: [], total: 0, loading: false, failed: false });

    const load = async (key: SupplierQualityDrilldownMetric, offset: number) => {
        setDrilldown((prev) => ({ ...prev, loading: true, failed: false }));
        try {
            const res = await apiClient.getSupplierDataQualityRecords(facilityId, key, {
                windowDays,
                limit: DRILLDOWN_PAGE_SIZE,
                offset,
            });
            setDrilldown((prev) => ({
                items: offset === 0 ? res.items : [...prev.items, ...res.items],
                total: res.total,
                loading: false,
                failed: false,
            }));
        } catch {
            setDrilldown((prev) => ({ ...prev, loading: false, failed: true }));
        }
    };

    const toggle = () => {
        if (!isDrilldown(metric.key)) return;
        const next = !open;
        setOpen(next);
        if (next && drilldown.items.length === 0) void load(metric.key, 0);
    };

    let value: ReactNode;
    if (metric.status === 'unavailable') {
        value = <span className="text-re-text-tertiary">Unavailable. {metric.reason}</span>;
    } else if (metric.numerator === null || metric.denominator === null) {
        value = <span className="text-re-text-tertiary">Not enough data. {metric.reason}</span>;
    } else {
        const counts = `${metric.numerator} of ${metric.denominator} ${copy.unit}`;
        value =
            metric.status === 'ok' && metric.share !== null ? (
                <span>
                    {counts} ({formatShare(metric.share)})
                </span>
            ) : (
                <span>
                    {counts}. <span className="text-re-text-tertiary">Not enough data (fewer than {minRecords})</span>
                </span>
            );
    }

    const canDrill = isDrilldown(metric.key) && metric.status !== 'unavailable' && (metric.numerator ?? 0) > 0;

    return (
        <li className="space-y-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                <span className="text-re-text-primary">{copy.label}:</span>
                {value}
                {canDrill && (
                    <Button variant="link" size="sm" onClick={toggle} aria-expanded={open}>
                        {open ? 'Hide records' : 'View records'}
                    </Button>
                )}
            </div>
            {metric.key === 'late_cte' && (
                <>
                    <p className="text-re-text-tertiary">{lateCteLabel}</p>
                    <SendingHoursNote hours={agreedSendingHours} />
                </>
            )}
            {metric.status !== 'unavailable' && metric.reason && <p className="text-re-text-tertiary">{metric.reason}</p>}
            {open && isDrilldown(metric.key) && (
                <div className="space-y-1 pl-3">
                    <DrilldownList metric={metric.key} state={drilldown} />
                    {drilldown.items.length < drilldown.total && (
                        <Button
                            variant="link"
                            size="sm"
                            disabled={drilldown.loading}
                            onClick={() => isDrilldown(metric.key) && void load(metric.key, drilldown.items.length)}
                        >
                            Show more ({drilldown.items.length} of {drilldown.total})
                        </Button>
                    )}
                </div>
            )}
        </li>
    );
}

interface DataQualityProps {
    facilityId: string;
    summary: SupplierDataQuality | undefined;
    /** True when the data quality request failed. */
    unavailable: boolean;
    windowDays: number;
    minRecords: number;
    lateCteLabel: string;
}

/** Four separate data quality measures for one facility. No combined score. */
export function DataQuality({
    facilityId,
    summary,
    unavailable,
    windowDays,
    minRecords,
    lateCteLabel,
}: DataQualityProps) {
    if (unavailable) {
        return <p className="mt-2 text-small text-re-text-tertiary">Data quality unavailable</p>;
    }
    if (!summary) {
        return <p className="mt-2 text-small text-re-text-tertiary">Data quality: No data</p>;
    }
    return (
        <div className="mt-2 text-small text-re-text-secondary" aria-label="Data quality">
            <p className="text-re-text-tertiary">Data quality, records received in the last {windowDays} days</p>
            <ul className="mt-1 space-y-1">
                {summary.metrics.map((metric) => (
                    <MetricRow
                        key={metric.key === 'late_cte' ? `${metric.key}:${summary.agreed_sending_hours ?? 'unset'}` : metric.key}
                        facilityId={facilityId}
                        metric={metric}
                        windowDays={windowDays}
                        minRecords={minRecords}
                        lateCteLabel={lateCteLabel}
                        agreedSendingHours={summary.agreed_sending_hours ?? null}
                    />
                ))}
            </ul>
        </div>
    );
}
