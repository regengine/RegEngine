import { describe, it, expect } from 'vitest';
import { decodeSLARequests, decodeSLAAlerts } from '@/hooks/use-sla';
import { exportWindowParams } from '@/lib/recall-export';
import { completedPhaseCount } from '@/components/fsma/phase-gates';
describe('recall wire contracts', () => {
  it('decodes actual envelopes and rejects malformed data', () => {
    expect(decodeSLARequests({ tenant_id: 't', total: 0, skip: 0, limit: 50, requests: [] }).requests).toEqual([]);
    expect(decodeSLARequests({ tenant_id: 't', total: 52, skip: 50, limit: 50, requests: [{ id: 'r', status:'open', export_ids:[], requested_at:'2026-10-01', deadline_at:'2026-10-02' }] }).total).toBe(52);
    expect(decodeSLAAlerts({ tenant_id: 't', alerts: [{ id: 'a', message:'deadline' }] }).alerts).toEqual([{ id: 'a', message:'deadline' }]);
    expect(() => decodeSLARequests({})).toThrow();
    expect(() => decodeSLAAlerts({ alerts: null })).toThrow();
  });
  it('requires bounded valid dates', () => {
    expect(() => exportWindowParams('', '')).toThrow('required');
    expect(() => exportWindowParams('2026-10-02', '2026-10-01')).toThrow();
    expect(() => exportWindowParams('2026-01-01', '2026-10-01')).toThrow('90');
    expect(() => exportWindowParams('2026-02-30', '2026-03-01')).toThrow();
    expect(exportWindowParams('2026-09-01', '2026-10-01').get('start_date')).toBe('2026-09-01');
  });
  it('completes only contiguous recorded milestones', () => {
    expect(completedPhaseCount([], false)).toBe(1);
    expect(completedPhaseCount(['records_assembled'], false)).toBe(2);
    expect(completedPhaseCount(['verified'], false)).toBe(1);
    expect(completedPhaseCount([], true)).toBe(1);
  });
});
