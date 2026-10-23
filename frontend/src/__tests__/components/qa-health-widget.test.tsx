import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

import { QAHealthWidget } from '@/components/dashboard/qa-health-widget';
import { useAuth } from '@/lib/auth-context';
import { useQAHealth } from '@/hooks/use-api';
import type { QAHealthResponse } from '@/types/api';

vi.mock('@/lib/auth-context', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/hooks/use-api', () => ({
  useQAHealth: vi.fn(),
}));

const qaHealth: QAHealthResponse = {
  schema_version: '1.0',
  generated_at: '2026-06-04T00:00:00Z',
  source: { kind: 'ci_artifact', path: 'qa/qa-health/latest.json' },
  overall: {
    status: 'unavailable',
    ready_percent: 0,
    blocking_count: 0,
    advisory_count: 0,
  },
  suites: [],
  clusters: [],
  decision_checks: [],
  artifact_refs: [],
};

describe('QAHealthWidget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(useQAHealth).mockReturnValue({
      data: qaHealth,
      isLoading: false,
      error: null,
    } as ReturnType<typeof useQAHealth>);
  });

  it('does not render for non-sysadmin users', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '', email: '', is_sysadmin: false, status: 'active' },
    } as ReturnType<typeof useAuth>);

    const { container } = render(<QAHealthWidget />);

    expect(container).toBeEmptyDOMElement();
    expect(useQAHealth).toHaveBeenCalledWith(false);
  });

  it('renders release health for sysadmin users', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '', email: '', is_sysadmin: true, status: 'active' },
    } as ReturnType<typeof useAuth>);

    render(<QAHealthWidget />);

    expect(screen.getByText('QA Health')).toBeInTheDocument();
    expect(screen.getByText('QA signal unavailable')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open qa health/i })).toHaveAttribute(
      'href',
      '/dashboard/qa-health',
    );
    expect(useQAHealth).toHaveBeenCalledWith(true);
  });

  it('a failed QA load reads as failed with unknown readiness — not "0% ready"', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: '', email: '', is_sysadmin: true, status: 'active' },
    } as ReturnType<typeof useAuth>);
    vi.mocked(useQAHealth).mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('timeout'),
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useQAHealth>);

    render(<QAHealthWidget />);

    expect(screen.getByText('QA signal failed')).toBeInTheDocument();
    expect(screen.getByText('Readiness unknown')).toBeInTheDocument();
    expect(screen.queryByText(/0% ready/)).not.toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument();
  });
});
