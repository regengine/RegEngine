/**
 * SEL-414: the QA Health card and the "Needs attention" panel read the same
 * selector (useQASignal), so they can never disagree.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

import DashboardPage from '@/app/dashboard/page';
import { useAuth } from '@/lib/auth-context';
import { useTenant } from '@/lib/tenant-context';
import { useQAHealth, useSystemMetrics } from '@/hooks/use-api';
import type { QAHealthResponse } from '@/types/api';

vi.mock('next/navigation', () => ({ useRouter: vi.fn(() => ({ push: vi.fn() })) }));
vi.mock('@/lib/auth-context', () => ({ useAuth: vi.fn() }));
vi.mock('@/lib/tenant-context', () => ({ useTenant: vi.fn() }));
vi.mock('@/hooks/use-onboarding', () => ({ useOnboardingStatus: vi.fn(() => ({ data: undefined })) }));
vi.mock('@/components/dashboard/getting-started-card', () => ({ GettingStartedCard: () => null }));
vi.mock('@/components/dashboard/system-health-widget', () => ({ SystemHealthWidget: () => null }));
vi.mock('@/components/dashboard/scan-history-widget', () => ({ ScanHistoryWidget: () => null }));
vi.mock('@/lib/api-hooks', () => ({ fetchWorkbenchReadinessSummary: vi.fn(() => new Promise(() => {})) }));
vi.mock('@/hooks/use-api', () => ({
  useSystemMetrics: vi.fn(() => ({ data: undefined, isLoading: false, error: null, refetch: vi.fn() })),
  useSystemStatus: vi.fn(() => ({
    data: { overall_status: 'healthy', services: [] },
    isLoading: false,
    error: null,
  })),
  useQAHealth: vi.fn(),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DashboardPage />
    </QueryClientProvider>,
  );
}

function attentionPanel() {
  return screen.getByRole('heading', { name: /needs attention/i }).closest('section') as HTMLElement;
}

const passing: QAHealthResponse = {
  schema_version: '1.0',
  generated_at: '',
  source: { kind: 'ci_artifact' },
  overall: { status: 'passing', ready_percent: 0, blocking_count: 0, advisory_count: 0 },
  suites: [],
  clusters: [],
  decision_checks: [],
  artifact_refs: [],
};

describe('Dashboard QA agreement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useSystemMetrics).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useSystemMetrics>);
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '', email: '', is_sysadmin: true, status: 'active' },
      isHydrated: true,
    } as ReturnType<typeof useAuth>);
    vi.mocked(useTenant).mockReturnValue({
      tenantId: '',
      isTenantReady: true,
    } as ReturnType<typeof useTenant>);
  });

  it('a failed QA load is failed in both the card and the attention panel', () => {
    vi.mocked(useQAHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('timeout'),
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useQAHealth>);

    renderPage();

    const panel = attentionPanel();
    expect(within(panel).getByText('QA signal failed')).toBeInTheDocument();
    expect(within(panel).queryByText('Nothing needs attention')).not.toBeInTheDocument();
    // The card says the same thing.
    expect(screen.getAllByText('QA signal failed').length).toBeGreaterThanOrEqual(2);
    expect(screen.queryByText(/0% ready/)).not.toBeInTheDocument();
  });

  it('while QA health loads, only the QA row is loading and it is not counted', () => {
    vi.mocked(useSystemMetrics).mockReturnValue({
      data: { open_alerts: 0, events_ingested: 0, chain_length: 0, chain_valid: false },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useSystemMetrics>);
    vi.mocked(useQAHealth).mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useQAHealth>);

    renderPage();

    const panel = attentionPanel();
    expect(within(panel).getByText('Checking QA signal')).toBeInTheDocument();
    expect(within(panel).queryByText('Nothing needs attention')).not.toBeInTheDocument();
    // The count badge covers only real items, not the pending QA check.
    expect(within(panel).getByRole('heading', { name: /needs attention/i })).toHaveTextContent(/needs attention$/i);
  });

  it('a passing gate is passing in both', () => {
    vi.mocked(useQAHealth).mockReturnValue({
      data: passing,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useQAHealth>);

    renderPage();

    expect(within(attentionPanel()).getByText('Nothing needs attention')).toBeInTheDocument();
    expect(screen.getByText('Release gate passing')).toBeInTheDocument();
  });

  it('an aborted QA fetch shows the timeout copy in both the card and the attention panel', () => {
    vi.mocked(useQAHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new DOMException('The operation was aborted.', 'AbortError'),
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useQAHealth>);

    renderPage();

    const panel = attentionPanel();
    expect(within(panel).getByText('The QA signal did not respond.')).toBeInTheDocument();
    expect(screen.getAllByText('The QA signal did not respond.').length).toBeGreaterThanOrEqual(2);
  });
});
