import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import RequestCaseDetailPage from '@/app/requests/[id]/page';
const state = vi.hoisted(() => ({
  data: {request_case_id:'r', requesting_party:'FDA', package_status:'assembling', scope_type:'tlc_trace', affected_lots:['LOT-1'], affected_facilities:[], total_records:1, gap_count:0, active_exception_count:0, request_received_at:'2026-10-01T00:00:00Z', response_due_at:'2026-10-02T00:00:00Z', signoffs:[]},
  signoff:vi.fn(), submit:vi.fn(), lookup:vi.fn(),
}));
vi.mock('next/navigation',()=> ({useParams:()=> ({id:'r'})}));
vi.mock('@/lib/auth-context',()=> ({useAuth:()=> ({tenantId:'t',user:{email:'reviewer@example.test'}})}));
vi.mock('@/hooks/use-request-workflow',()=> ({
  useRequestCase:(...args:any[])=> {state.lookup(...args);return {data:state.data};},
  useRequestSignoff:()=> ({mutate:state.signoff,isPending:false}),
  usePackageHistory:()=> ({data:{packages:[{package_id:'p',version_number:1,generated_at:'2026-10-01'}]}}),
  useAssemblePackage:()=> ({mutate:vi.fn(),isPending:false}),
  useSubmitPackage:()=> ({mutate:state.submit,isPending:false}),
}));
describe('request reviews and history',()=> {
  beforeEach(()=> {vi.clearAllMocks(); state.data.package_status='assembling';});
  it('requires explicit rationale for existing package review transition',async()=> {
    const user=userEvent.setup();render(<RequestCaseDetailPage/>);
    const button=screen.getByRole('button',{name:'Sign off package review'});expect(button).toBeDisabled();
    await user.type(screen.getByLabelText('Review or submission rationale'),'Verified lot scope and package');
    await user.click(button);
    expect(state.signoff).toHaveBeenCalledWith({requestCaseId:'r',signoff_type:'package_review',signed_by:'reviewer@example.test',notes:'Verified lot scope and package'},expect.any(Object));
  });
  it('preserves rationale and displays stale-state rejection',async()=> {
    state.data.package_status='internal_review';state.signoff.mockImplementation((_input,options)=>options.onError(new Error('Case changed; reload')));
    const user=userEvent.setup();render(<RequestCaseDetailPage/>);
    await user.type(screen.getByLabelText('Review or submission rationale'),'Reviewed evidence');
    await user.click(screen.getByRole('button',{name:'Sign off final approval'}));
    expect(screen.getByRole('alert')).toHaveTextContent('Case changed');
    expect(screen.getByLabelText('Review or submission rationale')).toHaveValue('Reviewed evidence');
    expect(state.submit).not.toHaveBeenCalled();
  });
  it('reads retained completed/amended case by ID and retains package history',()=> {
    state.data.package_status='amended';render(<RequestCaseDetailPage/>);
    expect(state.lookup).toHaveBeenCalledWith('t','r');
    expect(screen.getByText('Response Packages (1)')).toBeInTheDocument();
    expect(screen.queryByRole('button',{name:'Assemble Package'})).not.toBeInTheDocument();
  });
});

it.each(['gap_analysis','exception_triage','assembling','internal_review','ready'])('offers missing scope approval at %s without hiding later review work', async (stage) => {
  state.data.package_status=stage;
  const user=userEvent.setup();render(<RequestCaseDetailPage/>);
  const scope=screen.getByRole('button',{name:'Sign off scope'});
  await user.type(screen.getByLabelText('Review or submission rationale'),'Reviewed the requested lot scope');
  await user.click(scope);
  expect(state.signoff).toHaveBeenCalledWith(expect.objectContaining({requestCaseId:'r',signoff_type:'scope_approval'}),expect.any(Object));
});
