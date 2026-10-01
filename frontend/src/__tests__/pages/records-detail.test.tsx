import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import RecordsPage from '@/app/records/page';
const mocks = vi.hoisted(() => ({ retry: vi.fn() }));
vi.mock('@/lib/auth-context', () => ({ useAuth: () => ({ tenantId: 'tenant-A' }) }));
vi.mock('@/hooks/use-control-plane', () => ({
  useCanonicalEvents: () => ({ data: { total: 1, events: [{ event_id: 'canonical-A', traceability_lot_code: 'LOT-A', event_type: 'receiving', source_system: 'csv_upload' }] } }),
  useCanonicalEvent: () => ({ error: new Error('503 Record service unavailable'), refetch: mocks.retry }),
}));
describe('Record detail recovery', () => {
  it('keeps the record list visible and exposes detail failure with retry', async () => {
    render(<RecordsPage />);
    await userEvent.click(screen.getByRole('button', { name: 'LOT-A' }));
    expect(screen.getByText('Unable to load record detail')).toBeInTheDocument();
    expect(screen.getByText('503 Record service unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'LOT-A' })).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: 'Retry detail' }));
    expect(mocks.retry).toHaveBeenCalledOnce();
  });
});
