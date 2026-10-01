import { act, render, screen, waitFor, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { beforeEach, expect, it, vi } from 'vitest';
import ComplianceDashboardPage from '@/app/dashboard/compliance/page';
const scoreFetch = vi.hoisted(() => vi.fn());
const readinessFetch = vi.hoisted(() => vi.fn());
vi.mock('@/lib/auth-context', () => ({useAuth:()=>({isAuthenticated:true})}));
vi.mock('@/lib/tenant-context', () => ({useTenant:()=>({tenantId:'tenant-fixture'})}));
vi.mock('@/lib/api-hooks', () => ({fetchComplianceScore: (...args:unknown[]) => scoreFetch(...args), fetchWorkbenchReadinessSummary:()=>readinessFetch()}));
vi.mock('next/navigation', () => ({useRouter:()=>({push:vi.fn()}),usePathname:()=>'/dashboard/compliance'}));
function renderPage() {
 const client = new QueryClient({defaultOptions:{queries:{retry:false}}});
 return {client,...render(<QueryClientProvider client={client}><ComplianceDashboardPage/></QueryClientProvider>)};
}
beforeEach(()=>{
 scoreFetch.mockReset();
 scoreFetch.mockResolvedValue({overall_score:40,grade:'F',events_analyzed:10,breakdown:{chain_integrity:{score:100,detail:'fixture'}},next_actions:[],assessment_status:'available',scoring_policy:{weights:{chain_integrity:40}}});
 readinessFetch.mockReset();
 readinessFetch.mockResolvedValue(null);
});
it('shows the backend policy weight including a changed policy', async()=>{
 scoreFetch.mockResolvedValue({overall_score:40,grade:'F',events_analyzed:10,breakdown:{chain_integrity:{score:100,detail:'fixture'}},next_actions:[],assessment_status:'available',scoring_policy:{version:'fixture-v2',weights:{chain_integrity:40},rounding:'truncate'}});
 renderPage();
 await waitFor(()=>expect(screen.getByText('40%')).toBeInTheDocument());
 expect(screen.queryByText('25%')).not.toBeInTheDocument();
});
it.each(['unavailable','unassessed'])('does not show a compliance grade for %s scoring', async(assessment_status)=>{
 scoreFetch.mockResolvedValue({overall_score:0,grade:'F',assessment_status});
 renderPage();
 await waitFor(()=>expect(screen.getByText(assessment_status==='unassessed' ? /Not assessed\. Add traceability evidence/ : /Scoring unavailable\. No compliance assessment/)).toBeInTheDocument());
 expect(screen.queryByText('Grade F')).not.toBeInTheDocument();
});

it('shows preflight unavailable without inventing zero fixes or no saved run', async()=>{
 readinessFetch.mockRejectedValue(new Error('503'));
 renderPage();
 await waitFor(()=>expect(screen.getByText('Preflight unavailable')).toBeInTheDocument());
 expect(screen.queryByText('No saved preflight run yet')).not.toBeInTheDocument();
 expect(screen.queryByText('0 open fixes')).not.toBeInTheDocument();
 expect(screen.queryByText('Not yet')).not.toBeInTheDocument();
 expect(screen.queryByText('none')).not.toBeInTheDocument();
});
it('suppresses prior export eligibility after a failed preflight refresh',async()=>{
 readinessFetch.mockResolvedValueOnce({score:100,label:'Ready',unresolved_fix_count:0,export_eligible:true,run_id:'saved-run',source:'live'}).mockRejectedValue(new Error('offline'));
 const {client}=renderPage();
 await waitFor(()=>expect(screen.getByText('Yes')).toBeInTheDocument());
 await act(async()=>{await client.invalidateQueries({queryKey:['inflow-workbench-readiness','tenant-fixture']});});
 await waitFor(()=>expect(screen.getByText('Preflight unavailable')).toBeInTheDocument());
 expect(screen.queryByText('Yes')).not.toBeInTheDocument();
 expect(screen.queryByText('0 open fixes')).not.toBeInTheDocument();
});

it('preserves the successful no-run contract rather than treating it as unavailable',async()=>{
 readinessFetch.mockResolvedValue({score:null,label:null,unresolved_fix_count:0,export_eligible:false,run_id:null,source:'none'});
 renderPage();
 await waitFor(()=>expect(screen.getByText('No saved preflight run yet')).toBeInTheDocument());
 expect(screen.getByText('0 open fixes')).toBeInTheDocument();
 expect(screen.getByText('Not yet')).toBeInTheDocument();
 expect(screen.getByText('none')).toBeInTheDocument();
});
it('retains an actual zero score from a saved run',async()=>{
 readinessFetch.mockResolvedValue({score:0,label:'Needs correction',unresolved_fix_count:0,export_eligible:false,run_id:'zero-run',source:'live'});
 renderPage();
 await waitFor(()=>expect(screen.getByText('zero-run')).toBeInTheDocument());
 expect(within(screen.getByText('Needs correction').parentElement!).getByText('0')).toBeInTheDocument();
 expect(screen.queryByText('No saved preflight run yet')).not.toBeInTheDocument();
});
it('keeps pending preflight values unknown while the score is available',async()=>{
 readinessFetch.mockReturnValue(new Promise(()=>{}));
 renderPage();
 await waitFor(()=>expect(screen.getByText('Preflight loading')).toBeInTheDocument());
 expect(screen.queryByText('0 open fixes')).not.toBeInTheDocument();
 expect(screen.queryByText('No saved preflight run yet')).not.toBeInTheDocument();
 expect(screen.queryByText('Not yet')).not.toBeInTheDocument();
});
