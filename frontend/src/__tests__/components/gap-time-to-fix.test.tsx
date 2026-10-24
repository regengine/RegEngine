import { describe, expect, it } from 'vitest';
import { render, screen } from '@testing-library/react';
import { GapTimeToFix } from '@/app/dashboard/suppliers/gap-time-to-fix';
import type { SupplierGapTimeToFix } from '@/types/api';

const NOW = Date.UTC(2026, 0, 2);
const HOUR_MS = 3_600_000;

const summary = (overrides: Partial<SupplierGapTimeToFix>): SupplierGapTimeToFix => ({
    supplier_key: 'k',
    open_gap_count: 0,
    median_time_to_fix_seconds: null,
    oldest_open_gap_opened_at: null,
    at_risk: false,
    at_risk_gap_count: 0,
    past_internal_target: false,
    has_data: true,
    ...overrides,
});

describe('GapTimeToFix', () => {
    it('shows No data when the supplier has no gap history', () => {
        render(<GapTimeToFix summary={undefined} unavailable={false} now={NOW} />);
        expect(screen.getByText('Gap time to fix: No data')).toBeInTheDocument();
        expect(screen.queryByText(/At risk/)).not.toBeInTheDocument();
    });

    it('shows No data when the summary reports has_data false', () => {
        render(<GapTimeToFix summary={summary({ has_data: false })} unavailable={false} now={NOW} />);
        expect(screen.getByText('Gap time to fix: No data')).toBeInTheDocument();
    });

    it('cites 21 CFR 1.1455(c)(1) in the empty state', () => {
        render(<GapTimeToFix summary={undefined} unavailable={false} now={NOW} />);
        expect(screen.getByRole('link', { name: /21 CFR 1\.1455\(c\)\(1\)/ })).toHaveAttribute(
            'href',
            'https://www.ecfr.gov/current/title-21/section-1.1455',
        );
    });

    it('says unavailable instead of No data when the request failed', () => {
        render(<GapTimeToFix summary={undefined} unavailable now={NOW} />);
        expect(screen.getByText('Gap time to fix unavailable')).toBeInTheDocument();
        expect(screen.queryByText(/No data/)).not.toBeInTheDocument();
    });

    it('renders open count, median, oldest open gap, and the request due badge with its citation', () => {
        render(
            <GapTimeToFix
                summary={summary({
                    open_gap_count: 2,
                    median_time_to_fix_seconds: 5_400,
                    oldest_open_gap_opened_at: new Date(NOW - 25 * HOUR_MS).toISOString(),
                    at_risk: true,
                    at_risk_gap_count: 1,
                    past_internal_target: true,
                })}
                unavailable={false}
                now={NOW}
            />,
        );
        expect(screen.getByText('2 open gaps')).toBeInTheDocument();
        expect(screen.getByText('Median time to fix: 1 h 30 min')).toBeInTheDocument();
        expect(screen.getByText('Oldest open gap: 1 d 1 h')).toBeInTheDocument();
        expect(screen.getByText('At risk: open when FDA records response is due')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: /21 CFR 1\.1455\(c\)\(1\)/ })).toHaveAttribute(
            'href',
            'https://www.ecfr.gov/current/title-21/section-1.1455',
        );
        expect(screen.getByText('Internal target: fixed within 24 hours of flag')).toBeInTheDocument();
        expect(screen.getByText('Past internal target')).toBeInTheDocument();
        expect(screen.queryByText(/over 24 hours/)).not.toBeInTheDocument();
    });

    it('shows the internal target without a regulatory citation when not at risk', () => {
        render(
            <GapTimeToFix
                summary={summary({ open_gap_count: 1, past_internal_target: true })}
                unavailable={false}
                now={NOW}
            />,
        );
        expect(screen.getByText('Past internal target')).toBeInTheDocument();
        expect(screen.queryByText(/At risk/)).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: /1\.1455/ })).not.toBeInTheDocument();
    });

    it('says No fixes yet when no gap has closed and hides the badge when not at risk', () => {
        render(<GapTimeToFix summary={summary({ open_gap_count: 1 })} unavailable={false} now={NOW} />);
        expect(screen.getByText('1 open gap')).toBeInTheDocument();
        expect(screen.getByText('Median time to fix: No fixes yet')).toBeInTheDocument();
        expect(screen.queryByText(/At risk/)).not.toBeInTheDocument();
        expect(document.body.textContent).not.toMatch(/NaN|undefined/);
    });
});
