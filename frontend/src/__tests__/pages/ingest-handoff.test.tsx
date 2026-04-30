import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import IngestPage from '@/app/ingest/page';
import { useAuth } from '@/lib/auth-context';
import { useSearchParams } from 'next/navigation';

vi.mock('next/navigation', () => ({
  useRouter: vi.fn(() => ({ push: vi.fn(), replace: vi.fn(), prefetch: vi.fn(), back: vi.fn() })),
  usePathname: vi.fn(() => '/ingest'),
  useSearchParams: vi.fn(),
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: vi.fn(),
}));

vi.mock('@/hooks/use-api', () => ({
  useIngestURL: vi.fn(() => ({
    isPending: false,
    isSuccess: false,
    isError: false,
    mutateAsync: vi.fn(),
    reset: vi.fn(),
  })),
  useIngestFile: vi.fn(() => ({
    isPending: false,
    isSuccess: false,
    isError: false,
    mutateAsync: vi.fn(),
    reset: vi.fn(),
  })),
}));

vi.mock('@/hooks/use-dashboard-refresh', () => ({
  notifyDashboardRefresh: vi.fn(),
}));

vi.mock('@/app/ingest/NormalizedDocumentViewer', () => ({
  NormalizedDocumentViewer: ({ documentId }: { documentId: string }) => <div>Normalized {documentId}</div>,
}));

describe('Ingest sandbox handoff consumer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.sessionStorage.clear();
    (useAuth as any).mockReturnValue({
      apiKey: 'rge_test_key',
      setApiKey: vi.fn(),
    });
    (useSearchParams as any).mockReturnValue(new URLSearchParams('from=sandbox-handoff'));
  });

  it('recognizes a saved sandbox test-run handoff and shows the mapping preview contract', () => {
    window.sessionStorage.setItem(
      'regengine:sandbox-handoff',
      JSON.stringify({
        version: 1,
        source: 'free-sandbox',
        createdAt: '2026-04-30T12:00:00.000Z',
        summary: {
          totalEvents: 3,
          passedChecks: 2,
          needsWork: 1,
          blockers: 0,
        },
        csv: 'cte_type,traceability_lot_code,product_description\nshipping,LOT-1,Romaine',
        detectedColumns: ['cte_type', 'traceability_lot_code', 'product_description'],
        diagnosis: { status: 'needs_work' },
        corrections: { missingKdes: ['reference_document'] },
      }),
    );

    render(<IngestPage />);

    expect(screen.getByText(/Sandbox import mapping handoff/i)).toBeInTheDocument();
    expect(screen.getByText(/saved test-run diagnosis/i)).toBeInTheDocument();
    expect(screen.getByText(/before any authenticated feed or evidence workflow uses the data/i)).toBeInTheDocument();
    expect(screen.getByText('Events detected')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText(/cte_type/i)).toBeInTheDocument();
    expect(screen.getByText(/traceability_lot_code/i)).toBeInTheDocument();
    expect(screen.getByText(/Review suggested corrections/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Continue File Mapping/i })).toBeInTheDocument();
  });
});
