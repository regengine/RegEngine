import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RecallResponsePage from '@/app/dashboard/recall-response/page';
const mocks = vi.hoisted(() => ({ complete: vi.fn(), fetch: vi.fn(), requests: { data: { tenant_id: 't', total: 1, skip: 0, limit: 50, requests: [{ id:'r', tenant_id:'t', request_type:'records_request', requested_at:'2026-09-29T00:00:00Z', deadline_at:'2026-09-30T00:00:00Z', status:'overdue', notes:null, completed_at:null, export_ids:[], time_remaining_seconds:0, response_hours:null }] }, isLoading:false, error:null, refetch:vi.fn() } }));
vi.mock('@/lib/tenant-context', () => ({ useTenant: () => ({ tenantId:'t' }) }));
vi.mock('@/lib/fetch-with-csrf', () => ({ fetchWithCsrf: mocks.fetch }));
vi.mock('@/hooks/use-sla', () => ({
  useSLARequests: () => mocks.requests,
  useSLADashboard: () => ({ data: {open_requests:1, overdue_requests:1, avg_response_hours:null, compliance_rate_pct:null} }),
  useSLAAlerts: () => ({ data: { alerts: [] } }),
  useCreateSLARequest: () => ({ mutate:vi.fn(), isPending:false }),
  useCompleteSLARequest: () => ({ mutate:mocks.complete, isPending:false }),
}));
vi.mock('framer-motion', () => ({ motion: { div: ({children, initial, animate, transition, ...props}: any) => <div {...props}>{children}</div>, span:({children,...props}:any)=><span>{children}</span>, circle:({initial,animate,transition,...props}:any)=><circle {...props}/> }, AnimatePresence:({children}:any)=><>{children}</> }));

const HASH = 'a'.repeat(64);
function dates() {
  fireEvent.change(screen.getByLabelText('Export start date'), {target:{value:'2026-09-01'}});
  fireEvent.change(screen.getByLabelText('Export end date'), {target:{value:'2026-10-01'}});
}
describe('Recall response consequential operations', () => {
  beforeEach(() => { vi.clearAllMocks(); URL.createObjectURL=vi.fn(()=> 'blob:export'); URL.revokeObjectURL=vi.fn(); vi.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=> {}); });
  it('missing dates and failed exports preserve the open request', async () => {
    render(<RecallResponsePage/>); const user=userEvent.setup();
    await user.click(screen.getByRole('button',{name:'Generate export'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('required');
    expect(mocks.fetch).not.toHaveBeenCalled();
    dates(); mocks.fetch.mockResolvedValue(new Response('unavailable',{status:503}));
    await user.click(screen.getByRole('button',{name:'Generate export'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('Request remains open');
    expect(mocks.complete).not.toHaveBeenCalled();
    expect(screen.queryByRole('button',{name:'Record response completion'})).not.toBeInTheDocument();
  });
  it('awaits audited artifact and requires separate scope attestation', async () => {
    mocks.fetch.mockResolvedValue(new Response('records csv',{headers:{'X-Export-Hash':HASH}}));
    render(<RecallResponsePage/>); const user=userEvent.setup(); dates();
    await user.click(screen.getByRole('button',{name:'Generate export'}));
    const close=await screen.findByRole('button',{name:'Record response completion'});
    expect(close).toBeDisabled(); expect(mocks.complete).not.toHaveBeenCalled();
    expect(screen.getByText(/Audit hash:/)).toHaveTextContent(HASH);
    await user.click(screen.getByRole('checkbox'));
    await user.type(screen.getByLabelText('Completion evidence'),'Reviewed scope and response');
    await user.click(close);
    expect(mocks.complete).toHaveBeenCalledWith({export_hash:HASH,start_date:'2026-09-01',end_date:'2026-10-01',acknowledged:true,completion_notes:'Reviewed scope and response'});
    expect(screen.getByText(/external delivery is not verified/i)).toBeInTheDocument();
    expect(screen.getByText('Response rate not yet measured')).toBeInTheDocument();
  });
  it('does not offer completion for an artifact without audit metadata', async () => {
    mocks.fetch.mockResolvedValue(new Response('records csv'));
    render(<RecallResponsePage/>); dates(); fireEvent.click(screen.getByRole('button',{name:'Generate export'}));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('no audit hash'));
    expect(mocks.complete).not.toHaveBeenCalled();
  });
});
