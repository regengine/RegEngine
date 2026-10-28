import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IngestPage from '@/app/ingest/page';

const mocks = vi.hoisted(() => ({
  ingestFile: vi.fn(),
  ingestURL: vi.fn(),
  ingestEpcisEvent: vi.fn(),
  ingestEpcisBatch: vi.fn(),
  ingestEpcisXml: vi.fn(),
  validateEpcis: vi.fn(),
  getIngestionJob: vi.fn(),
  refresh: vi.fn(),
  storeApiKey: vi.fn(),
}));

let ingestURLData: any = undefined;

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ apiKey: 'cookie-managed', setApiKey: mocks.storeApiKey }), // pragma: allowlist secret
}));
vi.mock('@/hooks/use-api', () => ({
  useIngestURL: () => ({
    mutateAsync: async (args: any) => {
      const data = await mocks.ingestURL(args);
      ingestURLData = data;
      return data;
    },
    reset: vi.fn(() => {
      ingestURLData = undefined;
    }),
    get data() {
      return ingestURLData;
    },
    isPending: false,
    isError: false,
  }),
  useIngestFile: () => ({ mutateAsync: mocks.ingestFile, reset: vi.fn(), isPending: false, isError: false }),
  useIngestEpcisEvent: () => ({ mutateAsync: mocks.ingestEpcisEvent, reset: vi.fn(), isPending: false }),
  useIngestEpcisBatch: () => ({ mutateAsync: mocks.ingestEpcisBatch, reset: vi.fn(), isPending: false }),
  useIngestEpcisXml: () => ({ mutateAsync: mocks.ingestEpcisXml, reset: vi.fn(), isPending: false }),
  useValidateEpcisEvent: () => ({ mutateAsync: mocks.validateEpcis, reset: vi.fn(), isPending: false }),
}));
vi.mock('@/lib/api-client', () => ({
  apiClient: { getIngestionJob: mocks.getIngestionJob },
}));
vi.mock('@/hooks/use-dashboard-refresh', () => ({
  notifyDashboardRefresh: mocks.refresh,
}));
vi.mock('@/app/ingest/NormalizedDocumentViewer', () => ({
  NormalizedDocumentViewer: ({ documentId }: { documentId?: string }) => (
    <div>
      <div>Normalized document viewer</div>
      {documentId && <div>Receipt: {documentId}</div>}
    </div>
  ),
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
    ingestURLData = undefined;
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

  it('shows the API-key save error on the URL tab without sending a request', async () => {
    mocks.storeApiKey.mockRejectedValue(new Error('API key could not be saved. Please try again.'));
    render(<IngestPage />);
    await userEvent.click(screen.getByRole('tab', { name: /url ingestion/i }));
    fireEvent.change(screen.getByPlaceholderText('rge_...'), { target: { value: 'rge_replacement_key' } }); // pragma: allowlist secret
    fireEvent.change(screen.getByPlaceholderText('https://example.com/regulatory-document.pdf'), {
      target: { value: 'https://example.com/regulatory-document.pdf' },
    });
    await userEvent.click(screen.getByRole('button', { name: /ingest|upload & process/i }));

    expect(await screen.findByText('API key could not be saved. Please try again.')).toBeInTheDocument();
    expect(screen.getByText('Ingestion Failed')).toBeInTheDocument();
    expect(document.querySelector('.workspace-load-error')).not.toBeNull();
    expect(mocks.ingestURL).not.toHaveBeenCalled();
  });

  it('clears URL API-key save error when switching tabs and does not reappear on returning to URL tab', async () => {
    mocks.storeApiKey.mockRejectedValue(new Error('API key could not be saved. Please try again.'));
    render(<IngestPage />);
    await userEvent.click(screen.getByRole('tab', { name: /url ingestion/i }));
    fireEvent.change(screen.getByPlaceholderText('rge_...'), { target: { value: 'rge_replacement_key' } }); // pragma: allowlist secret
    fireEvent.change(screen.getByPlaceholderText('https://example.com/regulatory-document.pdf'), {
      target: { value: 'https://example.com/regulatory-document.pdf' },
    });
    await userEvent.click(screen.getByRole('button', { name: /ingest|upload & process/i }));

    expect(await screen.findByText('API key could not be saved. Please try again.')).toBeInTheDocument();
    expect(screen.getByText('Ingestion Failed')).toBeInTheDocument();
    expect(document.querySelector('.workspace-load-error')).not.toBeNull();

    await userEvent.click(screen.getByRole('tab', { name: /file upload/i }));

    expect(screen.queryByText('API key could not be saved. Please try again.')).not.toBeInTheDocument();
    expect(screen.queryByText('Ingestion Failed')).not.toBeInTheDocument();
    expect(document.querySelector('.workspace-load-error')).toBeNull();

    await userEvent.click(screen.getByRole('tab', { name: /url ingestion/i }));

    expect(screen.queryByText('API key could not be saved. Please try again.')).not.toBeInTheDocument();
    expect(screen.queryByText('Ingestion Failed')).not.toBeInTheDocument();
    expect(document.querySelector('.workspace-load-error')).toBeNull();
  });

  it('keeps previous job progress visible when API key save fails on subsequent submit', async () => {
    const jobId = crypto.randomUUID();
    mocks.ingestURL.mockResolvedValue({ job_id: jobId, status: 'queued' });
    mocks.getIngestionJob.mockResolvedValue({ status: 'queued' });
    render(<IngestPage />);

    await userEvent.click(screen.getByRole('tab', { name: /url ingestion/i }));
    fireEvent.change(screen.getByPlaceholderText('https://example.com/regulatory-document.pdf'), {
      target: { value: 'https://example.com/regulatory-document.pdf' },
    });
    await userEvent.click(screen.getByRole('button', { name: /ingest|upload & process/i }));

    expect(await screen.findByText('Ingestion Progress')).toBeInTheDocument();
    expect(screen.getByText(`Job ${jobId}`)).toBeInTheDocument();

    mocks.storeApiKey.mockRejectedValue(new Error('API key could not be saved. Please try again.'));
    fireEvent.change(screen.getByPlaceholderText('rge_...'), { target: { value: 'rge_replacement_key' } }); // pragma: allowlist secret
    await userEvent.click(screen.getByRole('button', { name: /ingest|upload & process/i }));

    expect(await screen.findByText('API key could not be saved. Please try again.')).toBeInTheDocument();
    expect(screen.getByText('Ingestion Progress')).toBeInTheDocument();
    expect(screen.getByText(`Job ${jobId}`)).toBeInTheDocument();
  });

  it('shows save error in completed view while retaining previous job receipt data on failed resubmit', async () => {
    const jobId = crypto.randomUUID();
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    try {
      mocks.ingestURL.mockResolvedValue({ job_id: jobId, status: 'queued' });
      mocks.getIngestionJob.mockResolvedValue({ status: 'queued' });
      render(<IngestPage />);

      await userEvent.click(screen.getByRole('tab', { name: /url ingestion/i }));
      fireEvent.change(screen.getByPlaceholderText('https://example.com/regulatory-document.pdf'), {
        target: { value: 'https://example.com/regulatory-document.pdf' },
      });
      await userEvent.click(screen.getByRole('button', { name: /ingest|upload & process/i }));

      expect(await screen.findByText('Ingestion Progress')).toBeInTheDocument();
      expect(screen.getByText(`Job ${jobId}`)).toBeInTheDocument();

      mocks.storeApiKey.mockRejectedValue(new Error('API key could not be saved. Please try again.'));
      fireEvent.change(screen.getByPlaceholderText('rge_...'), { target: { value: 'rge_replacement_key' } }); // pragma: allowlist secret
      await userEvent.click(screen.getByRole('button', { name: /ingest|upload & process/i }));

      expect(await screen.findByText('API key could not be saved. Please try again.')).toBeInTheDocument();

      mocks.getIngestionJob.mockResolvedValue({ status: 'completed' });
      await vi.advanceTimersByTimeAsync(2000);

      expect(await screen.findByText('API key could not be saved. Please try again.')).toBeInTheDocument();
      expect(screen.getByRole('alert')).toHaveTextContent('API key could not be saved. Please try again.');
      expect(screen.getByText('Normalized document viewer')).toBeInTheDocument();
      expect(screen.getByText(`Receipt: ${jobId}`)).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
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
