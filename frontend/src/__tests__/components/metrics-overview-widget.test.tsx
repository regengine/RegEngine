import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import { MetricsOverviewWidget, CSV_UPLOAD_HREF } from '@/components/dashboard/metrics-overview-widget';
import { useSystemMetrics, useSystemStatus } from '@/hooks/use-api';

vi.mock('@/hooks/use-api', () => ({
  useSystemMetrics: vi.fn(),
  useSystemStatus: vi.fn(),
}));

const refetch = vi.fn();

function mockMetrics(value: Partial<ReturnType<typeof useSystemMetrics>>) {
  vi.mocked(useSystemMetrics).mockReturnValue({
    data: undefined,
    isLoading: false,
    error: null,
    refetch,
    ...value,
  } as unknown as ReturnType<typeof useSystemMetrics>);
}

const emptyMetrics = {
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

describe('MetricsOverviewWidget', () => {
  afterEach(() => vi.unstubAllEnvs());

  beforeEach(() => {
    vi.clearAllMocks();
    // Alerts page is flag-gated; these cases cover the alerts-enabled tile.
    vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', 'true');
    vi.mocked(useSystemStatus).mockReturnValue({
      data: { overall_status: 'healthy', services: [] },
    } as unknown as ReturnType<typeof useSystemStatus>);
  });

  it('empty tiles say "No data yet" with a CSV upload link — no dash placeholders', () => {
    mockMetrics({ data: emptyMetrics });
    const { container } = render(<MetricsOverviewWidget readiness={undefined} />);

    // Score, CTE events, hash chain, open fixes.
    expect(screen.getAllByText('No data yet')).toHaveLength(4);
    const links = screen.getAllByRole('link', { name: 'Upload a CSV' });
    expect(links).toHaveLength(4);
    links.forEach((link) => expect(link).toHaveAttribute('href', CSV_UPLOAD_HREF));
    expect(container.textContent).not.toContain('—');
    // A real zero is a value, not an empty tile.
    expect(screen.getByText('0')).toBeInTheDocument();
  });

  it('a failed metrics load shows the error state with Retry, not placeholder zeros', () => {
    // Nothing real has ever loaded: no data, only an error.
    mockMetrics({ data: undefined, error: new Error('Network Error') });
    render(<MetricsOverviewWidget readiness={undefined} />);

    expect(screen.getByRole('alert')).toHaveTextContent(/couldn't load dashboard metrics/i);
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
    expect(screen.queryByText('No data yet')).not.toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
  });

  it('a failed refresh after a good load leaves the rendered tiles unchanged and shows a non-blocking note', () => {
    mockMetrics({ data: emptyMetrics });
    const { container, rerender } = render(<MetricsOverviewWidget readiness={undefined} />);
    const tilesBefore = container.querySelector('.grid')?.textContent;
    // The empty tiles are what loaded; an unchanged grid proves they survived.
    expect(tilesBefore).toContain('No data yet');

    // react-query keeps the last good `data` alongside the refetch `error`.
    mockMetrics({ data: emptyMetrics, error: new Error('Network Error') });
    rerender(<MetricsOverviewWidget readiness={undefined} />);

    expect(container.querySelector('.grid')?.textContent).toBe(tilesBefore);
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByText(/couldn't load dashboard metrics/i)).not.toBeInTheDocument();
    expect(screen.getByRole('status')).toHaveTextContent(/refresh failed/i);
    screen.getByRole('button', { name: 'Retry' }).click();
    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it('alerts disabled: the open alerts tile says "Alerts are off" with no count or CSV link', () => {
    vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '');
    mockMetrics({ data: emptyMetrics });
    render(<MetricsOverviewWidget readiness={undefined} />);

    expect(screen.getByText('Alerts are off')).toBeInTheDocument();
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    // Only score, CTE events, hash chain and open fixes are empty tiles.
    expect(screen.getAllByRole('link', { name: 'Upload a CSV' })).toHaveLength(4);
  });

  it('alerts enabled but no alert count: "No data yet", never a demo zero', () => {
    mockMetrics({ data: { ...emptyMetrics, open_alerts: undefined } });
    render(<MetricsOverviewWidget readiness={undefined} />);

    // Score, CTE events, hash chain, open alerts, open fixes.
    expect(screen.getAllByText('No data yet')).toHaveLength(5);
    expect(screen.queryByText('0')).not.toBeInTheDocument();
    expect(screen.queryByText('Alerts are off')).not.toBeInTheDocument();
  });

  it('a failed readiness load says so on the open fixes tile instead of "No data yet"', () => {
    mockMetrics({ data: emptyMetrics });
    render(<MetricsOverviewWidget readiness={undefined} readinessFailed />);

    expect(screen.getByText("Couldn't load")).toBeInTheDocument();
    // Only score, CTE events and hash chain are empty; open fixes is not.
    expect(screen.getAllByText('No data yet')).toHaveLength(3);
  });
});
