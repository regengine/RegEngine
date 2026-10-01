import { render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import { ComplianceStatusWidget } from '@/components/dashboard/compliance-status-widget';
it.each(['COMPLIANT','UNASSESSED'])('does not claim regulatory compliance for %s alert monitoring',async(status)=>{
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:true,json:async()=>({status,status_label:status==='UNASSESSED'?'Not assessed':'Compliant',active_alert_count:0,critical_alert_count:0,active_alerts:[]})}));
 render(<ComplianceStatusWidget tenantId="fixture"/>);
 await waitFor(()=>expect(screen.getByRole('heading', {name:status==='UNASSESSED'?'Not assessed':'No active alerts'})).toBeInTheDocument());
 expect(screen.queryByText('All compliance requirements met')).not.toBeInTheDocument();
 expect(screen.queryByText('Last checked: just now')).not.toBeInTheDocument();
});
