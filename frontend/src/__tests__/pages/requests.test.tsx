/**
 * Request-Response Workflow Page Tests
 *
 * Tests for the request workflow view:
 * - Active and completed case rendering
 * - Create form interaction
 * - Progress bar / status display
 * - Demo banner flag
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RequestWorkflowPage from '@/app/requests/page';

function createWrapper() {
    const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
    });
    return ({ children }: { children: React.ReactNode }) => (
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
}

// Mock auth context
vi.mock('@/lib/auth-context', () => ({
  useAuth: vi.fn().mockReturnValue({
    apiKey: 'test-api-key',
    tenantId: 'tenant-123',
  }),
}));

// Mock control-plane hooks
const mockCreateMutateAsync = vi.fn().mockResolvedValue({});
const mockAssembleMutate = vi.fn();
const mockSubmitMutate = vi.fn();
const mockUseRequestCases = vi.fn();

vi.mock('@/hooks/use-control-plane', () => ({
  useRequestCases: (...args: any[]) => mockUseRequestCases(...args),
  useCreateRequestCase: () => ({ mutateAsync: mockCreateMutateAsync, isPending: false }),
  useAssemblePackage: () => ({ mutate: mockAssembleMutate, isPending: false }),
  useSubmitPackage: () => ({ mutate: mockSubmitMutate, isPending: false }),
}));

// Mock framer-motion
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// Mock lucide-react icons
vi.mock('lucide-react', () => {
  const stub = (props: any) => <svg {...props} />;
  return {
    AlertTriangle: stub,
    CheckCircle: stub,
    Clock: stub,
    FileText: stub,
    Package: stub,
    PlayCircle: stub,
    Send: stub,
    Timer: stub,
  };
});

const ACTIVE_CASE = {
  request_case_id: 'rc-1',
  requesting_party: 'FDA',
  scope_type: 'tlc_trace',
  package_status: 'collecting',
  affected_lots: ['TLC-001', 'TLC-002'],
  total_records: 42,
  gap_count: 3,
  active_exception_count: 1,
  is_overdue: false,
  hours_remaining: 18.5,
  countdown_display: '18.5h remaining',
  request_received_at: '2026-03-25T10:00:00Z',
};

const READY_CASE = {
  request_case_id: 'rc-2',
  requesting_party: 'State DOH',
  scope_type: 'product_trace',
  package_status: 'ready',
  affected_lots: ['LOT-A'],
  total_records: 100,
  gap_count: 0,
  active_exception_count: 0,
  is_overdue: false,
  hours_remaining: 2,
  countdown_display: '2.0h remaining',
  request_received_at: '2026-03-25T12:00:00Z',
};

const COMPLETED_CASE = {
  request_case_id: 'rc-3',
  requesting_party: 'Internal Drill',
  scope_type: 'tlc_trace',
  package_status: 'submitted',
  affected_lots: ['TLC-005'],
  total_records: 200,
  gap_count: 0,
  active_exception_count: 0,
  is_overdue: false,
  hours_remaining: 0,
  countdown_display: null,
  request_received_at: '2026-03-20T08:00:00Z',
};

describe('RequestWorkflowPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  function setupCases(cases: any[] = [ACTIVE_CASE, READY_CASE, COMPLETED_CASE], overrides: any = {}) {
    mockUseRequestCases.mockReturnValue({
      data: { cases, __isDemo: false },
      isLoading: false,
      ...overrides,
    });
  }

  it('renders active cases section with case details', () => {
    setupCases();
    render(<RequestWorkflowPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/Active Cases/)).toBeInTheDocument();
    expect(screen.getByText('FDA')).toBeInTheDocument();
    expect(screen.getByText('18.5h remaining')).toBeInTheDocument();
  });

  it('renders completed cases section', () => {
    setupCases();
    render(<RequestWorkflowPage />, { wrapper: createWrapper() });

    expect(screen.getByText(/Completed/)).toBeInTheDocument();
    expect(screen.getByText('Submitted')).toBeInTheDocument();
    expect(screen.getByText('Internal Drill')).toBeInTheDocument();
  });

  it('shows status badge and progress info for active case', () => {
    setupCases();
    render(<RequestWorkflowPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Collecting')).toBeInTheDocument();
    expect(screen.getByText('42 records collected')).toBeInTheDocument();
    expect(screen.getByText('3 gaps / 1 exceptions')).toBeInTheDocument();
  });

  it('shows lot badges for active case', () => {
    setupCases();
    render(<RequestWorkflowPage />, { wrapper: createWrapper() });

    expect(screen.getByText('TLC-001')).toBeInTheDocument();
    expect(screen.getByText('TLC-002')).toBeInTheDocument();
  });

  it('opens create form and submits a new case', async () => {
    setupCases();
    const user = userEvent.setup();
    render(<RequestWorkflowPage />, { wrapper: createWrapper() });

    // Click "New Request Case" button
    const newButton = screen.getByRole('button', { name: /new request case/i });
    await user.click(newButton);

    // Form should appear
    expect(screen.getByText('Open New Request Case')).toBeInTheDocument();

    // Fill in lot codes
    const lotInput = screen.getByPlaceholderText(/TLC-001/);
    await user.type(lotInput, 'LOT-X, LOT-Y');

    // Submit
    const createButton = screen.getByRole('button', { name: /create case/i });
    await user.click(createButton);

    expect(mockCreateMutateAsync).toHaveBeenCalledWith({
      requesting_party: 'FDA',
      scope_type: 'tlc_trace',
      affected_lots: ['LOT-X', 'LOT-Y'],
      response_hours: 24,
    });
  });

  it('shows Submit button for ready cases and Assemble for non-ready', () => {
    setupCases();
    render(<RequestWorkflowPage />, { wrapper: createWrapper() });

    // Submit button for the ready case
    const submitButtons = screen.getAllByRole('button', { name: /submit/i });
    expect(submitButtons.length).toBeGreaterThanOrEqual(1);

    // Assemble button for the collecting case
    const assembleButtons = screen.getAllByRole('button', { name: /assemble/i });
    expect(assembleButtons.length).toBeGreaterThanOrEqual(1);
  });

  it('shows loading skeletons while loading', () => {
    setupCases([], { isLoading: true, data: undefined });
    render(<RequestWorkflowPage />, { wrapper: createWrapper() });

    expect(screen.getByText('Request-Response Workflow')).toBeInTheDocument();
    expect(screen.queryByText('FDA')).not.toBeInTheDocument();
  });

  it('shows empty state when no active cases', () => {
    setupCases([COMPLETED_CASE]);
    render(<RequestWorkflowPage />, { wrapper: createWrapper() });

    expect(screen.getByText('No active request cases')).toBeInTheDocument();
  });
});
