import { beforeEach, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import BulkUploadPage from '@/app/onboarding/bulk-upload/page';

const mocks = vi.hoisted(() => ({ authenticated: true, parse: vi.fn(), validate: vi.fn(), commit: vi.fn(), status: vi.fn(), refresh: vi.fn() }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ isAuthenticated: mocks.authenticated }) }));
vi.mock('@/lib/api-client', () => ({ apiClient: { parseSupplierBulkUpload: mocks.parse, validateSupplierBulkUpload: mocks.validate, commitSupplierBulkUpload: mocks.commit, getSupplierBulkUploadStatus: mocks.status } }));
vi.mock('@/hooks/use-dashboard-refresh', () => ({ notifyDashboardRefresh: mocks.refresh }));

beforeEach(() => { vi.clearAllMocks(); mocks.authenticated = true; });

function selectCsv(text = 'event_type,product_name,lot_number\nshipping,"Lettuce, green",L1') {
  fireEvent.change(screen.getByLabelText('Upload your file'), { target: { files: [new File([text], 'supplier.csv', { type: 'text/csv' })] } });
}

it('keeps a successful commit distinct from a failed status refresh', async () => {
  mocks.parse.mockResolvedValue({ session_id: 's1', detected_format: 'csv', facilities: 1, ftl_scopes: 0, tlcs: 1, events: 1, warnings: [] });
  mocks.validate.mockResolvedValue({ preview: { can_commit: true, errors: [] } });
  mocks.commit.mockResolvedValue({ summary: { facilities_created: 1, facilities_updated: 0, tlcs_created: 1, tlcs_updated: 0, events_chained: 1, sync_warning_count: 0 } });
  mocks.status.mockRejectedValue(new Error('Network error'));
  render(<BulkUploadPage />);
  selectCsv();
  await userEvent.click(screen.getByRole('button', { name: 'Parse + Validate' }));
  await screen.findByText('Ready to commit.');
  await userEvent.click(screen.getByRole('button', { name: 'Commit Import' }));
  expect(await screen.findByText('Commit Complete')).toBeInTheDocument();
  expect(await screen.findByText(/Commit succeeded, but status refresh failed/)).toBeInTheDocument();
  expect(mocks.commit).toHaveBeenCalledTimes(1);
  expect(mocks.refresh).toHaveBeenCalledTimes(1);
});

it('labels local checks as preliminary and cannot commit without authentication', async () => {
  mocks.authenticated = false;
  render(<BulkUploadPage />);
  selectCsv();
  await screen.findByText('Lettuce, green');
  await userEvent.click(screen.getByRole('button', { name: 'Parse + Validate' }));
  expect(await screen.findByText('Local structure checks passed. Server validation is required before commit.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Commit Import' })).toBeDisabled();
  expect(mocks.parse).not.toHaveBeenCalled();
  expect(mocks.commit).not.toHaveBeenCalled();
});
