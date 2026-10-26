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

describe('ingestion status timeout', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.storeApiKey.mockResolvedValue(undefined);
  });

  it('shows the status error when a status poll times out', async () => {
    const jobId = crypto.randomUUID();
    mocks.ingestURL.mockResolvedValueOnce({ job_id: jobId });
    // The internal 8s timeout aborts api-client's controller with a
    // TimeoutError while the page's own controller stays live.
    mocks.getIngestionJob.mockRejectedValue(
      new DOMException('Request timed out after 8000ms', 'TimeoutError'),
    );

    render(<IngestPage />);
    fireEvent.change(screen.getByPlaceholderText(/https:\/\//i), {
      target: { value: 'https://example.org/slow.pdf' },
    });
    await userEvent.click(screen.getByRole('button', { name: /^ingest document$/i }));

    expect(mocks.getIngestionJob).toHaveBeenCalledWith(jobId, { signal: expect.any(AbortSignal) });
    expect(await screen.findByText('Unable to fetch ingestion status.')).toBeInTheDocument();
  });

  it('does not swallow failures by error name while the poll is live', async () => {
    const jobId = crypto.randomUUID();
    mocks.ingestURL.mockResolvedValueOnce({ job_id: jobId });
    // Timeouts used to surface as AbortError and were ignored by name.
    // Only the page's own aborted controller may silence an error now.
    mocks.getIngestionJob.mockRejectedValue(
      new DOMException('The operation was aborted', 'AbortError'),
    );

    render(<IngestPage />);
    fireEvent.change(screen.getByPlaceholderText(/https:\/\//i), {
      target: { value: 'https://example.org/flaky.pdf' },
    });
    await userEvent.click(screen.getByRole('button', { name: /^ingest document$/i }));

    expect(await screen.findByText('Unable to fetch ingestion status.')).toBeInTheDocument();
  });
});

describe('ingestion status retry on terminal status', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.storeApiKey.mockResolvedValue(undefined);
  });

  it('stops the polling interval when Retry receives a terminal status', async () => {
    const jobId = crypto.randomUUID();
    mocks.ingestURL.mockResolvedValueOnce({ job_id: jobId });
    // First poll fails so the Retry action appears; the retry then resolves
    // terminal. Later ticks (if any) stay non-terminal.
    mocks.getIngestionJob
      .mockRejectedValueOnce(new Error('status fetch failed'))
      .mockResolvedValueOnce({ status: 'completed' })
      .mockResolvedValue({ status: 'queued' });
    const setIntervalSpy = vi.spyOn(window, 'setInterval');
    const clearIntervalSpy = vi.spyOn(window, 'clearInterval');
    try {
      render(<IngestPage />);
      fireEvent.change(screen.getByPlaceholderText(/https:\/\//i), {
        target: { value: 'https://example.org/terminal.pdf' },
      });
      await userEvent.click(screen.getByRole('button', { name: /^ingest document$/i }));

      const retryButton = await screen.findByRole('button', { name: 'Retry' });
      // The poll interval started by this job's effect is the most recent one.
      const intervals = setIntervalSpy.mock.results;
      const pollIntervalId = intervals[intervals.length - 1]?.value;
      expect(pollIntervalId).toBeDefined();

      await userEvent.click(retryButton);

      await waitFor(() => {
        expect(clearIntervalSpy).toHaveBeenCalledWith(pollIntervalId);
      });
      // Terminal status applied: the form card flips to the completed view.
      expect(await screen.findByText('Ingestion request completed')).toBeInTheDocument();
    } finally {
      setIntervalSpy.mockRestore();
      clearIntervalSpy.mockRestore();
    }
  });
});

describe('ingestion status terminal abort and no-regression', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.storeApiKey.mockResolvedValue(undefined);
  });

  it('aborts the in-flight poll when Retry observes terminal and ignores its late result', async () => {
    const jobId = crypto.randomUUID();
    mocks.ingestURL.mockResolvedValueOnce({ job_id: jobId });

    let resolveHangingPoll: ((value: { status: string }) => void) | null = null;
    let hangingSignal: AbortSignal | undefined;
    let callCount = 0;
    mocks.getIngestionJob.mockImplementation((_id: string, options?: { signal?: AbortSignal }) => {
      callCount += 1;
      if (callCount === 1) {
        return Promise.reject(new Error('status fetch failed'));
      }
      if (callCount === 2) {
        hangingSignal = options?.signal;
        return new Promise<{ status: string }>((resolve) => {
          resolveHangingPoll = resolve;
        });
      }
      if (callCount === 3) {
        return Promise.resolve({ status: 'completed' });
      }
      return Promise.resolve({ status: 'queued' });
    });

    const clearIntervalSpy = vi.spyOn(window, 'clearInterval');
    try {
      render(<IngestPage />);
      fireEvent.change(screen.getByPlaceholderText(/https:\/\//i), {
        target: { value: 'https://example.org/abort.pdf' },
      });
      await userEvent.click(screen.getByRole('button', { name: /^ingest document$/i }));

      const retryButton = await screen.findByRole('button', { name: 'Retry' });

      // Wait for the 2s interval tick to start the hanging second poll.
      await waitFor(() => expect(mocks.getIngestionJob).toHaveBeenCalledTimes(2), { timeout: 8000 });
      expect(hangingSignal).toBeInstanceOf(AbortSignal);
      expect(hangingSignal?.aborted).toBe(false);

      await userEvent.click(retryButton);

      // Retry terminal: completed view, interval cleared.
      expect(await screen.findByText('Ingestion request completed')).toBeInTheDocument();
      expect(clearIntervalSpy).toHaveBeenCalled();

      // The in-flight poll fetch was aborted via its AbortController.
      expect(hangingSignal?.aborted).toBe(true);

      // Its late non-terminal result must not regress the terminal status.
      resolveHangingPoll?.({ status: 'queued' });
      await new Promise((r) => setTimeout(r, 100));
      expect(await screen.findByText('Ingestion request completed')).toBeInTheDocument();
    } finally {
      clearIntervalSpy.mockRestore();
    }
  }, 15000);
});
