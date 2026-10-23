import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import RecallDrillPage from '@/app/proof/recall-drill/page';

describe('public proof recall drill page', () => {
    beforeEach(() => {
        vi.stubGlobal(
            'fetch',
            vi.fn().mockResolvedValue({
                ok: true,
                json: async () => ({
                    steps: [],
                    time_to_trace_seconds: 0,
                    output_csv_url: '',
                    lot_code: '',
                    fda_24h_mandate_seconds: 86400,
                    timestamp: '',
                }),
            }),
        );
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('renders no invented suppliers, lots, or trace nodes', () => {
        render(<RecallDrillPage />);

        expect(screen.queryByText(/sunny valley/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/fresh cut/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/metro foods/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/supermart/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/SV-2024/)).not.toBeInTheDocument();
        expect(screen.queryByText(/FC-2024/)).not.toBeInTheDocument();
        expect(screen.queryByText(/synthetic/i)).not.toBeInTheDocument();
        expect(
            screen.queryByRole('link', { name: /download recall csv/i }),
        ).not.toBeInTheDocument();
    });

    it('calls the drill endpoint and shows an empty state when no drill data exists', async () => {
        const user = userEvent.setup();
        render(<RecallDrillPage />);

        await user.click(screen.getByRole('button', { name: /start drill/i }));

        expect(fetch).toHaveBeenCalledWith('/api/ingestion/api/v1/proof/recall-drill', {
            method: 'POST',
        });
        expect(await screen.findByText('No data yet')).toBeInTheDocument();
        expect(
            screen.queryByRole('link', { name: /download recall csv/i }),
        ).not.toBeInTheDocument();
    });
});
