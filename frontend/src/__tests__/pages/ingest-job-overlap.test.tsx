import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ apiKey: 'cookie-managed', setApiKey: mocks.storeApiKey }), // pragma: allowlist secret
}));
vi.mock('@/hooks/use-api', () => ({
  useIngestURL: () => ({ mutateAsync: mocks.ingestURL, reset: vi.fn(), isPending: false, isError: false }),
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
  NormalizedDocumentViewer: () => <div>Normalized document viewer</div>,
}));

describe('ingestion status polling across job switches', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.storeApiKey.mockResolvedValue(undefined);
  });

  it('aborts the old job request and polls the new job immediately', async () => {
    const jobA = crypto.randomUUID();
    const jobB = crypto.randomUUID();
    mocks.ingestURL.mockResolvedValueOnce({ job_id: jobA }).mockResolvedValueOnce({ job_id: jobB });

    const seen: Array<{ jobId: string; signal?: AbortSignal }> = [];
    mocks.getIngestionJob.mockImplementation((jobId: string, options?: { signal?: AbortSignal }) => {
      seen.push({ jobId, signal: options?.signal });
      // The old job's status call hangs: the new job's first poll must still
      // go out immediately instead of being skipped by the stale in-flight one.
      if (seen.length === 1) {
        return new Promise(() => {});
      }
      return Promise.resolve({ status: 'queued' });
    });

    render(<IngestPage />);
    fireEvent.change(screen.getByPlaceholderText(/https:\/\//i), {
      target: { value: 'https://example.org/first.pdf' },
    });
    await userEvent.click(screen.getByRole('button', { name: /^ingest document$/i }));
    expect(await screen.findByText(`Job ${jobA}`)).toBeInTheDocument();
    await waitFor(() => expect(mocks.getIngestionJob).toHaveBeenCalledTimes(1));
    expect(mocks.getIngestionJob).toHaveBeenNthCalledWith(1, jobA, { signal: expect.any(AbortSignal) });
    expect(seen[0].signal).toBeInstanceOf(AbortSignal);

    fireEvent.change(screen.getByPlaceholderText(/https:\/\//i), {
      target: { value: 'https://example.org/second.pdf' },
    });
    await userEvent.click(screen.getByRole('button', { name: /^ingest document$/i }));
    expect(await screen.findByText(`Job ${jobB}`)).toBeInTheDocument();

    // The new job's first poll fires on effect mount, without waiting for the
    // 2s interval and without being skipped by the old job's hung request.
    await waitFor(() => expect(mocks.getIngestionJob).toHaveBeenCalledTimes(2));
    expect(mocks.getIngestionJob).toHaveBeenNthCalledWith(2, jobB, { signal: expect.any(AbortSignal) });
    expect(seen[1].jobId).toBe(jobB);
    expect(seen[1].signal).toBeInstanceOf(AbortSignal);
    expect(seen[1].signal?.aborted).toBe(false);

    // Switching jobs aborted the old job's in-flight request.
    expect(seen[0].signal?.aborted).toBe(true);
  });
});
