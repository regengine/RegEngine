import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';

const mocks = vi.hoisted(() => ({
  getSystemMetrics: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    getSystemMetrics: (...args: unknown[]) => mocks.getSystemMetrics(...args),
  },
}));

import { MetricsOverviewWidget } from '@/components/dashboard/metrics-overview-widget';

// An all-zero response: no made-up figures. The test compares what the widget
// rendered before and after the failed refresh, never specific values.
const firstResponse = {
  total_tenants: 0,
  total_documents: 0,
  active_jobs: 0,
  compliance_score: 0,
  compliance_grade: '',
  events_ingested: 0,
  chain_length: 0,
  chain_valid: false,
  open_alerts: 0,
};

describe('MetricsOverviewWidget with the real useSystemMetrics hook', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    vi.clearAllMocks();
    // useSystemStatus hits /api/<service>/health directly.
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200 })));
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: Infinity } },
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }

  it('a good load followed by a failed refresh leaves the rendered tiles unchanged', async () => {
    mocks.getSystemMetrics.mockResolvedValueOnce(firstResponse);
    const { container } = render(<MetricsOverviewWidget readiness={undefined} />, { wrapper });

    // The loading skeleton also renders a .grid; capture only after the load settles.
    await waitFor(() =>
      expect(queryClient.getQueryState(['system', 'metrics'])?.status).toBe('success'),
    );
    const tilesBefore = container.querySelector('.grid')?.textContent;
    // The empty tiles are what loaded; an unchanged grid proves they survived.
    expect(tilesBefore).toContain('No data yet');

    mocks.getSystemMetrics.mockRejectedValueOnce(new Error('Network Error'));
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ['system', 'metrics'] });
    });

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/refresh failed/i));
    expect(mocks.getSystemMetrics).toHaveBeenCalledTimes(2);
    // The first response is still the cached data, not replaced by a fallback.
    expect(queryClient.getQueryData(['system', 'metrics'])).toBe(firstResponse);
    expect(container.querySelector('.grid')?.textContent).toBe(tilesBefore);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText(/couldn't load dashboard metrics/i)).not.toBeInTheDocument();
  });

  it('a first load that fails shows the error state, with no placeholder zeros', async () => {
    mocks.getSystemMetrics.mockRejectedValueOnce(new Error('Network Error'));
    render(<MetricsOverviewWidget readiness={undefined} />, { wrapper });

    expect(await screen.findByRole('alert')).toHaveTextContent(/couldn't load dashboard metrics/i);
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    expect(screen.queryByText('No data yet')).not.toBeInTheDocument();
  });
});
