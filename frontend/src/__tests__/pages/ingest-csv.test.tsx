import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IngestPage from '@/app/ingest/page';

const mocks = vi.hoisted(() => ({
  ingestFile: vi.fn(),
  ingestURL: vi.fn(),
  getIngestionJob: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ apiKey: 'cookie-managed', setApiKey: vi.fn() }), // pragma: allowlist secret
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

async function uploadCsv() {
  render(<IngestPage />);
  await userEvent.click(screen.getByRole('tab', { name: /file upload/i }));
  const input = document.getElementById('file-upload') as HTMLInputElement;
  fireEvent.change(input, {
    target: { files: [new File(['cte_type,tlc\nshipping,LOT-1'], 'events.csv', { type: 'text/csv' })] },
  });
  await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));
}

describe('CSV import results on /ingest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it.each([
    [2, 0, 'CSV import complete'],
    [1, 1, 'CSV import partially accepted'],
    [0, 2, 'No rows imported'],
  ])('shows %i accepted and %i rejected without polling a document job', async (accepted, rejected, title) => {
    mocks.ingestFile.mockResolvedValue({ total: 2, accepted, rejected, events: [] });
    await uploadCsv();

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(`${accepted} of 2 rows accepted; ${rejected} rejected.`)).toBeInTheDocument();
    expect(screen.queryByText('Ingestion Progress')).not.toBeInTheDocument();
    expect(screen.queryByText('Normalized document viewer')).not.toBeInTheDocument();
    expect(mocks.getIngestionJob).not.toHaveBeenCalled();
    expect(mocks.refresh).toHaveBeenCalledTimes(accepted > 0 ? 1 : 0);
  });

  it('shows rejected row details and server KDE warnings', async () => {
    mocks.ingestFile.mockResolvedValue({
      total: 2, accepted: 1, rejected: 1,
      events: [{ status: 'rejected', errors: ['Row 3: Quantity must be positive'] }],
      kde_warnings: ['Row 2: Missing KDEs: reference_document'],
    });
    await uploadCsv();
    expect(await screen.findByText('Row 3: Quantity must be positive')).toBeInTheDocument();
    expect(screen.getByText('Row 2: Missing KDEs: reference_document')).toBeInTheDocument();
  });

  it('shows validation failure without reporting import success', async () => {
    mocks.ingestFile.mockRejectedValue(new Error('No valid rows found: Row 2: No CTE type'));
    await uploadCsv();
    expect(await screen.findByText('No valid rows found: Row 2: No CTE type')).toBeInTheDocument();
    expect(screen.queryByText('CSV import complete')).not.toBeInTheDocument();
    expect(mocks.refresh).not.toHaveBeenCalled();
  });

  it('keeps URL ingestion on the existing document job path', async () => {
    mocks.ingestURL.mockResolvedValue({ job_id: 'document-job-1' });
    render(<IngestPage />);
    fireEvent.change(screen.getByPlaceholderText(/https:\/\//i), { target: { value: 'https://example.org/document.pdf' } });
    await userEvent.click(screen.getByRole('button', { name: /^ingest document$/i }));
    expect(await screen.findByText('Job document-job-1')).toBeInTheDocument();
    expect(mocks.ingestFile).not.toHaveBeenCalled();
  });
});
