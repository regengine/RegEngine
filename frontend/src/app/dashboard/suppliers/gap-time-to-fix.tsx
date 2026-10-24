import { ExternalLink } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import type { SupplierGapTimeToFix } from '@/types/api';

const RECORDS_REQUEST_URL = 'https://www.ecfr.gov/current/title-21/section-1.1455';

/** Whole seconds to a short duration, largest two units. */
function formatDuration(totalSeconds: number): string {
    if (totalSeconds < 60) return 'under 1 min';
    const days = Math.floor(totalSeconds / 86_400);
    const hours = Math.floor((totalSeconds % 86_400) / 3_600);
    const minutes = Math.floor((totalSeconds % 3_600) / 60);
    if (days > 0) return hours > 0 ? `${days} d ${hours} h` : `${days} d`;
    if (hours > 0) return minutes > 0 ? `${hours} h ${minutes} min` : `${hours} h`;
    return `${minutes} min`;
}

function openFor(openedAt: string | null, now: number): string | null {
    if (!openedAt) return null;
    const opened = Date.parse(openedAt);
    if (Number.isNaN(opened)) return null;
    return formatDuration(Math.max(0, (now - opened) / 1000));
}

interface GapTimeToFixProps {
    summary: SupplierGapTimeToFix | undefined;
    /** True when the time to fix request failed. */
    unavailable: boolean;
    now: number;
}

/** Per facility data gap time to fix: open gaps, median fix time, oldest open gap. */
export function GapTimeToFix({ summary, unavailable, now }: GapTimeToFixProps) {
    if (unavailable) {
        return <p className="mt-2 text-small text-re-text-tertiary">Gap time to fix unavailable</p>;
    }

    const citation = (
        <a
            href={RECORDS_REQUEST_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-re-text-tertiary underline underline-offset-2 hover:text-re-text-primary"
        >
            21 CFR 1.1455(c)(1)
            <ExternalLink className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
        </a>
    );

    if (!summary || !summary.has_data) {
        return (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-re-text-tertiary">
                <span>Gap time to fix: No data</span>
                {citation}
            </div>
        );
    }

    const median = summary.median_time_to_fix_seconds;
    const oldest = openFor(summary.oldest_open_gap_opened_at, now);

    return (
        <div
            className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-small text-re-text-secondary"
            aria-label="Gap time to fix"
        >
            <span>
                {summary.open_gap_count} open gap{summary.open_gap_count !== 1 ? 's' : ''}
            </span>
            <span>Median time to fix: {median === null ? 'No fixes yet' : formatDuration(median)}</span>
            {oldest !== null && <span>Oldest open gap: {oldest}</span>}
            {summary.at_risk && (
                <Badge tone="danger" size="sm">
                    At risk: gap open over 24 hours
                </Badge>
            )}
            {citation}
        </div>
    );
}
