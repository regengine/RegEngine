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

// Non-empty so every tile renders a figure. The test compares what the widget
// rendered before and after the failed refresh, never specific values.
const firstResponse = {
  total_tenants: 1,
  total_documents: 1,
  active_jobs: 0,
  compliance_score: 72,
  compliance_grade: 'C',
  events_ingested: 1500,
  chain_length: 9,
  chain_valid: true,
  open_alerts: 2,
};
const readiness = { unresolved_fix_count: 3, export_eligible: false } as never;

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
    const { container } = render(<MetricsOverviewWidget readiness={readiness} />, { wrapper });

    // The loading skeleton also renders a .grid; capture only after the load settles.
    await waitFor(() =>
      expect(queryClient.getQueryState(['system', 'metrics'])?.status).toBe('success'),
    );
    const tilesBefore = container.querySelector('.grid')?.textContent;
    // Every tile shows a figure, so an unchanged grid proves the figures survived.
    expect(tilesBefore).toBeTruthy();
    expect(tilesBefore).not.toContain('No data yet');

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
