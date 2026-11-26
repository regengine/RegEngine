/**
 * Tests for signed-out access to /onboarding/bulk-upload
 * 
 * Product decision: CSV template download and page viewing work without auth.
 * Server-side validate and commit require sign-in.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BulkUploadPage from '@/app/onboarding/bulk-upload/page';

// Mock dependencies
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
  },
}));

vi.mock('@/hooks/use-dashboard-refresh', () => ({
  notifyDashboardRefresh: vi.fn(),
}));

import { useAuth } from '@/lib/auth-context';
import { apiClient } from '@/lib/api-client';

const mockUseAuth = vi.mocked(useAuth);
const mockApiClient = vi.mocked(apiClient);

describe('Signed-out access to bulk upload', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('signed-out GET renders the page without 307 redirect', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      hasTenantSession: false,
      user: null,
    } as ReturnType<typeof useAuth>);

    // This render should succeed without throwing or redirecting
    const { container } = render(<BulkUploadPage />);
    
    // Page should render with the CSV template download button
    expect(screen.getByRole('button', { name: /csv template/i })).toBeInTheDocument();
    
    // Should not redirect to /login (no redirect means no empty container)
    expect(container.firstChild).not.toBeNull();
  });

  it('signed-out user can download CSV template', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      hasTenantSession: false,
      user: null,
    } as ReturnType<typeof useAuth>);

    // Mock createObjectURL and click for CSV download
    const createObjectURLSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:mock-csv-url');
    const revokeObjectURLSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    
    const anchorClick = vi.fn();
    const originalCreateElement = document.createElement.bind(document);
    const createElementSpy = vi.spyOn(document, 'createElement').mockImplementation((tag: string) => {
      const el = originalCreateElement(tag);
      if (tag === 'a') {
        Object.defineProperty(el, 'click', { value: anchorClick, writable: true });
      }
      return el;
    });

    render(<BulkUploadPage />);
    
    // Click CSV template download button
    const csvButton = screen.getByRole('button', { name: /csv template/i });
    await userEvent.click(csvButton);
    
    // CSV download should work (client-side blob creation)
    expect(createObjectURLSpy).toHaveBeenCalled();
    expect(anchorClick).toHaveBeenCalled();
    expect(revokeObjectURLSpy).toHaveBeenCalled();
    
    // Should NOT call server API for CSV (it's generated client-side)
    expect(mockApiClient.downloadSupplierBulkUploadTemplate).not.toHaveBeenCalled();
    
    createObjectURLSpy.mockRestore();
    revokeObjectURLSpy.mockRestore();
    createElementSpy.mockRestore();
  });

  it('signed-out save is blocked with sign-in prompt', async () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      hasTenantSession: false,
      user: null,
    } as ReturnType<typeof useAuth>);

    render(<BulkUploadPage />);
    
    // Upload a test CSV file
    const file = new File(['event_type,product_name,lot_number\nShip,Product1,LOT-001'], 'test.csv', { type: 'text/csv' });
    const input = screen.getByLabelText(/upload your file/i);
    await userEvent.upload(input, file);
    
    // Wait for local preview to complete
    await screen.findByText('Product1');
    
    // Click "Check my file" - this does LOCAL validation only
    await userEvent.click(screen.getByRole('button', { name: /check my file/i }));
    
    // Should show sign-in prompt for server validation
    expect(await screen.findByText(/sign in to run the full check and save/i)).toBeInTheDocument();
    
    // "Save records" button should be disabled
    expect(screen.getByRole('button', { name: /save records/i })).toBeDisabled();
    
    // Server validate and commit APIs should NOT be called
    expect(mockApiClient.parseSupplierBulkUpload).not.toHaveBeenCalled();
    expect(mockApiClient.validateSupplierBulkUpload).not.toHaveBeenCalled();
    expect(mockApiClient.commitSupplierBulkUpload).not.toHaveBeenCalled();
  });

  it('copy correctly limits "No account required" to viewing and template download', () => {
    mockUseAuth.mockReturnValue({
      isAuthenticated: false,
      hasTenantSession: false,
      user: null,
    } as ReturnType<typeof useAuth>);

    render(<BulkUploadPage />);
    
    // Should say template download needs no account
    expect(screen.getByText(/download the template with no account required/i)).toBeInTheDocument();
    
    // Should clarify that validation and saving require sign-in
    expect(screen.getByText(/sign in to validate and save your records/i)).toBeInTheDocument();
    
    // Should NOT promise server validation without auth
    const pageText = screen.getByText(/upload a csv to preview your data/i).textContent || '';
    expect(pageText.toLowerCase()).not.toContain('validate your data against');
  });
});

describe('XLSX card text', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockUseAuth.mockReturnValue({
      isAuthenticated: true,
      hasTenantSession: true,
      user: { email: 'test@example.com' },
    } as ReturnType<typeof useAuth>);
  });

  it('shows exact text: Preview. Multi-sheet workbook. Upload the CSV for now.', () => {
    render(<BulkUploadPage />);
    
    // Exact string assertion as requested
    expect(screen.getByText('Preview. Multi-sheet workbook. Upload the CSV for now.')).toBeInTheDocument();
  });
});
