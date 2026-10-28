import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';

import RecordsPage from '@/app/records/page';
import RulesPage from '@/app/rules/page';
import ExceptionsPage from '@/app/exceptions/page';
import RequestsPage from '@/app/requests/page';

const state = vi.hoisted(() => ({ exceptionsLoaded: false }));
const failed = { data: undefined, error: new Error('Load failed'), isLoading: false, refetch: vi.fn() };
const retryCount = vi.fn();

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ tenantId: '', user: null }),
}));
vi.mock('@/components/ui/use-toast', () => ({ useToast: () => ({ toast: vi.fn() }) }));
vi.mock('@/hooks/use-control-plane', () => ({
  useCanonicalEvents: () => failed,
  useCanonicalEvent: () => ({ data: undefined }),
  useRules: () => failed,
  useSeedRules: () => ({ isPending: false, mutate: vi.fn() }),
  useExceptions: () => state.exceptionsLoaded
    ? { data: { cases: [] }, error: null, isLoading: false, refetch: vi.fn() }
    : failed,
  useBlockingExceptionCount: () => ({ data: undefined, error: new Error('Count unavailable'), refetch: retryCount }),
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
  it('hides the records count behind the records error state', () => {
    failed.refetch.mockClear();
    render(<RecordsPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('We could not load your records.');
    expect(screen.queryByText(/total records/i)).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Contact support' })).toHaveAttribute('href', '/settings/support');
    expect(screen.queryByText(/Request ID:/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(failed.refetch).toHaveBeenCalledOnce();
  });

  it('hides the rules count', () => {
    render(<RulesPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('Load failed');
    expect(screen.queryByText(/\d+ rules/i)).not.toBeInTheDocument();
  });

  it('hides No Blockers when exceptions fail', () => {
    state.exceptionsLoaded = false;
    render(<ExceptionsPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('Load failed');
    expect(screen.queryByText('No Blockers')).not.toBeInTheDocument();
  });

  it('keeps the empty exception table when only the count fails', () => {
    state.exceptionsLoaded = true;
    render(<ExceptionsPage />);
    expect(screen.getByText('No exceptions found')).toBeInTheDocument();
    expect(screen.queryByText('No Blockers')).not.toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('Count unavailable');
    fireEvent.click(screen.getByRole('button', { name: 'Retry count' }));
    expect(retryCount).toHaveBeenCalled();
    state.exceptionsLoaded = false;
  });

  it('shows only the request error state', () => {
    render(<RequestsPage />);
    expect(screen.getByRole('alert')).toHaveTextContent('Load failed');
    expect(screen.queryByRole('button', { name: 'New Request Case' })).not.toBeInTheDocument();
    expect(screen.queryByText(/Active Cases/)).not.toBeInTheDocument();
  });
});
