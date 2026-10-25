/**
 * Recall Report Page Tests
 *
 * Tests for the recall investigation / readiness report:
 * - Renders heading
 * - Shows the "No data yet" empty state for the backend PR #3536 no-data
 *   contract (status "no_data", score 0, grade "N/A", demo_mode false,
 *   demo_disclaimer null)
 * - Never renders fabricated data or a demo disclaimer
 * - Auth guard (skips fetch without credentials)
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import RecallReportPage from '@/app/dashboard/recall-report/page';

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

// ── No-data report matching the backend PR #3536 contract ──

const MOCK_NO_DATA_REPORT = {
  tenant_id: 'tenant-123',
  generated_at: new Date().toISOString(),
  overall_score: 0,
  overall_grade: 'N/A',
  overall_status: 'no_data',
  time_to_respond_estimate: '',
  dimensions: [],
  executive_summary: '',
  action_items: [],
  demo_mode: false,
  demo_disclaimer: null,
};

// ── Mocks ──

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() }),
  usePathname: () => '/dashboard/recall-report',
  useSearchParams: () => new URLSearchParams(),
}));

const mockUseAuth = vi.fn();
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => mockUseAuth(),
}));

const mockUseTenant = vi.fn();
vi.mock('@/lib/tenant-context', () => ({
  useTenant: () => mockUseTenant(),
}));

const mockFetchRecallReport = vi.fn();
vi.mock('@/lib/api-hooks', () => ({
  fetchRecallReport: (...args: any[]) => mockFetchRecallReport(...args),
}));

// Mock framer-motion
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    span: ({ children, ...props }: any) => <span {...props}>{children}</span>,
    circle: (props: any) => <circle {...props} />,
  },
  AnimatePresence: ({ children }: any) => <>{children}</>,
}));

// Mock Breadcrumbs
vi.mock('@/components/layout/breadcrumbs', () => ({
  Breadcrumbs: ({ items }: any) => (
    <nav aria-label="breadcrumb">
      {items.map((item: any, i: number) => (
        <span key={i}>{item.label}</span>
      ))}
    </nav>
  ),
}));

// Mock next/link
vi.mock('next/link', () => ({
  default: ({ children, href, ...props }: any) => <a href={href} {...props}>{children}</a>,
}));

vi.mock('lucide-react', () => {
  const stub = (props: any) => <svg {...props} />;
  return {
    Download: stub,
    Timer: stub,
    Database: stub,
    ShieldCheck: stub,
    Users: stub,
    Upload: stub,
    GraduationCap: stub,
    AlertTriangle: stub,
    ArrowUp: stub,
    ArrowRight: stub,
    Play: stub,
    Package: stub,
    MapPin: stub,
    Clock: stub,
    CheckCircle2: stub,
    XCircle: stub,
    ShoppingCart: stub,
    Zap: stub,
    Info: stub,
    ChevronDown: stub,
    ChevronUp: stub,
    RefreshCw: stub,
  };
});

// Mock api-config for dynamic import
vi.mock('@/lib/api-config', () => ({
  getServiceURL: () => '/api/ingestion',
}));

describe('RecallReportPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({ apiKey: null, isAuthenticated: true });
    mockUseTenant.mockReturnValue({ tenantId: 'tenant-123', isSystemTenant: false });
    // Default: API returns the no-data contract (status "no_data")
    mockFetchRecallReport.mockResolvedValue(MOCK_NO_DATA_REPORT);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('renders page heading', async () => {
    render(<RecallReportPage />, { wrapper: createWrapper() });
    expect(screen.getByRole('heading', { name: 'Recall Report' })).toBeInTheDocument();
  });

  it('fetches the recall report without a placeholder apiKey', async () => {
    render(<RecallReportPage />, { wrapper: createWrapper() });

    await waitFor(() => {
      expect(mockFetchRecallReport).toHaveBeenCalledWith('tenant-123');
    });
  });

  it('shows the "No data yet" empty state for the no-data contract', async () => {
    render(<RecallReportPage />, { wrapper: createWrapper() });
    // "No data yet" appears twice: the empty-state title and the grade
    // placeholder (backend grade "N/A" renders as the placeholder, not a badge).
    await waitFor(() => {
      expect(screen.getAllByText('No data yet').length).toBeGreaterThan(0);
    });
    expect(screen.queryByText('N/A')).not.toBeInTheDocument();
  });

  it('never renders a demo disclaimer', async () => {
    render(<RecallReportPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getAllByText('No data yet').length).toBeGreaterThan(0);
    });
    expect(screen.queryByText(/demo/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/sample scenario/i)).not.toBeInTheDocument();
  });

  it('renders no readiness dimensions or action items when the report has none', async () => {
    render(<RecallReportPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getAllByText('No data yet').length).toBeGreaterThan(0);
    });
    expect(screen.queryByText('Trace Speed')).not.toBeInTheDocument();
    expect(screen.queryByText('Data Completeness')).not.toBeInTheDocument();
    expect(screen.queryByText('Chain Integrity')).not.toBeInTheDocument();
    expect(screen.queryByText('Supplier Coverage')).not.toBeInTheDocument();
    expect(screen.queryByText('Prioritized Actions')).not.toBeInTheDocument();
  });

  it('shows the empty state with a next-step link', async () => {
    render(<RecallReportPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getAllByText('No data yet').length).toBeGreaterThan(0);
    });
    expect(screen.getByRole('link', { name: /import records/i })).toHaveAttribute('href', '/tools/data-import');
  });

  it('shows an error without fabricated results when the API fails', async () => {
    mockFetchRecallReport.mockRejectedValue(new Error('API unavailable'));
    render(<RecallReportPage />, { wrapper: createWrapper() });
    await waitFor(() => {
      expect(screen.getByText('Recall report unavailable')).toBeInTheDocument();
    });
    expect(screen.queryByText('No data yet')).not.toBeInTheDocument();
  });

  it('does not fetch when credentials are missing', () => {
    mockUseAuth.mockReturnValue({ apiKey: null, isAuthenticated: false });
    mockUseTenant.mockReturnValue({ tenantId: null, isSystemTenant: true });
    render(<RecallReportPage />, { wrapper: createWrapper() });
    expect(mockFetchRecallReport).not.toHaveBeenCalled();
  });

  it('exports the FDA response through the cookie-backed ingestion proxy without browser auth headers', async () => {
    const fetchSpy = vi.fn().mockResolvedValue({
      ok: true,
      blob: async () => new Blob(['csv']),
    });
    vi.stubGlobal('fetch', fetchSpy);

    const createObjectURL = vi.fn(() => 'blob:recall-export');
    const revokeObjectURL = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const anchor = originalCreateElement('a');
    const click = vi.fn();
    anchor.click = click;
    vi.spyOn(document, 'createElement').mockImplementation(((tagName: string, options?: ElementCreationOptions) => {
      if (tagName.toLowerCase() === 'a') {
        return anchor;
      }
      return originalCreateElement(tagName, options);
    }) as typeof document.createElement);
    vi.spyOn(document.body, 'appendChild');
    vi.stubGlobal('URL', {
      ...window.URL,
      createObjectURL,
      revokeObjectURL,
    });

    const user = userEvent.setup();
    render(<RecallReportPage />, { wrapper: createWrapper() });

    const exportButton = await screen.findByRole('button', { name: /generate fda 24-hour response/i });
    await user.click(exportButton);

    await waitFor(() => {
      expect(fetchSpy).toHaveBeenCalledWith(
        '/api/ingestion/api/v1/fda/export/all?tenant_id=tenant-123&format=csv',
        expect.objectContaining({ credentials: 'include' }),
      );
    });

    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get('X-RegEngine-API-Key')).toBeNull();
    expect(click).toHaveBeenCalled();
    expect(createObjectURL).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalled();
  });
});
