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

describe('Data Import Hub CSV results', () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([
    [2, 0, 'CSV import complete'],
    [1, 1, 'CSV import partially accepted'],
    [0, 2, 'No rows imported'],
  ])('shows %i accepted and %i rejected truthfully', async (accepted, rejected, title) => {
    mocks.ingestFile.mockResolvedValue({ total: 2, accepted, rejected, events: [] });
    await uploadCsv();
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText(`${accepted} of 2 rows accepted; ${rejected} rejected.`)).toBeInTheDocument();
    expect(screen.queryByText('Uploaded successfully')).not.toBeInTheDocument();
    expect(screen.queryByText(/Job ID:/)).not.toBeInTheDocument();
  });

  it('shows row rejection details and KDE warnings', async () => {
    mocks.ingestFile.mockResolvedValue({
      total: 2, accepted: 1, rejected: 1,
      events: [{ status: 'rejected', errors: ['Row 3: Quantity must be positive'] }],
      kde_warnings: ['Row 2: Missing KDEs: reference_document'],
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
    expect(screen.queryByText('CSV import complete')).not.toBeInTheDocument();
  });
});
