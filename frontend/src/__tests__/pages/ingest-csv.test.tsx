import { beforeEach, describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IngestPage from '@/app/ingest/page';

const mocks = vi.hoisted(() => ({
  urlError: null as Error | null,
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
  useIngestURL: () => ({ mutateAsync: mocks.ingestURL, reset: vi.fn(), isError: !!mocks.urlError, error: mocks.urlError }),
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

function csvResult(accepted: number, rejected: number) {
  const statuses = [
    ...Array.from({ length: accepted }, () => 'accepted' as const),
    ...Array.from({ length: rejected }, () => 'rejected' as const),
  ];
  return {
    total: statuses.length,
    accepted,
    rejected,
    ingestion_timestamp: '2026-08-31T12:00:00+00:00',
    events: statuses.map((status, index) => ({
      traceability_lot_code: `LOT-${index + 1}`,
      cte_type: 'shipping',
      status,
      event_id: status === 'accepted' ? `evt-${index + 1}` : null,
      sha256_hash: status === 'accepted' ? `sha-${index + 1}` : null,
      chain_hash: status === 'accepted' ? `chain-${index + 1}` : null,
      errors: status === 'rejected' ? [`Row ${index + 2}: rejected`] : [],
    })),
  };
}

describe('CSV import results on /ingest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.storeApiKey.mockResolvedValue(undefined);
  });

  it.each([
    [2, 0, 'CSV processed'],
    [1, 1, 'CSV partially accepted'],
    [0, 2, 'No rows accepted'],
  ])('shows %i accepted and %i rejected without polling a document job', async (accepted, rejected, title) => {
    mocks.ingestFile.mockResolvedValue(csvResult(accepted, rejected));
    await uploadCsv();

    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(`${accepted} of 2 rows accepted; ${rejected} rejected.`)).toBeInTheDocument();
    expect(screen.queryByText('Ingestion Progress')).not.toBeInTheDocument();
    expect(screen.queryByText('Normalized document viewer')).not.toBeInTheDocument();
    expect(mocks.getIngestionJob).not.toHaveBeenCalled();
    expect(mocks.refresh).toHaveBeenCalledTimes(accepted > 0 ? 1 : 0);
  });

  it('shows rejected row details and server KDE warnings', async () => {
    const result = csvResult(1, 1);
    result.events[1].errors = ['Row 3: Quantity must be positive'];
    mocks.ingestFile.mockResolvedValue({
      ...result,
      kde_warnings: ['Row 2: Missing KDEs: reference_document'],
      kde_warning_count: 1,
    });
    await uploadCsv();
    expect(await screen.findByText('Row 3: Quantity must be positive')).toBeInTheDocument();
    expect(screen.getByText('Row 2: Missing KDEs: reference_document')).toBeInTheDocument();
  });

  it('shows validation failure without reporting import success', async () => {
    mocks.ingestFile.mockRejectedValue(new Error('No valid rows found: Row 2: No CTE type'));
    await uploadCsv();
    expect(await screen.findByText('No valid rows found: Row 2: No CTE type')).toBeInTheDocument();
    expect(screen.queryByText('CSV processed')).not.toBeInTheDocument();
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

  it('waits for the API-key cookie write before uploading with a changed key', async () => {
    let finishCookieWrite: (() => void) | undefined;
    mocks.storeApiKey.mockReturnValue(new Promise<void>((resolve) => {
      finishCookieWrite = resolve;
    }));
    mocks.ingestFile.mockResolvedValue(csvResult(1, 0));
    render(<IngestPage />);
    fireEvent.change(screen.getByPlaceholderText('rge_...'), { target: { value: 'rge_replacement_key' } }); // pragma: allowlist secret
    await userEvent.click(screen.getByRole('tab', { name: /file upload/i }));
    fireEvent.change(document.getElementById('file-upload') as HTMLInputElement, {
      target: { files: [new File(['cte_type,tlc\nshipping,LOT-1'], 'events.csv')] },
    });
    const submit = screen.getByRole('button', { name: /upload & process/i });
    await userEvent.click(submit);

    expect(mocks.storeApiKey).toHaveBeenCalledWith('rge_replacement_key'); // pragma: allowlist secret
    expect(mocks.ingestFile).not.toHaveBeenCalled();
    expect(submit).toBeDisabled();
    fireEvent.submit(submit.closest('form') as HTMLFormElement);
    expect(mocks.storeApiKey).toHaveBeenCalledTimes(1);
    finishCookieWrite?.();

    expect(await screen.findByText('CSV processed')).toBeInTheDocument();
    expect(mocks.ingestFile).toHaveBeenCalledTimes(1);
  });

  it('does not upload when the API-key cookie cannot be saved', async () => {
    mocks.storeApiKey.mockRejectedValue(new Error('API key could not be saved. Please try again.'));
    render(<IngestPage />);
    fireEvent.change(screen.getByPlaceholderText('rge_...'), { target: { value: 'rge_replacement_key' } }); // pragma: allowlist secret
    await userEvent.click(screen.getByRole('tab', { name: /file upload/i }));
    fireEvent.change(document.getElementById('file-upload') as HTMLInputElement, {
      target: { files: [new File(['cte_type,tlc\nshipping,LOT-1'], 'events.csv')] },
    });
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));

    expect(await screen.findByText('API key could not be saved. Please try again.')).toBeInTheDocument();
    expect(mocks.ingestFile).not.toHaveBeenCalled();
  });

  it('offers the CTE Jev suggested and re-uploads with it only on confirmation', async () => {
    const rejected = Object.assign(new Error('No valid rows found: Row 2: No CTE type'), {
      response: {
        status: 400,
        data: {
          detail: {
            message: 'No valid rows found',
            errors: ['Row 2: No CTE type'],
            cte_type_suggestion: {
              status: 'ok', cte_type: 'receiving', confidence: 0.97, band: 'auto_apply', applied: false,
            },
          },
        },
      },
    });
    mocks.ingestFile.mockRejectedValueOnce(rejected).mockResolvedValueOnce(csvResult(1, 0));
    await uploadCsv();

    expect(await screen.findByText('These rows look like Receiving events (97% confidence).')).toBeInTheDocument();
    expect(mocks.ingestFile).toHaveBeenCalledTimes(1);
    expect(mocks.ingestFile.mock.calls[0][0].cteType).toBeUndefined();

    await userEvent.click(screen.getByRole('button', { name: 'Import as Receiving' }));

    expect(await screen.findByText('CSV processed')).toBeInTheDocument();
    expect(mocks.ingestFile).toHaveBeenCalledTimes(2);
    expect(mocks.ingestFile.mock.calls[1][0]).toMatchObject({ apiKey: 'cookie-managed', cteType: 'receiving' }); // pragma: allowlist secret
    expect(mocks.ingestFile.mock.calls[1][0].file).toBe(mocks.ingestFile.mock.calls[0][0].file);
    expect(screen.queryByRole('button', { name: 'Import as Receiving' })).not.toBeInTheDocument();
  });

  it('offers nothing when Jev found the file mixed or unclear', async () => {
    mocks.ingestFile.mockRejectedValue(Object.assign(new Error('No valid rows found: Row 2: No CTE type'), {
      response: {
        status: 400,
        data: {
          detail: {
            message: 'No valid rows found',
            errors: ['Row 2: No CTE type'],
            cte_type_suggestion: { status: 'ok', cte_type: null, confidence: 0.9, band: 'auto_apply', applied: false },
          },
        },
      },
    }));
    await uploadCsv();

    expect(await screen.findByText('No valid rows found: Row 2: No CTE type')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Import as/ })).not.toBeInTheDocument();
  });

  it('lists Jev column suggestions on a rejected upload and on a partial one', async () => {
    const lotSuggestion = {
      source_header: 'Lot #', source_key: 'lot_#', canonical_field: 'traceability_lot_code',
      confidence: 0.97, band: 'auto_apply', applied: false, blocked_reason: 'apply_disabled',
    };
    mocks.ingestFile.mockRejectedValueOnce(Object.assign(new Error('No valid rows found: Row 2: missing lot code'), {
      response: {
        status: 400,
        data: { detail: { message: 'No valid rows found', errors: [], header_mapping_suggestions: [lotSuggestion] } },
      },
    }));
    await uploadCsv();
    expect(await screen.findByText(/looks like Traceability Lot Code \(97% confidence\)/)).toBeInTheDocument();
    expect(screen.getByText(/Rename the column to .Traceability Lot Code. and upload again/)).toBeInTheDocument();

    mocks.ingestFile.mockResolvedValueOnce({ ...csvResult(1, 1), header_mapping_suggestions: [lotSuggestion] });
    await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));
    expect(await screen.findByText('CSV partially accepted')).toBeInTheDocument();
    expect(screen.getByText(/looks like Traceability Lot Code/)).toBeInTheDocument();
  });

  it('limits the chooser to the CSV contract', async () => {
    render(<IngestPage />);
    await userEvent.click(screen.getByRole('tab', { name: /file upload/i }));
    expect(document.getElementById('file-upload')).toHaveAttribute('accept', '.csv,text/csv');
    expect(screen.getByText('CSV files up to 5MB')).toBeInTheDocument();
  });
});


