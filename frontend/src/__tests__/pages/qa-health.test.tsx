import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import QAHealthPage from '@/app/dashboard/qa-health/page';
import { useAuth } from '@/lib/auth-context';
import { useQAHealth } from '@/hooks/use-api';
import type { QAHealthResponse } from '@/types/api';

vi.mock('@/lib/auth-context', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/hooks/use-api', () => ({
  useQAHealth: vi.fn(),
}));

vi.mock('@/components/layout/page-container', () => ({
  PageContainer: ({ children }: { children: React.ReactNode }) => (
    <main>{children}</main>
  ),
}));

// Minimal shape the page reads. Strings are field-name placeholders and counts
// are zero, so no assertion depends on invented QA results.
const suite = {
  id: 'suite.id',
  label: 'suite.label',
  command: 'suite.command',
  status: 'failed',
  passed: 0,
  failed: 0,
  skipped: 0,
  errors: 0,
  duration_seconds: null,
  blocking: true,
} satisfies QAHealthResponse['suites'][number];

const cluster = {
  title: 'cluster.title',
  severity: 'critical',
  affected_suites: [suite.id],
  owner_lane: 'cluster.owner_lane',
  impact: 'cluster.impact',
  next_action: 'cluster.next_action',
} satisfies QAHealthResponse['clusters'][number];

const decisionCheck = {
  label: 'decision_check.label',
  status: 'blocking',
  detail: 'decision_check.detail',
} satisfies QAHealthResponse['decision_checks'][number];

const artifactRef = {
  id: 'artifact_ref.id',
  label: 'artifact_ref.label',
  path: 'artifact_ref.path',
  type: 'artifact_ref.type',
} satisfies QAHealthResponse['artifact_refs'][number];

const qaHealth: QAHealthResponse = {
  schema_version: 'schema_version',
  // Not a parseable date: the page renders it verbatim.
  generated_at: 'generated_at',
  source: { kind: 'ci_artifact', workflow: 'source.workflow' },
  overall: { status: 'failing', ready_percent: 0, blocking_count: 0, advisory_count: 0 },
  suites: [suite],
  clusters: [cluster],
  decision_checks: [decisionCheck],
  artifact_refs: [artifactRef],
};

function mockQAHealth(overrides: Partial<ReturnType<typeof useQAHealth>> = {}) {
  const result = {
    data: qaHealth,
    isLoading: false,
    error: null,
    refetch: vi.fn(),
    isRefetching: false,
    ...overrides,
  };
  vi.mocked(useQAHealth).mockReturnValue(result as unknown as ReturnType<typeof useQAHealth>);
  return result;
}

function mockUser(isSysadmin: boolean) {
  vi.mocked(useAuth).mockReturnValue({
    user: { id: 'user.id', email: 'user@example.com', is_sysadmin: isSysadmin, status: 'active' },
    isHydrated: true,
  } as ReturnType<typeof useAuth>);
}

describe('QAHealthPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockQAHealth();
  });

  it('renders sysadmin QA health details from the endpoint payload', async () => {
    mockUser(true);

    const user = userEvent.setup();
    render(<QAHealthPage />);

    expect(screen.getByRole('heading', { name: 'QA Health' })).toBeInTheDocument();
    expect(
      screen.getByText(`Latest CI artifact: ${qaHealth.generated_at} - ${qaHealth.source.workflow}`),
    ).toBeInTheDocument();
    expect(screen.getByText('Release gate failing')).toBeInTheDocument();
    expect(screen.getAllByText(suite.label).length).toBeGreaterThan(0);
    expect(screen.getByText(`${suite.passed.toLocaleString()} pass`)).toBeInTheDocument();
    expect(screen.getByText(cluster.title)).toBeInTheDocument();
    expect(screen.getByText(cluster.impact)).toBeInTheDocument();
    expect(screen.getByText(decisionCheck.label)).toBeInTheDocument();
    expect(screen.getByText(decisionCheck.detail)).toBeInTheDocument();
    expect(screen.getByText(`${qaHealth.overall.blocking_count} blocking`)).toBeInTheDocument();
    expect(screen.getByRole('progressbar', { name: 'QA release readiness' })).toHaveAttribute(
      'aria-valuenow',
      String(qaHealth.overall.ready_percent),
    );

    await user.click(screen.getByRole('tab', { name: 'Artifacts' }));
    expect(screen.getByText(artifactRef.path)).toBeInTheDocument();
    expect(useQAHealth).toHaveBeenCalledWith(true);
  });

  it('blocks non-sysadmin users before fetching QA health', () => {
    mockUser(false);

    render(<QAHealthPage />);

    expect(screen.getByText('Sysadmin access required')).toBeInTheDocument();
    expect(screen.queryByText(suite.label)).not.toBeInTheDocument();
    expect(useQAHealth).toHaveBeenCalledWith(false);
  });

  it('renders empty states when the endpoint reports no QA signal', async () => {
    mockUser(true);
    mockQAHealth({
      data: {
        ...qaHealth,
        overall: { ...qaHealth.overall, status: 'unavailable' },
        suites: [],
        clusters: [],
        decision_checks: [],
        artifact_refs: [],
      },
    });

    const user = userEvent.setup();
    render(<QAHealthPage />);

    expect(screen.getByText('QA signal unavailable')).toBeInTheDocument();
    expect(screen.getByText('No failure clusters in the latest QA artifact.')).toBeInTheDocument();
    expect(screen.getByText('No suites were reported.')).toBeInTheDocument();
    expect(screen.queryByText(decisionCheck.label)).not.toBeInTheDocument();

    await user.click(screen.getByRole('tab', { name: 'Artifacts' }));
    expect(screen.getByText('No artifact references were included.')).toBeInTheDocument();
  });

  it('renders the error state and retries when the request fails', async () => {
    mockUser(true);
    const { refetch } = mockQAHealth({ data: undefined, error: new Error('request failed') });

    const user = userEvent.setup();
    render(<QAHealthPage />);

    expect(screen.getByText('QA health request failed')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent(
      'The sysadmin QA endpoint did not return a dashboard summary.',
    );
    expect(screen.queryByRole('heading', { name: 'QA Health' })).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Retry' }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
