import { describe, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IngestPage from '@/app/ingest/page';

const mocks = vi.hoisted(() => ({
    ingestFile: vi.fn(),
    ingestURL: vi.fn(),
    getIngestionJob: vi.fn(),
    refresh: vi.fn(),
    storeApiKey: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({ apiKey: 'cookie-managed', setApiKey: mocks.storeApiKey }), // pragma: allowlist secret
}));
vi.mock('@/hooks/use-api', () => ({
    useIngestURL: () => ({ mutateAsync: mocks.ingestURL, reset: vi.fn() }),
    useIngestFile: () => ({ mutateAsync: mocks.ingestFile, reset: vi.fn() }),
}));
vi.mock('@/lib/api-client', () => ({
    apiClient: { getIngestionJob: mocks.getIngestionJob },
}));
vi.mock('@/hooks/use-dashboard-refresh', () => ({
    notifyDashboardRefresh: mocks.refresh,
}));
vi.mock('@/app/ingest/NormalizedDocumentViewer', () => ({
    NormalizedDocumentViewer: () => <div>Normalized document viewer</div>,
}));

// The built-in eCFR sample URL. Submitting it must go through the real
// ingestion API like any other URL, never a faked local completion.
const SAMPLE_URL =
    'https://www.ecfr.gov/api/versioner/v1/full/2024-01-01/title-21.xml?chapter=I&subchapter=A&part=1';

describe('IngestPage sample URL', () => {
    it('sends the sample URL to the real ingestion API', async () => {
        mocks.ingestURL.mockReset();
        mocks.ingestURL.mockResolvedValue({ job_id: 'job-1', document_id: 'doc-1' });
        mocks.getIngestionJob.mockResolvedValue({ status: 'completed' });

        render(<IngestPage />);

        // Wait for the stored API key prefill so the form can submit.
        await screen.findByDisplayValue('cookie-managed'); // pragma: allowlist secret

        // Fill the URL through the built-in example shortcut.
        await userEvent.click(screen.getByRole('button', { name: /fda regulations/i }));
        expect(screen.getByLabelText(/document url/i)).toHaveValue(SAMPLE_URL);

        await userEvent.click(screen.getByRole('button', { name: /ingest document/i }));

        await waitFor(() => expect(mocks.ingestURL).toHaveBeenCalled());
        expect(mocks.ingestURL).toHaveBeenCalledWith(
            expect.objectContaining({ url: SAMPLE_URL }),
        );
        expect(screen.queryByText(/demo-job-123/)).not.toBeInTheDocument();
    });
});