describe('URL document receipt', () => {
  it('shows the synchronous document ID without treating it as a job', async () => {
    mocks.ingestURL.mockResolvedValue({ document_id: 'document-sync-42' });
    render(<IngestPage />);
    await userEvent.type(screen.getByPlaceholderText(/https:/i), 'https://example.org/regulation');
    await userEvent.click(screen.getByRole('button', { name: /ingest document/i }));
    expect(await screen.findByText(/document-sync-42/)).toBeInTheDocument();
    expect(mocks.getIngestionJob).not.toHaveBeenCalled();
  });
});


describe('Ingestion response identity and failed terminal status', () => {
  it('ignores a late URL response after the input changes', async () => {
    let finish!: (receipt: { document_id: string }) => void;
    mocks.ingestURL.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    render(<IngestPage />);
    const input = screen.getByPlaceholderText(/https:/i);
    await userEvent.type(input, 'https://example.org/A');
    await userEvent.click(screen.getByRole('button', { name: /ingest document/i }));
    fireEvent.change(input, { target: { value: 'https://example.org/B' } });
    await act(async () => finish({ document_id: 'stale-document-A' }));
    expect(screen.queryByText(/stale-document-A/)).not.toBeInTheDocument();
  });

  it('renders failed polling as a terminal failure', async () => {
    mocks.ingestURL.mockResolvedValueOnce({ job_id: 'async-job-42' });
    mocks.getIngestionJob.mockResolvedValueOnce({ status: 'failed' });
    render(<IngestPage />);
    await userEvent.type(screen.getByPlaceholderText(/https:/i), 'https://example.org/job');
    await userEvent.click(screen.getByRole('button', { name: /ingest document/i }));
    expect(await screen.findByText('Job async-job-42')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('Status: FAILED')).toBeInTheDocument(), { timeout: 3500 });
    expect(screen.getByText(/Document processing failed/)).toBeInTheDocument();
    expect(screen.queryByText('Ingestion request completed')).not.toBeInTheDocument();
  });

  it('keeps the durable run receipt without linking legacy IDs as canonical records', async () => {
    mocks.ingestFile.mockResolvedValueOnce({ ...csvResult(1, 0), ingestion_run_id: 'run-source-42' });
    await uploadCsv();
    expect(await screen.findByRole('link', { name: 'run-source-42' })).toHaveAttribute('href', '/api/ingestion/api/v1/records/ingestion-runs/run-source-42');
    expect(screen.queryByRole('link', { name: 'evt-1' })).not.toBeInTheDocument();
  });
});


