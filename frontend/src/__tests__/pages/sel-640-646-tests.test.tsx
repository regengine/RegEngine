/**
 * Tests for SEL-640 through SEL-646 (High priority UX fixes)
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BulkUploadPage from '@/app/onboarding/bulk-upload/page';
import TracePage from '@/app/trace/page';

// Mock the dependencies
vi.mock('next/navigation', () => ({
  useSearchParams: () => ({
    get: () => null,
  }),
  useRouter: () => ({
    push: vi.fn(),
  }),
}));

vi.mock('@/lib/auth-context', () => ({
  useAuth: vi.fn(),
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
  },
}));

vi.mock('@/hooks/use-dashboard-refresh', () => ({
  notifyDashboardRefresh: vi.fn(),
}));

import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';

const mockUseAuth = vi.mocked(useAuth);
const mockApiClient = vi.mocked(apiClient);

describe('SEL-640: Signed-out CSV template download', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      hasTenantSession: false,
    } as ReturnType<typeof useAuth>);
  });

  it('allows CSV template download when signed out', async () => {
    const user = userEvent.setup();
    render(<BulkUploadPage />);

    const csvButton = screen.getByText('CSV Template').closest('button');
    expect(csvButton).not.toBeDisabled();

    // Mock createObjectURL and click
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-url');
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});

    await user.click(csvButton!);

    await waitFor(() => {
      expect(createObjectURLSpy).toHaveBeenCalled();
    });

    createObjectURLSpy.mockRestore();
    revokeObjectURLSpy.mockRestore();
  });

  it('shows "Sign in to download" helper text for XLSX when signed out', () => {
    render(<BulkUploadPage />);
    expect(screen.getByText('Sign in to download')).toBeInTheDocument();
  });

  it('shows updated CSV card copy', () => {
    render(<BulkUploadPage />);
    expect(screen.getByText('Start here. One row per event, with the columns RegEngine checks.')).toBeInTheDocument();
  });
});

describe('SEL-643: Bulk-upload success state', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      hasTenantSession: true,
    } as ReturnType<typeof useAuth>);
  });

  it('shows "Records saved" instead of "Commit Complete"', async () => {
    const file = new File(['facility_name,product_name\nFac1,Prod1'], 'test.csv', { type: 'text/csv' });
    
    mockApiClient.parseSupplierBulkUpload.mockResolvedValue({
      session_id: 'test-session',
      detected_format: 'csv',
      facilities: 1,
      ftl_scopes: 1,
      tlcs: 1,
      events: 1,
    } as never);

    mockApiClient.validateSupplierBulkUpload.mockResolvedValue({
      preview: {
        can_commit: true,
        facilities_to_create: 1,
        facilities_to_update: 0,
        tlcs_to_create: 1,
        tlcs_to_update: 0,
        ftl_scopes_to_upsert: 1,
        events_to_chain: 1,
      },
    } as never);

    mockApiClient.commitSupplierBulkUpload.mockResolvedValue({
      summary: {
        facilities_created: 1,
        facilities_updated: 0,
        tlcs_created: 1,
        tlcs_updated: 0,
        events_chained: 1,
        sync_warning_count: 0,
        sync_warnings: [],
      },
    } as never);

    const user = userEvent.setup();
    render(<BulkUploadPage />);

    const input = screen.getByLabelText(/upload your file/i);
    await user.upload(input, file);

    await waitFor(() => screen.getByRole('button', { name: /parse \+ validate/i }));
    await user.click(screen.getByRole('button', { name: /parse \+ validate/i }));

    await waitFor(() => screen.getByRole('button', { name: /commit import/i }));
    await user.click(screen.getByRole('button', { name: /commit import/i }));

    expect(await screen.findByText('Records saved')).toBeInTheDocument();
  });

  it('shows "Lot codes" instead of "TLCs"', async () => {
    const file = new File(['facility_name,product_name\nFac1,Prod1'], 'test.csv', { type: 'text/csv' });
    
    mockApiClient.parseSupplierBulkUpload.mockResolvedValue({
      session_id: 'test-session',
      detected_format: 'csv',
      facilities: 1,
      ftl_scopes: 1,
      tlcs: 1,
      events: 1,
    } as never);

    mockApiClient.validateSupplierBulkUpload.mockResolvedValue({
      preview: {
        can_commit: true,
        facilities_to_create: 1,
        facilities_to_update: 0,
        tlcs_to_create: 1,
        tlcs_to_update: 0,
        ftl_scopes_to_upsert: 1,
        events_to_chain: 1,
      },
    } as never);

    mockApiClient.commitSupplierBulkUpload.mockResolvedValue({
      summary: {
        facilities_created: 1,
        facilities_updated: 0,
        tlcs_created: 1,
        tlcs_updated: 0,
        events_chained: 1,
        sync_warning_count: 0,
        sync_warnings: [],
      },
    } as never);

    const user = userEvent.setup();
    render(<BulkUploadPage />);

    const input = screen.getByLabelText(/upload your file/i);
    await user.upload(input, file);

    await waitFor(() => screen.getByRole('button', { name: /parse \+ validate/i }));
    await user.click(screen.getByRole('button', { name: /parse \+ validate/i }));

    await waitFor(() => screen.getByRole('button', { name: /commit import/i }));
    await user.click(screen.getByRole('button', { name: /commit import/i }));

    expect(await screen.findByText('Lot codes')).toBeInTheDocument();
  });

  it('shows action links after successful commit', async () => {
    const file = new File(['facility_name,product_name\nFac1,Prod1'], 'test.csv', { type: 'text/csv' });
    
    mockApiClient.parseSupplierBulkUpload.mockResolvedValue({
      session_id: 'test-session',
      detected_format: 'csv',
      facilities: 1,
      ftl_scopes: 1,
      tlcs: 1,
      events: 1,
    } as never);

    mockApiClient.validateSupplierBulkUpload.mockResolvedValue({
      preview: {
        can_commit: true,
        facilities_to_create: 1,
        facilities_to_update: 0,
        tlcs_to_create: 1,
        tlcs_to_update: 0,
        ftl_scopes_to_upsert: 1,
        events_to_chain: 1,
      },
    } as never);

    mockApiClient.commitSupplierBulkUpload.mockResolvedValue({
      summary: {
        facilities_created: 1,
        facilities_updated: 0,
        tlcs_created: 1,
        tlcs_updated: 0,
        events_chained: 1,
        sync_warning_count: 0,
        sync_warnings: [],
      },
    } as never);

    const user = userEvent.setup();
    render(<BulkUploadPage />);

    const input = screen.getByLabelText(/upload your file/i);
    await user.upload(input, file);

    await waitFor(() => screen.getByRole('button', { name: /parse \+ validate/i }));
    await user.click(screen.getByRole('button', { name: /parse \+ validate/i }));

    await waitFor(() => screen.getByRole('button', { name: /commit import/i }));
    await user.click(screen.getByRole('button', { name: /commit import/i }));

    expect(await screen.findByRole('link', { name: /trace a lot/i })).toHaveAttribute('href', '/trace');
    expect(await screen.findByRole('link', { name: /export fda spreadsheet/i })).toHaveAttribute('href', '/trace');
  });
});

describe('SEL-644 & SEL-646: Trace page error messages', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      hasTenantSession: true,
    } as ReturnType<typeof useAuth>);
  });

  it('shows improved no-result message with CSV upload link', async () => {
    mockApiClient.getSupplierFDAExportPreview.mockResolvedValue({
      rows: [],
      total_count: 0,
    } as never);

    const user = userEvent.setup();
    render(<TracePage />);

    await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-NOTFOUND');
    await user.click(screen.getByRole('button', { name: /trace/i }));

    expect(await screen.findByText(/no records found for lot code/i)).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /upload a csv/i })).toHaveAttribute('href', '/onboarding/bulk-upload');
  });

  it('shows generic error message and logs technical details', async () => {
    const consoleErrorSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    
    mockApiClient.getSupplierFDAExportPreview.mockRejectedValue(new Error('Network timeout'));

    const user = userEvent.setup();
    render(<TracePage />);

    await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-ERROR');
    await user.click(screen.getByRole('button', { name: /trace/i }));

    expect(await screen.findByText(/we could not run this trace/i)).toBeInTheDocument();
    expect(consoleErrorSpy).toHaveBeenCalledWith('Trace query error:', 'Network timeout');

    consoleErrorSpy.mockRestore();
  });

  it('handles 404 export error with CSV upload link', async () => {
    mockApiClient.downloadSupplierFDARecords.mockRejectedValue({
      response: { status: 404 },
    });

    const user = userEvent.setup();
    render(<TracePage />);

    await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-NOTFOUND');
    await user.click(screen.getByRole('button', { name: /export fda spreadsheet/i }));

    expect(await screen.findByText(/there are no records for lot code/i)).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /upload a csv/i })).toHaveAttribute('href', '/onboarding/bulk-upload');
  });

  it('handles 401 export error with sign-in link', async () => {
    mockApiClient.downloadSupplierFDARecords.mockRejectedValue({
      response: { status: 401 },
    });

    const user = userEvent.setup();
    render(<TracePage />);

    await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-UNAUTH');
    await user.click(screen.getByRole('button', { name: /export fda spreadsheet/i }));

    expect(await screen.findByText(/your session ended/i)).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /sign in again/i })).toHaveAttribute('href', '/login');
  });

  it('handles 403 export error with sign-in link', async () => {
    mockApiClient.downloadSupplierFDARecords.mockRejectedValue({
      response: { status: 403 },
    });

    const user = userEvent.setup();
    render(<TracePage />);

    await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-FORBIDDEN');
    await user.click(screen.getByRole('button', { name: /export fda spreadsheet/i }));

    expect(await screen.findByText(/your session ended/i)).toBeInTheDocument();
    expect(await screen.findByRole('link', { name: /sign in again/i })).toHaveAttribute('href', '/login');
  });

  it('handles other export errors with generic message', async () => {
    mockApiClient.downloadSupplierFDARecords.mockRejectedValue({
      response: { status: 500 },
    });

    const user = userEvent.setup();
    render(<TracePage />);

    await user.type(screen.getByPlaceholderText(/enter tlc/i), 'TLC-ERROR');
    await user.click(screen.getByRole('button', { name: /export fda spreadsheet/i }));

    expect(await screen.findByText(/we could not build the fda spreadsheet/i)).toBeInTheDocument();
  });
});
