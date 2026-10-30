import { describe, expect, it } from 'vitest';
import {
  CSV_HEADER,
  attentionRows,
  buildCsv,
  deriveLedger,
  derivePackages,
  deriveRows,
  detailFor,
  fixQueue,
  gapIndex,
  heroStatus,
  nextActions,
  overviewStats,
  parseView,
  recordState,
  scenarios,
  stableHash,
  windowRows,
} from '@/lib/demo-workspace/model';

const all = scenarios();
const first = all[0];

describe('demo workspace dataset', () => {
  it('ships five chains with exactly one gap each', () => {
    expect(all).toHaveLength(5);
    for (const scenario of all) {
      expect(scenario.chain.length).toBeGreaterThanOrEqual(6);
      expect(scenario.chain.length).toBeLessThanOrEqual(7);
      expect(scenario.chain.filter((r) => r.gap)).toHaveLength(1);
      expect(scenario.hue).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });
});

describe('record state and rows', () => {
  it('marks the gap row open until the scenario is fixed', () => {
    const idx = gapIndex(first);
    const gap = first.chain[idx];
    expect(recordState(gap, false)).toBe('needs-correction');
    expect(recordState(gap, true)).toBe('corrected');
    expect(recordState(first.chain[0], false)).toBe('committed');

    const open = deriveRows(first, {});
    expect(open[idx].lot).toBe('missing');
    expect(open[idx].openGap).toBe(true);

    const fixed = deriveRows(first, { [first.id]: true });
    expect(fixed[idx].lot).toBe(first.lot);
    expect(fixed[idx].state).toBe('corrected');
    expect(fixed[idx].openGap).toBe(false);
  });

  it('windows four rows around the gap and expands to the full chain', () => {
    const rows = deriveRows(first, {});
    const idx = gapIndex(first);
    const collapsed = windowRows(rows, idx, false);
    expect(collapsed.visible).toHaveLength(4);
    expect(collapsed.visible.some((r) => r.index === idx)).toBe(true);
    expect(collapsed.hidden).toBe(rows.length - 4);
    const expanded = windowRows(rows, idx, true);
    expect(expanded.visible).toHaveLength(rows.length);
    expect(expanded.hidden).toBe(0);
  });

  it('describes the gap, then the corrected record, in the detail panel', () => {
    const idx = gapIndex(first);
    const gap = detailFor(first, idx, {}, 'landing');
    expect(gap?.kind).toBe('gap');
    expect(gap?.canFix).toBe(true);
    expect(gap?.kv.map(([k]) => k)).toEqual(['Owner', 'Recovery', 'Date']);

    const workspaceGap = detailFor(first, idx, {}, 'workspace');
    expect(workspaceGap?.kv.map(([k]) => k)).toEqual(['Owner', 'Recovery', 'Date', 'Location']);

    const corrected = detailFor(first, idx, { [first.id]: true }, 'workspace');
    expect(corrected?.kind).toBe('corrected');
    expect(corrected?.canFix).toBe(false);
    expect(corrected?.kv.map(([k]) => k)).toContain('Event hash');

    expect(detailFor(first, null, {}, 'landing')).toBeNull();
  });
});

describe('hashes, ledger and packages', () => {
  it('produces deterministic stand-in hashes', () => {
    expect(stableHash('x')).toBe(stableHash('x'));
    expect(stableHash('x')).not.toBe(stableHash('y'));
    expect(stableHash('x')).toMatch(/^[0-9a-f]{8}…[0-9a-f]{4}$/);
  });

  it('chains every committed record and appends one entry per fix', () => {
    const total = all.reduce((sum, s) => sum + s.chain.length, 0);
    const open = deriveLedger(all, {});
    expect(open).toHaveLength(total - all.length);
    const after = deriveLedger(all, { [first.id]: true });
    expect(after).toHaveLength(open.length + 1);
    for (const entry of after) {
      expect(entry.ts).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:00-07:00$/);
      expect(entry.chainHash).not.toBe(entry.eventHash);
    }
    expect(new Set(after.map((e) => e.chainHash)).size).toBe(after.length);
  });

  it('writes an OPEN row instead of dropping the gap from the CSV', () => {
    const csv = buildCsv(first, {});
    const lines = csv.split('\n');
    expect(lines[0]).toBe(CSV_HEADER);
    expect(lines).toHaveLength(first.chain.length + 1);
    expect(lines[gapIndex(first) + 1]).toContain('"OPEN"');
    expect(lines[gapIndex(first) + 1]).toContain('""');
    const fixedCsv = buildCsv(first, { [first.id]: true });
    expect(fixedCsv).not.toContain('"OPEN"');
    expect(fixedCsv).toContain(`"${first.lot}"`);
  });

  it('flips a package to ready once its chain is fixed', () => {
    const before = derivePackages(all, {});
    expect(before.every((p) => !p.ready)).toBe(true);
    expect(before[0].badge).toBe(`${first.chain.length - 1} OF ${first.chain.length} READY`);
    const after = derivePackages(all, { [first.id]: true });
    expect(after[0].ready).toBe(true);
    expect(after[0].badge).toBe('READY');
    expect(after[0].manifest).not.toBe(before[0].manifest);
  });

  it('summarises the hero status strip', () => {
    const open = heroStatus(first, {});
    expect(open.open).toBe(1);
    expect(open.exportReady).toBe(false);
    expect(open.ledgerLine).toBe(`${first.chain.length - 1} of ${first.chain.length} records committed`);
    const done = heroStatus(first, { [first.id]: true });
    expect(done.exportReady).toBe(true);
    expect(done.exportBadge).toBe('Ready to export');
  });
});

describe('overview derivations', () => {
  it('counts open fixes down as chains are fixed', () => {
    expect(overviewStats(all, {}).open).toBe(5);
    expect(overviewStats(all, { [first.id]: true }).open).toBe(4);
    expect(attentionRows(all, {})).toHaveLength(5);
    expect(attentionRows(all, { [first.id]: true })).toHaveLength(4);
    expect(fixQueue(all, { [first.id]: true }).filter((f) => f.done)).toHaveLength(1);
  });

  it('orders next actions and drops the fix step once the queue is clear', () => {
    const everything = Object.fromEntries(all.map((s) => [s.id, true]));
    expect(nextActions(all, {}).map((a) => a.view)).toEqual(['fix', 'export', 'ledger']);
    expect(nextActions(all, everything).map((a) => a.view)).toEqual(['export', 'ledger']);
    expect(nextActions(all, {})[0].n).toBe('01');
  });

  it('parses the view from the location hash', () => {
    expect(parseView('#ledger')).toBe('ledger');
    expect(parseView('ledger')).toBe('ledger');
    expect(parseView('#nope')).toBe('overview');
    expect(parseView('')).toBe('overview');
  });
});
