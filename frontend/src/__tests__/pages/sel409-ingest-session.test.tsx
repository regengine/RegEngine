import { expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import IngestPage from '@/app/ingest/page';

const ingestFile = vi.fn((_input: { apiKey?: string; file: File }) => new Promise(() => {}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ isAuthenticated: true, apiKey: null, setApiKey: vi.fn() }),
}));
vi.mock('@/hooks/use-api', () => ({
  useIngestURL: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false }),
  useIngestFile: () => ({ mutateAsync: ingestFile, isPending: false, isError: false }),
  useIngestEpcisEvent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useIngestEpcisBatch: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useIngestEpcisXml: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useValidateEpcisEvent: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/lib/api-client', () => ({ apiClient: { getIngestionJob: vi.fn() } }));
vi.mock('@/hooks/use-dashboard-refresh', () => ({ notifyDashboardRefresh: vi.fn() }));
vi.mock('@/app/ingest/NormalizedDocumentViewer', () => ({
  NormalizedDocumentViewer: () => null,
}));

it('uses the owner session without prompting for an API key', async () => {
  render(<IngestPage />);
  expect(screen.queryByText('API Key Required')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('API Key')).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole('tab', { name: /file upload/i }));
  fireEvent.change(document.getElementById('file-upload') as HTMLInputElement, {
    target: { files: [new File(['cte_type,tlc\nshipping,LOT-1'], 'events.csv')] },
  });
  await userEvent.click(screen.getByRole('button', { name: /upload & process/i }));

  await waitFor(() => expect(ingestFile).toHaveBeenCalledTimes(1));
  expect(ingestFile.mock.calls[0][0]).toMatchObject({ apiKey: undefined });
});
