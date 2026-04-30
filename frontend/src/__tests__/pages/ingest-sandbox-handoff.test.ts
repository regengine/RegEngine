import { describe, expect, it } from 'vitest';
import { parseSandboxHandoff } from '@/app/ingest/sandbox-handoff';

describe('sandbox import handoff parsing', () => {
  it('reads detected columns, event counts, blockers, and next mapping action', () => {
    const result = parseSandboxHandoff(JSON.stringify({
      version: 1,
      source: 'free-sandbox',
      createdAt: '2026-04-30T12:00:00.000Z',
      summary: {
        totalEvents: 4,
        passedChecks: 2,
        needsWork: 2,
        blockers: 1,
      },
      detectedColumns: ['cte_type', 'traceability_lot_code', 'event_time'],
      diagnosis: {
        total_events: 4,
        compliant_events: 2,
        non_compliant_events: 2,
        blocking_reasons: ['Missing traceability lot code on row 3'],
      },
    }));

    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.view.detectedColumns).toEqual(['cte_type', 'traceability_lot_code', 'event_time']);
    expect(result.view.totalEvents).toBe(4);
    expect(result.view.passedChecks).toBe(2);
    expect(result.view.needsWork).toBe(2);
    expect(result.view.blockerCount).toBe(1);
    expect(result.view.blockers).toEqual(['Missing traceability lot code on row 3']);
    expect(result.view.nextMappingAction).toContain('Resolve sandbox blockers');
  });

  it('falls back to CSV headers when detectedColumns are absent', () => {
    const result = parseSandboxHandoff(JSON.stringify({
      version: 1,
      source: 'free-sandbox',
      createdAt: '2026-04-30T12:00:00.000Z',
      summary: {
        totalEvents: 1,
        passedChecks: 1,
        needsWork: 0,
        blockers: 0,
      },
      csv: 'cte_type,lot,quantity\nshipping,L-1,12',
    }));

    expect(result.ok).toBe(true);
    if (!result.ok) return;

    expect(result.view.detectedColumns).toEqual(['cte_type', 'lot', 'quantity']);
    expect(result.view.nextMappingAction).toContain('Map detected columns');
  });

  it('rejects malformed or unsupported handoffs', () => {
    expect(parseSandboxHandoff(null).ok).toBe(false);
    expect(parseSandboxHandoff('{bad json').ok).toBe(false);
    expect(parseSandboxHandoff(JSON.stringify({ version: 2, summary: {} })).ok).toBe(false);
  });
});
