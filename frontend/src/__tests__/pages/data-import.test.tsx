import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { DataImportClient } from '@/app/tools/data-import/components/DataImportClient';

const mocks = vi.hoisted(() => ({ ingestFile: vi.fn(), toast: vi.fn() }));
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ apiKey: 'cookie-managed' }), // pragma: allowlist secret
}));
vi.mock('@/lib/api-client', () => ({ apiClient: { ingestFile: mocks.ingestFile } }));
vi.mock('@/components/ui/use-toast', () => ({ toast: mocks.toast }));
vi.mock('@/components/layout/FreeToolPageShell', () => ({
  FreeToolPageShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));
vi.mock('@/components/lead-gate/LeadGate', () => ({
  LeadGate: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

async function uploadCsv() {
  render(<DataImportClient />);
  fireEvent.change(screen.getByLabelText('Upload CSV file'), {
    target: { files: [new File(['cte_type,tlc\nshipping,LOT-1'], 'events.csv', { type: 'text/csv' })] },
  });
  await userEvent.click(screen.getByRole('button', { name: /submit to ingestion pipeline/i }));
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

describe('Data Import Hub CSV results', () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([
    [2, 0, 'CSV processed'],
    [1, 1, 'CSV partially accepted'],
    [0, 2, 'No rows accepted'],
  ])('shows %i accepted and %i rejected truthfully', async (accepted, rejected, title) => {
    mocks.ingestFile.mockResolvedValue(csvResult(accepted, rejected));
    await uploadCsv();
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(`${accepted} of 2 rows accepted; ${rejected} rejected.`)).toBeInTheDocument();
    expect(screen.queryByText('Uploaded successfully')).not.toBeInTheDocument();
    expect(screen.queryByText(/Job ID:/)).not.toBeInTheDocument();
  });

  it('shows row rejection details and KDE warnings', async () => {
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

  it('uses the normalized error message instead of rendering an error detail object', async () => {
    const error = Object.assign(new Error('No valid rows found: Row 2: No CTE type'), {
      response: { status: 400, data: { detail: { message: 'No valid rows found', errors: ['Row 2: No CTE type'] } } },
    });
    mocks.ingestFile.mockRejectedValue(error);
    await uploadCsv();
    expect(await screen.findByText('No valid rows found: Row 2: No CTE type')).toBeInTheDocument();
    expect(screen.queryByText('CSV processed')).not.toBeInTheDocument();
  });

  it('offers the CTE Jev suggested and re-uploads with it only on confirmation', async () => {
    const error = Object.assign(new Error('No valid rows found: Row 2: No CTE type'), {
      response: {
        status: 400,
        data: {
          detail: {
            message: 'No valid rows found',
            errors: ['Row 2: No CTE type'],
            cte_type_suggestion: {
              status: 'ok', cte_type: 'shipping', confidence: 0.912, band: 'auto_apply', applied: false,
            },
          },
        },
      },
    });
    mocks.ingestFile.mockRejectedValueOnce(error).mockResolvedValueOnce(csvResult(1, 0));
    await uploadCsv();

    expect(await screen.findByText('These rows look like Shipping events (91% confidence).')).toBeInTheDocument();
    expect(mocks.ingestFile).toHaveBeenLastCalledWith('cookie-managed', expect.any(File), 'data_import_hub', undefined);

    await userEvent.click(screen.getByRole('button', { name: 'Import as Shipping' }));

    expect(await screen.findByText('CSV processed')).toBeInTheDocument();
    expect(mocks.ingestFile).toHaveBeenCalledTimes(2);
    expect(mocks.ingestFile).toHaveBeenLastCalledWith('cookie-managed', expect.any(File), 'data_import_hub', 'shipping');
  });

  it('does not offer a suggestion again after a confirmed CTE is rejected', async () => {
    const error = Object.assign(new Error('No valid rows found: Row 2: Missing receive_date'), {
      response: {
        status: 400,
        data: {
          detail: {
            message: 'No valid rows found',
            errors: ['Row 2: Missing receive_date'],
            cte_type_suggestion: {
              status: 'ok', cte_type: 'receiving', confidence: 0.95, band: 'auto_apply', applied: false,
            },
          },
        },
      },
    });
    mocks.ingestFile.mockRejectedValue(error);
    await uploadCsv();
    await userEvent.click(await screen.findByRole('button', { name: 'Import as Receiving' }));

    expect(await screen.findByText('No valid rows found: Row 2: Missing receive_date')).toBeInTheDocument();
    expect(mocks.ingestFile).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole('button', { name: /^Import as/ })).not.toBeInTheDocument();
  });

  it('starts one upload however fast Import as is clicked', async () => {
    const error = Object.assign(new Error('No valid rows found: Row 2: No CTE type'), {
      response: {
        status: 400,
        data: {
          detail: {
            message: 'No valid rows found',
            errors: ['Row 2: No CTE type'],
            cte_type_suggestion: {
              status: 'ok', cte_type: 'receiving', confidence: 0.95, band: 'auto_apply', applied: false,
            },
          },
        },
      },
    });
    // The re-upload stays in flight, as a slow network would keep it.
    mocks.ingestFile.mockRejectedValueOnce(error).mockReturnValueOnce(new Promise(() => {}));
    await uploadCsv();
    const importButton = await screen.findByRole('button', { name: 'Import as Receiving' });

    // The result panel animates out, so the button stays in the page (and
    // clickable) for a moment after the first click.
    fireEvent.click(importButton);
    fireEvent.click(importButton);
    fireEvent.click(screen.getByRole('button', { name: /uploading/i }));

    expect(mocks.ingestFile).toHaveBeenCalledTimes(2);
    expect(mocks.ingestFile).toHaveBeenLastCalledWith('cookie-managed', expect.any(File), 'data_import_hub', 'receiving');
  });

  it('rejects TSV before calling the CSV endpoint', async () => {
    render(<DataImportClient />);
    fireEvent.change(screen.getByLabelText('Upload CSV file'), {
      target: { files: [new File(['a\tb'], 'events.tsv', { type: 'text/tab-separated-values' })] },
    });
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'Invalid file type' }));
    expect(screen.queryByRole('button', { name: /submit to ingestion pipeline/i })).not.toBeInTheDocument();
    expect(mocks.ingestFile).not.toHaveBeenCalled();
  });

  it('rejects files larger than the server five-megabyte limit', async () => {
    render(<DataImportClient />);
    const oversized = new File([new Uint8Array(5 * 1024 * 1024 + 1)], 'events.csv', { type: 'text/csv' });
    fireEvent.change(screen.getByLabelText('Upload CSV file'), { target: { files: [oversized] } });
    expect(mocks.toast).toHaveBeenCalledWith(expect.objectContaining({ title: 'File too large' }));
    expect(screen.queryByRole('button', { name: /submit to ingestion pipeline/i })).not.toBeInTheDocument();
    expect(mocks.ingestFile).not.toHaveBeenCalled();
  });
});
