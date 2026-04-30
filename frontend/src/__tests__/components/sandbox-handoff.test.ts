import { describe, expect, it } from 'vitest';
import {
  buildSandboxOperationalHandoff,
  SANDBOX_HANDOFF_STORAGE_KEY,
  saveSandboxOperationalHandoff,
} from '@/components/marketing/sandbox-handoff';

describe('sandbox operational handoff', () => {
  it('builds the session handoff contract from a sandbox result and detected CSV headers', () => {
    const handoff = buildSandboxOperationalHandoff({
      csv: '"cte_type",traceability_lot_code,product_description\nshipping,LOT-1,Romaine',
      createdAt: '2026-04-30T12:00:00.000Z',
      diagnosis: { status: 'needs_work' },
      corrections: [{ title: 'Fill required KDEs' }],
      result: {
        total_events: 1,
        non_compliant_events: 1,
        total_rule_failures: 2,
        blocking_reasons: ['Missing BOL'],
        events: [
          {
            rules_passed: 3,
            blocking_defects: [{ rule_title: 'Reference document required' }],
            all_results: [],
          },
        ],
      },
    });

    expect(handoff).toEqual({
      version: 1,
      source: 'free-sandbox',
      createdAt: '2026-04-30T12:00:00.000Z',
      summary: {
        totalEvents: 1,
        passedChecks: 3,
        needsWork: 1,
        blockers: 1,
      },
      csv: '"cte_type",traceability_lot_code,product_description\nshipping,LOT-1,Romaine',
      detectedColumns: ['cte_type', 'traceability_lot_code', 'product_description'],
      diagnosis: { status: 'needs_work' },
      corrections: [{ title: 'Fill required KDEs' }],
    });
  });

  it('persists the handoff under the agreed sessionStorage key', () => {
    const storage = new Map<string, string>();
    const mockStorage = {
      setItem: (key: string, value: string) => storage.set(key, value),
    } as unknown as Storage;
    const handoff = buildSandboxOperationalHandoff({
      csv: 'cte_type\nreceiving',
      result: {
        total_events: 1,
        non_compliant_events: 0,
        total_rule_failures: 0,
        blocking_reasons: [],
        events: [{ rules_passed: 4, all_results: [] }],
      },
      createdAt: '2026-04-30T12:00:00.000Z',
    });

    saveSandboxOperationalHandoff(handoff, mockStorage);

    expect(JSON.parse(storage.get(SANDBOX_HANDOFF_STORAGE_KEY) || '{}')).toMatchObject({
      version: 1,
      source: 'free-sandbox',
      summary: { totalEvents: 1, passedChecks: 4, needsWork: 0, blockers: 0 },
      detectedColumns: ['cte_type'],
    });
  });
});
