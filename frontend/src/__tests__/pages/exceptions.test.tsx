/**
 * Exception Queue Page Tests
 *
 * Tests for the exception queue view:
 * - Exception list rendering
 * - Severity and status badges
 * - Resolve / waive actions
 * - Blocking count display
 * - Demo banner flag
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ExceptionQueuePage from '@/app/exceptions/page';

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
    tenantId: 'tenant-123',
    user: { id: 'user-1', email: 'qa@example.com' },
  }),
}));

// Mock control-plane hooks
const mockResolveMutate = vi.fn();
const mockWaiveMutate = vi.fn();
const mockUseExceptions = vi.fn();
const mockUseBlockingExceptionCount = vi.fn();

vi.mock('@/hooks/use-control-plane', () => ({
  useExceptions: (...args: any[]) => mockUseExceptions(...args),
  useBlockingExceptionCount: (...args: any[]) => mockUseBlockingExceptionCount(...args),
  useResolveException: () => ({ mutateAsync: mockResolveMutate, isPending: false }),
  useWaiveException: () => ({ mutateAsync: mockWaiveMutate, isPending: false }),
  useAssignException: () => ({ mutate: vi.fn(), isPending: false }),
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
vi.mock('lucide-react', async (importOriginal) => {
  // The design-system primitives (Callout, StatTile, DataTable, StatusBadge)
  // read their icons at module scope, so a partial mock throws on import.
  // Spread the real module and keep stubbing the icons this suite names.
  const actual = await importOriginal<typeof import('lucide-react')>();
  const stub = (props: any) => <svg {...props} />;
  return {
    ...actual,
    AlertTriangle: stub,
    CheckCircle: stub,
    Clock: stub,
    Filter: stub,
    Shield: stub,
    User: stub,
    XCircle: stub,
  };
});

const SAMPLE_CASES = [
  {
    case_id: 'exc-1',
    severity: 'critical',
    status: 'open',
    rule_category: 'kde_presence',
    source_supplier: 'Acme Foods',
    owner_user_id: null,
    due_date: '2026-04-01',
    recommended_remediation: 'Add missing KDE',
  },
  {
    case_id: 'exc-2',
    severity: 'warning',
    status: 'in_review',
    rule_category: 'lot_linkage',
    source_supplier: 'Beta Corp',
    owner_user_id: 'user-42',
    due_date: null,
    recommended_remediation: null,
  },
  {
    case_id: 'exc-3',
    severity: 'info',
    status: 'resolved',
    rule_category: 'record_completeness',
    source_supplier: null,
    owner_user_id: null,
    due_date: null,
    recommended_remediation: null,
  },
];

describe('ExceptionQueuePage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseBlockingExceptionCount.mockReturnValue({
      data: { blocking_count: 2 },
      isLoading: false,
    });
  });

  function setupExceptions(overrides: any = {}) {
    mockUseExceptions.mockReturnValue({
      data: { cases: SAMPLE_CASES, __isDemo: false },
      isLoading: false,
      ...overrides,
    });
  }

  it('renders exception list with supplier names', () => {
    setupExceptions();
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });

    expect(screen.getByText('Acme Foods')).toBeInTheDocument();
    expect(screen.getByText('Beta Corp')).toBeInTheDocument();
  });

  it('shows severity badges in the table', () => {
    setupExceptions();
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });

    // Severity labels appear in both filter dropdowns and table badges
    const table = screen.getByRole('table');
    expect(table).toHaveTextContent('Critical');
    expect(table).toHaveTextContent('Warning');
    expect(table).toHaveTextContent('Info');
  });

  it('shows status badges in the table', () => {
    setupExceptions();
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });

    // Status labels appear in stat cards, filter dropdowns, AND table
    const table = screen.getByRole('table');
    expect(table).toHaveTextContent('Open');
    expect(table).toHaveTextContent('In Review');
    expect(table).toHaveTextContent('Resolved');
  });

  it('calls resolve mutation when Resolve button is clicked', async () => {
    setupExceptions();
    const user = userEvent.setup();
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });

    const resolveButtons = screen.getAllByRole('button', { name: /resolve/i });
    await user.click(resolveButtons[0]);

    expect(mockResolveMutate).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('Case-specific reason'), 'Verified corrected KDE against supplier evidence');
    await user.click(screen.getByRole('button', { name: 'Confirm resolve' }));
    expect(mockResolveMutate).toHaveBeenCalledWith({
      caseId: 'exc-1',
      resolutionSummary: 'Verified corrected KDE against supplier evidence',
      resolvedBy: 'qa@example.com',
    });
  });

  it('calls waive mutation when Waive button is clicked', async () => {
    setupExceptions();
    const user = userEvent.setup();
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });

    const waiveButtons = screen.getAllByRole('button', { name: /waive/i });
    await user.click(waiveButtons[0]);

    expect(mockWaiveMutate).not.toHaveBeenCalled();
    await user.type(screen.getByLabelText('Case-specific reason'), 'Approved documented exception for supplier Acme');
    await user.click(screen.getByRole('button', { name: 'Confirm waive' }));
    expect(mockWaiveMutate).toHaveBeenCalledWith({
      caseId: 'exc-1',
      waiverReason: 'Approved documented exception for supplier Acme',
      waiverApprovedBy: 'qa@example.com',
    });
  });

  it.each(['403 Permission denied', '409 Case changed; refresh', '500 Database unavailable'])('preserves the reason when sign-off fails: %s', async (message) => {
    setupExceptions();
    mockResolveMutate.mockRejectedValueOnce(new Error(message));
    const user = userEvent.setup();
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });
    await user.click(screen.getAllByRole('button', { name: 'Resolve' })[0]);
    await user.type(screen.getByLabelText('Case-specific reason'), 'Supplier evidence reviewed');
    await user.click(screen.getByRole('button', { name: 'Confirm resolve' }));
    expect(await screen.findByText(message)).toBeInTheDocument();
    expect(screen.getByLabelText('Case-specific reason')).toHaveValue('Supplier evidence reviewed');
  });

  it('prevents competing actions while the sign-off is pending', async () => {
    setupExceptions();
    let finish!: () => void;
    mockResolveMutate.mockImplementationOnce(() => new Promise<void>(resolve => { finish = resolve; }));
    const user = userEvent.setup();
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });
    await user.click(screen.getAllByRole('button', { name: 'Resolve' })[0]);
    expect(screen.getByRole('button', { name: 'Confirm resolve' })).toBeDisabled();
    await user.type(screen.getByLabelText('Case-specific reason'), 'Corrected KDE evidence');
    await user.click(screen.getByRole('button', { name: 'Confirm resolve' }));
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled();
    expect(screen.getByLabelText('Case-specific reason')).toBeDisabled();
    finish();
  });

  it('displays blocking count badge' , () => {
    setupExceptions();
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });

    expect(screen.getByText(/2 Blocking/)).toBeInTheDocument();
  });

  it('shows "No Blockers" when blocking count is zero', () => {
    setupExceptions();
    mockUseBlockingExceptionCount.mockReturnValue({
      data: { blocking_count: 0 },
      isLoading: false,
    });
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });

    expect(screen.getByText('No Blockers')).toBeInTheDocument();
  });

  it('never declares unknown blockers clear', () => {
    setupExceptions();
    mockUseBlockingExceptionCount.mockReturnValue({ error: new Error('Unavailable') });
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });
    expect(screen.queryByText('No Blockers')).not.toBeInTheDocument();
    expect(screen.getByText('Blockers unavailable')).toBeInTheDocument();
  });

  it('renders page heading and description', () => {
    setupExceptions();
    render(<ExceptionQueuePage />, { wrapper: createWrapper() });

    expect(screen.getByText('Exception Queue')).toBeInTheDocument();
    expect(screen.getByText(/compliance exceptions/i)).toBeInTheDocument();
  });
});
