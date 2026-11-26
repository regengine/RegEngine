/**
 * Tests for SEL-641, SEL-642, SEL-645, SEL-647 (Medium/Low priority UX fixes)
 * 
 * These tests explicitly verify each new string and link introduced by the SEL tickets
 * to ensure mutations don't silently revert user-facing copy changes.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { readFileSync } from 'fs';
import { join } from 'path';
import BulkUploadPage from '@/app/onboarding/bulk-upload/page';
import TracePage from '@/app/trace/page';

// Mock dependencies
vi.mock('next/navigation', () => ({
  useSearchParams: () => ({
    get: () => null,
  }),
  useRouter: () => ({
    push: vi.fn(),
  }),
  usePathname: () => '/integrations',
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    hasTenantSession: true,
    activeAccountId: 'test-account',
    userEmail: 'test@example.com',
    isAuthenticated: true,
  }),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    parseSupplierBulkUpload: vi.fn(),
    validateSupplierBulkUpload: vi.fn(),
    commitSupplierBulkUpload: vi.fn(),
    getSupplierBulkUploadStatus: vi.fn(),
    downloadSupplierBulkUploadTemplate: vi.fn(),
    getSupplierFDAExportPreview: vi.fn(),
    downloadSupplierFDARecords: vi.fn(),
    listSupplierFDAExportJobs: vi.fn().mockResolvedValue({ jobs: [], pagination: { page: 1, page_size: 20, total_count: 0, total_pages: 0 } }),
    getIntegrations: vi.fn().mockResolvedValue({ integrations: [] }),
  },
}));

vi.mock('@/hooks/use-dashboard-refresh', () => ({
  notifyDashboardRefresh: vi.fn(),
}));

vi.mock('@/components/dashboard/metrics-overview-widget', () => ({
  MetricsOverviewWidget: () => null,
}));

describe('SEL-641: File picker restricted to CSV only', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('file input accept attribute restricted to CSV only', () => {
    render(<BulkUploadPage />);
    
    // SEL-641: File input should only accept CSV (was .csv,.xlsx,.json,.pdf)
    const fileInput = screen.getByLabelText(/upload your file/i);
    expect(fileInput).toHaveAttribute('accept', '.csv');
  });
});

describe('SEL-642: Jargon replacements', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows "Check my file" button instead of old validation button text', () => {
    render(<BulkUploadPage />);
    
    // SEL-642: Button text changed from technical jargon to plain language
    expect(screen.getByRole('button', { name: /check my file/i })).toBeInTheDocument();
  });

  it('shows "Save records" button instead of old commit button text', () => {
    render(<BulkUploadPage />);
    
    // SEL-642: Commit button renamed to plain language
    expect(screen.getByRole('button', { name: /save records/i })).toBeInTheDocument();
  });

  it('removed "TLC" jargon from trace page description', () => {
    render(<TracePage />);
    
    // SEL-642: "Traceability Lot Code (TLC)" removed from user-facing text
    const description = screen.getByText(/enter a lot code to see every step/i);
    expect(description).toBeInTheDocument();
    expect(description.textContent).not.toContain('TLC');
  });
});

describe('SEL-645: Trace page simplifications', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows simplified page title "Trace a lot"', () => {
    render(<TracePage />);
    
    // SEL-645: Simplified from longer technical title
    expect(screen.getByText('Trace a lot')).toBeInTheDocument();
  });

  it('shows simplified description without jargon', () => {
    render(<TracePage />);
    
    // SEL-645: Plain language description
    expect(screen.getByText(/enter a lot code to see every step it went through/i)).toBeInTheDocument();
  });

  it('shows simplified placeholder text in lot code input', () => {
    render(<TracePage />);
    
    // SEL-645: Simple placeholder instead of technical instructions
    const input = screen.getByRole('textbox', { name: /trace lot/i });
    expect(input).toHaveAttribute('placeholder', 'Enter a lot code from your records');
  });
});

describe('SEL-647: CSV/JSON link updates', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('export-jobs page source code links to /onboarding/bulk-upload for CSV upload', () => {
    // SEL-647: Check source code directly since component requires React Query
    const exportJobsSource = readFileSync(
      join(__dirname, '../../app/dashboard/export-jobs/page.tsx'),
      'utf-8'
    );
    
    // All old /ingest links should be updated to /onboarding/bulk-upload
    expect(exportJobsSource).toContain('href="/onboarding/bulk-upload"');
    expect(exportJobsSource).toContain('Upload a CSV');
  });

  it('export-jobs page source code links to /docs/quickstart for JSON events API', () => {
    // SEL-647: Check source code directly
    const exportJobsSource = readFileSync(
      join(__dirname, '../../app/dashboard/export-jobs/page.tsx'),
      'utf-8'
    );
    
    // JSON API links should be updated to quickstart with new text
    expect(exportJobsSource).toContain('href="/docs/quickstart"');
    expect(exportJobsSource).toContain('Send your first JSON event');
  });

  it('integrations page source code maintains /docs/api for API docs button', () => {
    // SEL-647: Check source code directly
    const integrationsSource = readFileSync(
      join(__dirname, '../../app/integrations/page.tsx'),
      'utf-8'
    );
    
    // Top API docs button should stay at /docs/api (not changed to /docs/quickstart)
    expect(integrationsSource).toContain('href="/docs/api"');
    expect(integrationsSource).toContain('API docs');
  });

  it('integrations page source code empty state links to /onboarding/bulk-upload', () => {
    // SEL-647: Check source code directly
    const integrationsSource = readFileSync(
      join(__dirname, '../../app/integrations/page.tsx'),
      'utf-8'
    );
    
    // Empty state CSV link should be updated
    expect(integrationsSource).toContain('href="/onboarding/bulk-upload"');
    expect(integrationsSource).toContain('Upload a CSV');
  });

  it('integrations page source code empty state shows "Send your first JSON event" with /docs/quickstart link', () => {
    // SEL-647: Check source code directly
    const integrationsSource = readFileSync(
      join(__dirname, '../../app/integrations/page.tsx'),
      'utf-8'
    );
    
    // Empty state JSON link should have new text and target
    expect(integrationsSource).toContain('Send your first JSON event');
    expect(integrationsSource).toContain('href="/docs/quickstart"');
  });
});