describe('Reviewed ingestion context transitions', () => {
  beforeEach(() => { mocks.urlError = null; });
  it('clears and disposes a received job when switching tabs', async () => {
    mocks.ingestURL.mockResolvedValueOnce({ job_id: 'job-before-tab' });
    let finish!: (value: { status: string }) => void;
    mocks.getIngestionJob.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; }));
    render(<IngestPage />);
    await userEvent.type(screen.getByPlaceholderText(/https:/i), 'https://example.org/job');
    await userEvent.click(screen.getByRole('button', { name: /ingest document/i }));
    expect(await screen.findByText('Job job-before-tab')).toBeInTheDocument();
    await waitFor(() => expect(finish).toBeDefined(), { timeout: 3500 });
    await userEvent.click(screen.getByRole('tab', { name: /file upload/i }));
    await userEvent.click(screen.getByRole('tab', { name: /URL ingestion/i }));
    expect(screen.queryByText('Job job-before-tab')).not.toBeInTheDocument();
    await act(async () => finish({ status: 'completed' }));
    expect(screen.queryByText('Ingestion request completed')).not.toBeInTheDocument();
  });

  it('clears a retained job when an example replaces the input', async () => {
    mocks.ingestURL.mockResolvedValueOnce({ job_id: 'job-before-example' });
    render(<IngestPage />);
    await userEvent.type(screen.getByPlaceholderText(/https:/i), 'https://example.org/job');
    await userEvent.click(screen.getByRole('button', { name: /ingest document/i }));
    expect(await screen.findByText('Job job-before-example')).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'FDA Regulations (21 CFR)' }));
    expect(screen.queryByText('Job job-before-example')).not.toBeInTheDocument();
  });

  it('suppresses a stale observer error after an example replaces pending input', async () => {
    let reject!: (error: Error) => void;
    mocks.ingestURL.mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }));
    render(<IngestPage />);
    await userEvent.type(screen.getByPlaceholderText(/https:/i), 'https://example.org/A');
    await userEvent.click(screen.getByRole('button', { name: /ingest document/i }));
    await userEvent.click(screen.getByRole('button', { name: 'FDA Regulations (21 CFR)' }));
    await act(async () => { mocks.urlError = new Error('URL A rejected'); reject(mocks.urlError); });
    expect(screen.queryByText('URL A rejected')).not.toBeInTheDocument();
    expect(screen.queryByText('Ingestion Failed')).not.toBeInTheDocument();
  });

  it('clears a current failure when the URL is edited', async () => {
    mocks.ingestURL.mockImplementationOnce(async () => { mocks.urlError = new Error('URL A rejected'); throw mocks.urlError; });
    render(<IngestPage />);
    const input = screen.getByPlaceholderText(/https:/i);
    await userEvent.type(input, 'https://example.org/A');
    await userEvent.click(screen.getByRole('button', { name: /ingest document/i }));
    expect((await screen.findAllByText('URL A rejected')).length).toBeGreaterThan(0);
    fireEvent.change(input, { target: { value: 'https://example.org/B' } });
    expect(screen.queryByText('URL A rejected')).not.toBeInTheDocument();
  });
});
