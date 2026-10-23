import { expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

import IngestPage from '@/app/ingest/page';

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ isAuthenticated: true, apiKey: null, setApiKey: vi.fn() }),
}));
vi.mock('@/hooks/use-api', () => ({
  useIngestURL: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false }),
  useIngestFile: () => ({ mutateAsync: vi.fn(), isPending: false, isError: false }),
  useIngestEpcisEvent: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useIngestEpcisBatch: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useIngestEpcisXml: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useValidateEpcisEvent: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
vi.mock('@/lib/api-client', () => ({ apiClient: { getIngestionJob: vi.fn() } }));
vi.mock('@/hooks/use-dashboard-refresh', () => ({ notifyDashboardRefresh: vi.fn() }));
vi.mock('@/app/ingest/NormalizedDocumentViewer', () => ({
  NormalizedDocumentViewer: () => null,
}));

it('does not prompt an authenticated user for an API key', () => {
  render(<IngestPage />);
  expect(screen.queryByText('API Key Required')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('API Key')).not.toBeInTheDocument();
});
