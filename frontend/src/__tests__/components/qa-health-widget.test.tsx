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
    status: 'failing',
    ready_percent: 28,
    blocking_count: 3,
    advisory_count: 1,
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
      user: { id: 'u1', email: 'user@example.com', is_sysadmin: false, status: 'active' },
    } as ReturnType<typeof useAuth>);

    const { container } = render(<QAHealthWidget />);

    expect(container).toBeEmptyDOMElement();
    expect(useQAHealth).toHaveBeenCalledWith(false);
  });

  it('renders release health for sysadmin users', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: { id: 'u1', email: 'admin@example.com', is_sysadmin: true, status: 'active' },
    } as ReturnType<typeof useAuth>);

    render(<QAHealthWidget />);

    expect(screen.getByText('QA Health')).toBeInTheDocument();
    expect(screen.getByText('Release gate failing')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /open qa health/i })).toHaveAttribute(
      'href',
      '/dashboard/qa-health',
    );
    expect(useQAHealth).toHaveBeenCalledWith(true);
  });
});
