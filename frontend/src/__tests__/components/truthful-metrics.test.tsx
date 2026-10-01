import { render, screen } from '@testing-library/react';
import { beforeEach, it, expect, vi } from 'vitest';
import { MetricsOverviewWidget } from '@/components/dashboard/metrics-overview-widget';
const metrics = vi.hoisted(() => vi.fn());
vi.mock('@/hooks/use-api', () => ({ useSystemMetrics: () => metrics(), useSystemStatus: () => ({data:{overall_status:'healthy'}}) }));
beforeEach(() => metrics.mockReturnValue({data: undefined, isLoading:false, isError:true}));
it('shows unavailable metrics without asserting a saved-run absence', () => {
 render(<MetricsOverviewWidget/>);
 expect(screen.getByText('Score unavailable')).toBeInTheDocument();
 expect(screen.queryByText('No saved Inflow Workbench run yet')).not.toBeInTheDocument();
});
it('retains an assessed real zero and does not infer chain validity', () => {
 metrics.mockReturnValue({data:{compliance_score:0, events_ingested:0, chain_length:12, chain_valid:null, open_alerts:0, chain_verification_status:'unavailable'}, isLoading:false});
 render(<MetricsOverviewWidget/>);
 expect(screen.getByText('Verification unavailable')).toBeInTheDocument();
 expect(screen.queryByText('Broken')).not.toBeInTheDocument();
 expect(screen.getAllByText('0').length).toBeGreaterThanOrEqual(3);
});

it('renders the completed verifier scope including zero-entry coverage', () => {
 metrics.mockReturnValue({data:{chain_valid:true,chain_length:0,chain_verified_scope:'ingestion webhook chain'},isLoading:false});
 render(<MetricsOverviewWidget/>);
 expect(screen.getByText('ingestion webhook chain')).toBeInTheDocument();
 expect(screen.getByText('0 entries')).toBeInTheDocument();
});
