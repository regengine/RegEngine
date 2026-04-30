import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import CurationDashboard from '@/app/ingest/curation/page';
import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';

vi.mock('@/lib/auth-context', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    getDiscoveryQueue: vi.fn(),
    approveDiscovery: vi.fn(),
    rejectDiscovery: vi.fn(),
    bulkApproveDiscovery: vi.fn(),
    bulkRejectDiscovery: vi.fn(),
  },
}));

vi.mock('@/components/ui/use-toast', () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  motion: {
    div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    tr: ({ children, ...props }: any) => <tr {...props}>{children}</tr>,
  },
}));

vi.mock('lucide-react', () => {
  const Icon = (props: any) => <svg aria-hidden="true" {...props} />;
  return {
    ShieldCheck: Icon,
    Search: Icon,
    Trash2: Icon,
    CheckCircle: Icon,
    AlertTriangle: Icon,
    Globe: Icon,
    ExternalLink: Icon,
    RefreshCw: Icon,
    Clock: Icon,
  };
});

describe('CurationDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('does not show the sign-in gate for an authenticated cookie-backed session without a readable API key', async () => {
    (useAuth as any).mockReturnValue({
      isAuthenticated: true,
      isHydrated: true,
      apiKey: null,
    });
    (apiClient.getDiscoveryQueue as any).mockResolvedValue([
      {
        body: 'FDA FSMA 204',
        url: 'https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods',
        index: 4,
      },
    ]);

    render(<CurationDashboard />);

    expect(screen.queryByText('Authentication Required')).not.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText('Manual Discovery Curation')).toBeInTheDocument();
      expect(screen.getByText('FDA FSMA 204')).toBeInTheDocument();
    });
    expect(apiClient.getDiscoveryQueue).toHaveBeenCalledTimes(1);
  });

  it('waits for auth hydration before fetching the discovery queue', () => {
    (useAuth as any).mockReturnValue({
      isAuthenticated: false,
      isHydrated: false,
      apiKey: null,
    });

    render(<CurationDashboard />);

    expect(screen.getByText('Loading session...')).toBeInTheDocument();
    expect(apiClient.getDiscoveryQueue).not.toHaveBeenCalled();
  });

  it('shows the sign-in gate only after hydration confirms the user is unauthenticated', () => {
    (useAuth as any).mockReturnValue({
      isAuthenticated: false,
      isHydrated: true,
      apiKey: null,
    });

    render(<CurationDashboard />);

    expect(screen.getByText('Authentication Required')).toBeInTheDocument();
    expect(apiClient.getDiscoveryQueue).not.toHaveBeenCalled();
  });
});
