/**
 * #2837 — the drift widget must not render an infinite loading skeleton.
 *
 * DriftAlertsWidget destructured only { data, isLoading } and branched on
 * `isLoading || !health`, so ANY failure — 404, 500, network drop — landed in
 * the skeleton branch and the card animated "Monitoring system health..."
 * forever with no way for the user to tell that anything was wrong.
 *
 * The widget's data source has no backend at all: GET /api/fsma/drift/health
 * has no router in services/ or server/ (`grep -rn "/drift" services/ server/`
 * returns nothing), so in practice the failure branch is the ONLY branch that
 * runs in a real deployment. The failure state therefore has to read as
 * "capability not connected", not as a transient error.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { DriftAlertsWidget } from '@/components/fsma/drift-alerts';

const mockUseDriftHealth = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/use-fsma', () => ({
    useDriftHealth: () => mockUseDriftHealth(),
}));

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => (
            <div {...props}>{children}</div>
        ),
    },
}));

const HEALTHY = {
    trace_completeness_rate: 0.97,
    average_ingest_latency_ms: 120,
    error_rate_percent: 0.1,
    status: 'HEALTHY',
    alerts: [],
};

beforeEach(() => {
    vi.clearAllMocks();
});

describe('DriftAlertsWidget (#2837)', () => {
    it('shows the skeleton only while genuinely loading', () => {
        mockUseDriftHealth.mockReturnValue({ data: undefined, isLoading: true, isError: false });

        render(<DriftAlertsWidget />);

        expect(screen.getByText('Monitoring system health...')).toBeInTheDocument();
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });

    it('renders an explicit unavailable state on error instead of a skeleton', () => {
        mockUseDriftHealth.mockReturnValue({
            data: undefined,
            isLoading: false,
            isError: true,
            error: new Error('HTTP 404'),
        });

        render(<DriftAlertsWidget />);

        // The infinite-skeleton copy must be gone.
        expect(screen.queryByText('Monitoring system health...')).not.toBeInTheDocument();

        const status = screen.getByRole('status');
        expect(status).toHaveTextContent('Drift monitoring is not available');
        // Phrased as an unconnected capability, not a retryable blip.
        expect(status).toHaveTextContent(/not connected yet/i);
        expect(status).toHaveTextContent('HTTP 404');
        expect(screen.getByText('Unavailable')).toBeInTheDocument();
    });

    it('renders the unavailable state when the query settles with no data', () => {
        mockUseDriftHealth.mockReturnValue({ data: undefined, isLoading: false, isError: false });

        render(<DriftAlertsWidget />);

        expect(screen.queryByText('Monitoring system health...')).not.toBeInTheDocument();
        expect(screen.getByRole('status')).toHaveTextContent('Drift monitoring is not available');
    });

    it('still renders metrics when the query succeeds', () => {
        mockUseDriftHealth.mockReturnValue({ data: HEALTHY, isLoading: false, isError: false });

        render(<DriftAlertsWidget />);

        expect(screen.getByText('Healthy')).toBeInTheDocument();
        expect(screen.getByText('97.0%')).toBeInTheDocument();
        expect(screen.getByText('120ms')).toBeInTheDocument();
        expect(screen.getByText('No active drift alerts')).toBeInTheDocument();
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });
});
