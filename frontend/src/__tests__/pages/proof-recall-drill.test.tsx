import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RecallDrillPage from '@/app/proof/recall-drill/page';

const uid = () => crypto.randomUUID();

function stubFetch(body: unknown, ok = true) {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok, status: ok ? 200 : 503, json: async () => body }));
}

describe('public proof recall drill page', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('renders the API message as an empty state when data_available is false', async () => {
        const message = uid();
        stubFetch({
            data_available: false,
            steps: [],
            time_to_trace_seconds: null,
            output_csv_url: null,
            lot_code: null,
            fda_24h_mandate_seconds: 86400,
            message,
            timestamp: new Date().toISOString(),
        });
        const user = userEvent.setup();
        render(<RecallDrillPage />);

        await user.click(screen.getByRole('button', { name: /start drill/i }));

        expect(fetch).toHaveBeenCalledWith('/api/ingestion/api/v1/proof/recall-drill', { method: 'POST' });
        expect(await screen.findByTestId('recall-drill-empty')).toHaveTextContent(message);
        expect(screen.queryByText(/Drill log/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/Time to trace/i)).not.toBeInTheDocument();
        expect(screen.queryByRole('link', { name: /download recall csv/i })).not.toBeInTheDocument();
        expect(document.body.textContent).not.toMatch(/samples\//);
    });

    it('renders only steps the API returned when data is available', async () => {
        const stepName = uid();
        const stepDetail = uid();
        stubFetch({
            data_available: true,
            steps: [{ name: stepName, duration_ms: 0, status: 'ok', detail: stepDetail }],
            time_to_trace_seconds: null,
            output_csv_url: null,
            lot_code: null,
            fda_24h_mandate_seconds: 86400,
            message: uid(),
            timestamp: new Date().toISOString(),
        });
        const user = userEvent.setup();
        render(<RecallDrillPage />);

        await user.click(screen.getByRole('button', { name: /start drill/i }));

        expect(await screen.findByText(stepName)).toBeInTheDocument();
        expect(await screen.findByText(stepDetail)).toBeInTheDocument();
        // No trace time is invented when the API reports none.
        expect(screen.queryByText(/Time to trace/i)).not.toBeInTheDocument();
    });

    it('shows an error and no fallback drill when the endpoint fails', async () => {
        stubFetch({}, false);
        const user = userEvent.setup();
        render(<RecallDrillPage />);

        await user.click(screen.getByRole('button', { name: /start drill/i }));

        expect(await screen.findByRole('alert')).toBeInTheDocument();
        expect(screen.queryByText(/Drill log/i)).not.toBeInTheDocument();
    });
});
