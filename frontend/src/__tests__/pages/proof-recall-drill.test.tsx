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
                    steps: [
                        {
                            name: 'Identifying from API',
                            duration_ms: 100,
                            status: 'ok',
                            detail: 'Endpoint loaded the frozen public dataset.',
                        },
                    ],
                    time_to_trace_seconds: 0.1,
                    output_csv_url: '/samples/sample_recall_drill.csv',
                    lot_code: 'SV-20240115-001',
                    fda_24h_mandate_seconds: 86400,
                    timestamp: '2026-05-19T00:00:00Z',
                }),
            }),
        );
    });

    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('starts the public backend drill endpoint and renders returned steps', async () => {
        const user = userEvent.setup();
        render(<RecallDrillPage />);

        await user.click(screen.getByRole('button', { name: /start drill/i }));

        expect(fetch).toHaveBeenCalledWith('/api/ingestion/api/v1/proof/recall-drill', {
            method: 'POST',
        });
        expect(await screen.findByText(/Identifying from API/)).toBeInTheDocument();
        expect(
            screen.getByText(/Endpoint loaded the frozen public dataset/i),
        ).toBeInTheDocument();
    });
});
