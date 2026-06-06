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

const qaHealth: QAHealthResponse = {
  schema_version: '1.0',
  generated_at: '2026-06-04T00:00:00Z',
  source: {
    kind: 'ci_artifact',
    path: 'qa/qa-health/latest.json',
    workflow: 'QA Health',
    branch: 'main',
  },
  overall: {
    status: 'failing',
    ready_percent: 28,
    blocking_count: 3,
    advisory_count: 1,
  },
  suites: [
    {
      id: 'backend-pytest',
      label: 'Backend pytest',
      command: 'python3 -m pytest --no-cov',
      status: 'failed',
      passed: 8379,
      failed: 240,
      skipped: 319,
      errors: 23,
      duration_seconds: 372.98,
      blocking: true,
    },
    {
      id: 'frontend-vitest',
      label: 'Frontend Vitest',
      command: 'npm run test:run',
      status: 'passed',
      passed: 618,
      failed: 0,
      skipped: 4,
      errors: 0,
      duration_seconds: null,
      blocking: true,
    },
    {
      id: 'frontend-e2e',
      label: 'Playwright E2E',
      command: 'npm run test:e2e',
      status: 'failed',
      passed: 13,
      failed: 55,
      skipped: 2,
      errors: 0,
      duration_seconds: 2694,
      blocking: true,
    },
    {
      id: 'frontend-install',
      label: 'Install drift',
      command: 'npm ci',
      status: 'failed',
      passed: 0,
      failed: 1,
      skipped: 0,
      errors: 0,
      duration_seconds: null,
      blocking: true,
    },
  ],
  clusters: [
    {
      title: 'Login tests stuck in email-code mode',
      severity: 'critical',
      affected_suites: ['frontend-e2e'],
      owner_lane: 'frontend',
      impact: 'Authenticated browser journeys fail before dashboard assertions.',
      next_action: 'Align Playwright login setup with password mode.',
    },
  ],
  decision_checks: [
    {
      label: 'Blocking: backend unit failures',
      status: 'blocking',
      detail: '240 failures and 23 errors',
    },
    {
      label: 'Passed: Vitest',
      status: 'passed',
      detail: '618 tests passed',
    },
  ],
  artifact_refs: [
    {
      id: 'playwright-results',
      label: 'Playwright failure artifacts',
      path: 'frontend/test-results',
      type: 'directory',
    },
  ],
};

describe('QAHealthPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useQAHealth).mockReturnValue({
      data: qaHealth,
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      isRefetching: false,
    } as unknown as ReturnType<typeof useQAHealth>);
  });

  it('renders sysadmin QA health details', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 'u1', email: 'admin@example.com', is_sysadmin: true, status: 'active' },
      isHydrated: true,
    } as ReturnType<typeof useAuth>);

    const user = userEvent.setup();
    render(<QAHealthPage />);

    expect(screen.getByRole('heading', { name: 'QA Health' })).toBeInTheDocument();
    expect(screen.getByText('Release gate failing')).toBeInTheDocument();
    expect(screen.getAllByText('Backend pytest').length).toBeGreaterThan(0);
    expect(screen.getByText('Login tests stuck in email-code mode')).toBeInTheDocument();
    expect(screen.getByText('Blocking: backend unit failures')).toBeInTheDocument();
    await user.click(screen.getByRole('tab', { name: 'Artifacts' }));
    expect(screen.getByText('frontend/test-results')).toBeInTheDocument();
    expect(useQAHealth).toHaveBeenCalledWith(true);
  });

  it('blocks non-sysadmin users before fetching QA health', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 'u1', email: 'user@example.com', is_sysadmin: false, status: 'active' },
      isHydrated: true,
    } as ReturnType<typeof useAuth>);

    render(<QAHealthPage />);

    expect(screen.getByText('Sysadmin access required')).toBeInTheDocument();
    expect(useQAHealth).toHaveBeenCalledWith(false);
  });

  it('renders missing artifact state from the endpoint summary', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 'u1', email: 'admin@example.com', is_sysadmin: true, status: 'active' },
      isHydrated: true,
    } as ReturnType<typeof useAuth>);
    vi.mocked(useQAHealth).mockReturnValue({
      data: {
        ...qaHealth,
        overall: {
          status: 'unavailable',
          ready_percent: 0,
          blocking_count: 0,
          advisory_count: 0,
        },
        suites: [],
        clusters: [],
        artifact_refs: [],
      },
      isLoading: false,
      error: null,
      refetch: vi.fn(),
      isRefetching: false,
    } as unknown as ReturnType<typeof useQAHealth>);

    render(<QAHealthPage />);

    expect(screen.getByText('QA signal unavailable')).toBeInTheDocument();
    expect(screen.getByText('No failure clusters in the latest QA artifact.')).toBeInTheDocument();
  });
});
