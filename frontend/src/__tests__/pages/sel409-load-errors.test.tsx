import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import RecordsPage from '@/app/records/page';
import RulesPage from '@/app/rules/page';
import ExceptionsPage from '@/app/exceptions/page';
import RequestsPage from '@/app/requests/page';

const failed = { data: undefined, error: new Error('Load failed'), isLoading: false, refetch: vi.fn() };

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ tenantId: '11111111-1111-4111-8111-111111111111', user: { id: 'owner' } }),
}));
vi.mock('@/components/ui/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock('@/hooks/use-control-plane', () => ({
  useCanonicalEvents: () => failed,
  useCanonicalEvent: () => ({ data: undefined }),
  useRules: () => failed,
  useSeedRules: () => ({ isPending: false, mutate: vi.fn() }),
  useExceptions: () => failed,
  useBlockingExceptionCount: () => ({ data: { blocking_count: 0 }, error: null, refetch: vi.fn() }),
  useResolveException: () => ({ isPending: false, mutate: vi.fn() }),
  useWaiveException: () => ({ isPending: false, mutate: vi.fn() }),
  useAssignException: () => ({ isPending: false, mutate: vi.fn() }),
  useRequestCases: () => failed,
  useCreateRequestCase: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useApproveScope: () => ({ isPending: false, mutate: vi.fn() }),
  useCollectRecords: () => ({ isPending: false, mutate: vi.fn() }),
  useRunGapAnalysis: () => ({ isPending: false, mutate: vi.fn() }),
  useAssemblePackage: () => ({ isPending: false, mutate: vi.fn() }),
  useSubmitPackage: () => ({ isPending: false, mutate: vi.fn() }),
}));

describe('SEL-409 failed workspace loads', () => {
  it('hides the records count', () => {
    render(<RecordsPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('Load failed');
    expect(screen.queryByText(/total records/i)).not.toBeInTheDocument();
  });

  it('hides the rules count', () => {
    render(<RulesPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('Load failed');
    expect(screen.queryByText(/\d+ rules/i)).not.toBeInTheDocument();
  });

  it('hides No Blockers when exceptions fail', () => {
    render(<ExceptionsPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('Load failed');
    expect(screen.queryByText('No Blockers')).not.toBeInTheDocument();
  });

  it('shows only the request error state', () => {
    render(<RequestsPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('Load failed');
    expect(screen.queryByRole('button', { name: 'New Request Case' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Active Cases/)).not.toBeInTheDocument();
  });
});
