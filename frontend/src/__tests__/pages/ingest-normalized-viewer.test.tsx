import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import IngestPage from '@/app/ingest/page';

const mocks = vi.hoisted(() => ({
  ingestURL: vi.fn(),
  ingestFile: vi.fn(),
  ingestEpcisEvent: vi.fn(),
  ingestEpcisBatch: vi.fn(),
  ingestEpcisXml: vi.fn(),
  validateEpcis: vi.fn(),
  getIngestionJob: vi.fn(),
  refresh: vi.fn(),
  storeApiKey: vi.fn(),
  urlData: undefined as { job_id?: string; document_id?: string } | undefined,
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ apiKey: 'cookie-managed', setApiKey: mocks.storeApiKey }), // pragma: allowlist secret
}));
vi.mock('@/hooks/use-api', () => ({
  useIngestURL: () => ({ mutateAsync: mocks.ingestURL, data: mocks.urlData, reset: vi.fn(), isPending: false, isError: false }),
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
  NormalizedDocumentViewer: ({ documentId }: { documentId: string }) => (
    <div data-testid="normalized-viewer">{documentId}</div>
  ),
}));

const EMPTY_STATE = 'No normalized document is available for this ingest.';

function mockCompletedUrlIngest(response: { job_id: string; document_id?: string }) {
  mocks.ingestURL.mockImplementation(async () => {
    mocks.urlData = response;
    return response;
  });
  mocks.getIngestionJob.mockResolvedValue({ status: 'completed' });
}

async function submitUrlIngest() {
  render(<IngestPage />);
  fireEvent.change(screen.getByPlaceholderText(/https:\/\//i), {
    target: { value: `https://example.org/document-${crypto.randomUUID()}.pdf` },
  });
  await userEvent.click(screen.getByRole('button', { name: /^ingest document$/i }));
  // The page polls the job every 2s; the mocked poll resolves completed.
  expect(await screen.findByText('Ingestion request completed', {}, { timeout: 5000 })).toBeInTheDocument();
}

describe('completed URL ingest on /ingest', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.urlData = undefined;
    mocks.storeApiKey.mockResolvedValue(undefined);
  });

  it('shows an empty state and no viewer when document_id is absent', async () => {
    mockCompletedUrlIngest({ job_id: crypto.randomUUID() });
    await submitUrlIngest();

    expect(screen.getByText(EMPTY_STATE)).toBeInTheDocument();
    expect(screen.queryByTestId('normalized-viewer')).not.toBeInTheDocument();
  });

  it('shows an empty state and no viewer when document_id is an empty string', async () => {
    mockCompletedUrlIngest({ job_id: crypto.randomUUID(), document_id: '' });
    await submitUrlIngest();

    expect(screen.getByText(EMPTY_STATE)).toBeInTheDocument();
    expect(screen.queryByTestId('normalized-viewer')).not.toBeInTheDocument();
  });

  it('passes the real document id to the viewer when present', async () => {
    const documentId = crypto.randomUUID();
    mockCompletedUrlIngest({ job_id: crypto.randomUUID(), document_id: documentId });
    await submitUrlIngest();

    expect(screen.queryByText(EMPTY_STATE)).not.toBeInTheDocument();
    expect(screen.getByTestId('normalized-viewer')).toHaveTextContent(documentId);
  });
});
