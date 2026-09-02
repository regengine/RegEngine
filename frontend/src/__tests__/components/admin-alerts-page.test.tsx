/**
 * #2999 — /admin/alerts must not report "operating within compliance
 * thresholds" when it cannot fetch alerts at all.
 *
 * The page fed `alertsData?.alerts.filter(...) || []` straight into the
 * empty state, so a failed fetch (`alertsData === undefined`) rendered the
 * all-clear copy. "I could not reach the alerts service" and "there are no
 * alerts" are opposite conditions; collapsing them into the reassuring one
 * ends an investigation a visible error would have started. The fetch target
 * (GET /api/fsma/drift/alerts) has no backend router (#2980), so before this
 * fix the false all-clear was the ONLY state this page ever rendered.
 *
 * Three states, following DriftAlertsWidget's precedent (#2837):
 * loading spinner / explicit unavailable / true empty state.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import AdminAlertsPage from '@/app/admin/alerts/page';

const mockUseDriftAlerts = vi.hoisted(() => vi.fn());
const mockUseAcknowledgeAlert = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/use-fsma', () => ({
    useDriftAlerts: () => mockUseDriftAlerts(),
    useAcknowledgeAlert: () => mockUseAcknowledgeAlert(),
}));

const ALL_CLEAR_COPY = /operating within compliance thresholds/i;

beforeEach(() => {
    vi.clearAllMocks();
    mockUseAcknowledgeAlert.mockReturnValue({ mutateAsync: vi.fn() });
});

describe('AdminAlertsPage (#2999)', () => {
    it('never renders the all-clear copy when the fetch fails', () => {
        mockUseDriftAlerts.mockReturnValue({
            data: undefined,
            isLoading: false,
            isError: true,
            error: new Error('HTTP 404'),
        });

        render(<AdminAlertsPage />);

        expect(screen.queryByText(ALL_CLEAR_COPY)).not.toBeInTheDocument();
        expect(screen.queryByText('No alerts found')).not.toBeInTheDocument();

        const status = screen.getByRole('status');
        expect(status).toHaveTextContent('Alerts unavailable');
        expect(status).toHaveTextContent(/not an all-clear/i);
        expect(status).toHaveTextContent('HTTP 404');
        expect(screen.getByText('Unavailable')).toBeInTheDocument();
    });

    it('treats a settled query with no data as unavailable, not as zero alerts', () => {
        mockUseDriftAlerts.mockReturnValue({
            data: undefined,
            isLoading: false,
            isError: false,
        });

        render(<AdminAlertsPage />);

        expect(screen.queryByText(ALL_CLEAR_COPY)).not.toBeInTheDocument();
        expect(screen.getByRole('status')).toHaveTextContent('Alerts unavailable');
    });

    it('still renders the true empty state for a successful response with zero alerts', () => {
        mockUseDriftAlerts.mockReturnValue({
            data: { alerts: [] },
            isLoading: false,
            isError: false,
        });

        render(<AdminAlertsPage />);

        expect(screen.getByText('No alerts found')).toBeInTheDocument();
        expect(screen.getByText(ALL_CLEAR_COPY)).toBeInTheDocument();
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
        expect(screen.getByText('0 Active Alerts')).toBeInTheDocument();
    });

    it('shows the spinner while loading, without the all-clear copy', () => {
        mockUseDriftAlerts.mockReturnValue({
            data: undefined,
            isLoading: true,
            isError: false,
        });

        render(<AdminAlertsPage />);

        expect(screen.queryByText(ALL_CLEAR_COPY)).not.toBeInTheDocument();
        expect(screen.queryByRole('status')).not.toBeInTheDocument();
    });
});
