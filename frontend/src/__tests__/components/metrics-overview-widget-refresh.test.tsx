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

const realMetrics = {
  total_tenants: 1,
  total_documents: 4,
  active_jobs: 0,
  compliance_score: 72,
  compliance_grade: 'C',
  events_ingested: 1500,
  chain_length: 9,
  chain_valid: true,
  open_alerts: 2,
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

  it('a good load followed by a failed refresh keeps the real numbers visible', async () => {
    mocks.getSystemMetrics.mockResolvedValueOnce(realMetrics);
    render(<MetricsOverviewWidget readiness={undefined} />, { wrapper });

    expect(await screen.findByText('72')).toBeInTheDocument();
    expect(screen.getByText('1,500')).toBeInTheDocument();

    mocks.getSystemMetrics.mockRejectedValueOnce(new Error('Network Error'));
    await act(async () => {
      await queryClient.refetchQueries({ queryKey: ['system', 'metrics'] });
    });

    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(/refresh failed/i));
    expect(mocks.getSystemMetrics).toHaveBeenCalledTimes(2);
    expect(screen.getByText('72')).toBeInTheDocument();
    expect(screen.getByText('1,500')).toBeInTheDocument();
    expect(screen.getByText('Verified')).toBeInTheDocument();
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
