import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import AnalysisResultClient from '@/app/ingest/results/[id]/AnalysisResultClient';

const mocks = vi.hoisted(() => ({ id: 'document-A', analysis: vi.fn() }));
vi.mock('next/navigation', () => ({ useParams: () => ({ id: mocks.id }) }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ apiKey: 'test-session', tenantId: 'tenant-A', user: { id: 'operator' } }) }));
vi.mock('@/lib/api-client', () => ({ apiClient: { getDocumentAnalysis: mocks.analysis } }));
function fixture(id: string) { return { document_id: id, risk_score: 0, critical_risks: [] }; }
function wrapper({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>{children}</QueryClientProvider>;
}
describe('Document analysis recovery', () => {
  beforeEach(() => { mocks.id = 'document-A'; mocks.analysis.mockReset(); });
  it('shows API failure as unavailable and allows retry', async () => {
    mocks.analysis.mockRejectedValueOnce(new Error('503 Analysis unavailable')).mockResolvedValueOnce(fixture('document-A'));
    render(<AnalysisResultClient />, { wrapper });
    expect(await screen.findByText('503 Analysis unavailable')).toBeInTheDocument();
    expect(screen.queryByText('Document Not Found')).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry analysis' }));
    expect(await screen.findByText('document-A')).toBeInTheDocument();
  });
  it('does not display a previous document when its deferred request finishes late', async () => {
    let finish!: (value: ReturnType<typeof fixture>) => void;
    mocks.analysis.mockImplementationOnce(() => new Promise(resolve => { finish = resolve; })).mockResolvedValueOnce(fixture('document-B'));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const view = (id: string) => { mocks.id = id; return <QueryClientProvider client={client}><AnalysisResultClient /></QueryClientProvider>; };
    const { rerender } = render(view('document-A'));
    rerender(view('document-B'));
    expect(await screen.findByText('document-B')).toBeInTheDocument();
    await act(async () => finish(fixture('document-A')));
    expect(screen.queryByText('document-A')).not.toBeInTheDocument();
    expect(screen.getByText('document-B')).toBeInTheDocument();
  });
});
