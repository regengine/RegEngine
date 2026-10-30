/**
 * Pure derivations for the public demo workspace and the landing-page hero
 * workbench. No React, no DOM: everything here is a function of the static
 * scenario dataset plus a small amount of visitor state (selected scenario,
 * selected row, which scenarios have been "fixed").
 *
 * Hashes are deterministic stand-ins (a djb2 pair), not SHA-256. The ledger
 * and manifest hashes exist so the surfaces can show the shape of a
 * hash-chained record; the real engine uses SHA-256 and `verify_chain.py`.
 */
import data from './recall-scenarios.json';

export interface Kdes {
  lot: string;
  qty: string;
  location: string;
}

export interface Gap {
  field: string;
  cfr: string;
  reason: string;
  owner: string;
  recovery: string;
}

export interface ChainRecord {
  cte: string;
  firm: string;
  place: string;
  date: string;
  kdes: Kdes;
  gap?: Gap;
}

export interface ScenarioSource {
  title: string;
  agent: string;
  firstRecall: string;
  pattern: string;
}

export interface Scenario {
  id: string;
  food: string;
  ftlCategory: string;
  hue: string;
  source: ScenarioSource;
  request: string;
  lot: string;
  chain: ChainRecord[];
}

/** scenario id -> true once the visitor has sent the correction link. */
export type FixedMap = Readonly<Record<string, boolean>>;

export type RecordState = 'committed' | 'needs-correction' | 'corrected';

export type DemoSurface = 'landing' | 'workspace';

export const VIEW_IDS = ['overview', 'import', 'fix', 'ledger', 'export'] as const;
export type ViewId = (typeof VIEW_IDS)[number];

export const SHORT_LABELS: Readonly<Record<string, string>> = {
  peppers: 'Jalapeños',
  cucumbers: 'Cucumbers',
  shrimp: 'Shrimp',
  cantaloupe: 'Cantaloupe',
  cheese: 'Soft cheese',
};

/** Shown while a record has no traceability lot code. */
export const MISSING_LOT = 'missing';

const SCENARIOS = (data as { scenarios: Scenario[] }).scenarios;

export function scenarios(): readonly Scenario[] {
  return SCENARIOS;
}

export function shortLabel(scenario: Pick<Scenario, 'id' | 'food'>): string {
  return SHORT_LABELS[scenario.id] ?? scenario.food;
}

/** "Rancho Las Lomas (grower)" -> "Rancho Las Lomas". */
export function firmName(firm: string): string {
  return firm.replace(/ \(.*\)$/, '');
}

export function fileName(scenario: Scenario): string {
  return `${scenario.id}_receiving_log.xlsx`;
}

export function gapIndex(scenario: Scenario): number {
  return scenario.chain.findIndex((record) => Boolean(record.gap));
}

export function gapRecord(scenario: Scenario): ChainRecord | undefined {
  return scenario.chain.find((record) => Boolean(record.gap));
}

export function isFixed(scenario: Pick<Scenario, 'id'>, fixed: FixedMap): boolean {
  return Boolean(fixed[scenario.id]);
}

export function recordState(record: ChainRecord, scenarioFixed: boolean): RecordState {
  if (!record.gap) return 'committed';
  return scenarioFixed ? 'corrected' : 'needs-correction';
}

export function parseView(hash: string): ViewId {
  const value = hash.replace(/^#/, '');
  return (VIEW_IDS as readonly string[]).includes(value) ? (value as ViewId) : 'overview';
}

/** Deterministic stand-in hash: `xxxxxxxx…xxxx`. Not SHA-256. */
export function stableHash(input: string): string {
  let h1 = 5381;
  let h2 = 52711;
  for (let i = 0; i < input.length; i += 1) {
    const c = input.charCodeAt(i);
    h1 = (h1 * 33) ^ c;
    h2 = (h2 * 31) ^ c;
  }
  const hex = (n: number) => (n >>> 0).toString(16).padStart(8, '0');
  return `${hex(h1)}…${hex(h2).slice(-4)}`;
}

export function eventHash(scenario: Pick<Scenario, 'id'>, record: ChainRecord): string {
  return stableHash(scenario.id + record.cte + record.date);
}

export interface Row {
  index: number;
  cte: string;
  firm: string;
  place: string;
  date: string;
  qty: string;
  location: string;
  lot: string;
  state: RecordState;
  isGap: boolean;
  openGap: boolean;
}

export function deriveRows(scenario: Scenario, fixed: FixedMap): Row[] {
  const scenarioFixed = isFixed(scenario, fixed);
  return scenario.chain.map((record, index) => {
    const isGap = Boolean(record.gap);
    const openGap = isGap && !scenarioFixed;
    return {
      index,
      cte: record.cte,
      firm: firmName(record.firm),
      place: record.place,
      date: record.date,
      qty: record.kdes.qty,
      location: record.kdes.location,
      lot: openGap ? MISSING_LOT : isGap ? scenario.lot : record.kdes.lot,
      state: recordState(record, scenarioFixed),
      isGap,
      openGap,
    };
  });
}

export interface RowWindow {
  visible: Row[];
  hidden: number;
}

/** The hero shows four rows around the gap unless expanded. */
export function windowRows(rows: Row[], gapIdx: number, expanded: boolean): RowWindow {
  if (expanded) return { visible: rows, hidden: 0 };
  const lo = Math.max(0, Math.min(gapIdx - 2, rows.length - 4));
  const hi = Math.min(rows.length, lo + 4);
  const visible = rows.filter((row) => row.index >= lo && row.index < hi);
  return { visible, hidden: rows.length - visible.length };
}

export interface Detail {
  kind: 'gap' | 'committed' | 'corrected';
  label: string;
  title: string;
  body: string;
  kv: Array<[string, string]>;
  canFix: boolean;
}

export function detailFor(
  scenario: Scenario,
  rowIndex: number | null,
  fixed: FixedMap,
  surface: DemoSurface,
): Detail | null {
  if (rowIndex === null) return null;
  const record = scenario.chain[rowIndex];
  if (!record) return null;
  const scenarioFixed = isFixed(scenario, fixed);
  const firm = firmName(record.firm);

  if (record.gap && !scenarioFixed) {
    const recovery =
      surface === 'landing' ? record.gap.recovery.split(';')[0] : record.gap.recovery;
    const kv: Array<[string, string]> = [
      ['Owner', record.gap.owner],
      ['Recovery', recovery],
      ['Date', record.date],
    ];
    if (surface === 'workspace') kv.push(['Location', record.kdes.location]);
    return {
      kind: 'gap',
      label: `Gap · ${record.cte} · ${firm}`,
      title: `${record.gap.field} (${record.gap.cfr})`,
      body: record.gap.reason,
      kv,
      canFix: true,
    };
  }

  const corrected = Boolean(record.gap);
  const kv: Array<[string, string]> = [
    ['Lot', corrected ? scenario.lot : record.kdes.lot],
    ['Quantity', record.kdes.qty],
    ['Location', record.kdes.location],
    ['Date', record.date],
  ];
  if (surface === 'workspace') kv.push(['Event hash', eventHash(scenario, record)]);
  return {
    kind: corrected ? 'corrected' : 'committed',
    label: `${record.cte} · ${firm}${corrected ? ' · corrected' : ''}`,
    title: record.place,
    body: corrected
      ? `Supplier supplied ${record.gap!.field.toLowerCase()} through the correction link. Re-checked and committed.`
      : 'All Key Data Elements present for this event. Hashed into the ledger against the previous entry.',
    kv,
    canFix: false,
  };
}

export function committedRecords(scenario: Scenario, fixed: FixedMap): ChainRecord[] {
  const scenarioFixed = isFixed(scenario, fixed);
  return scenario.chain.filter((record) => !record.gap || scenarioFixed);
}

export interface HeroStatus {
  committed: number;
  total: number;
  open: number;
  latestHash: string;
  ledgerLine: string;
  exportBadge: string;
  exportLine: string;
  exportReady: boolean;
}

export function heroStatus(scenario: Scenario, fixed: FixedMap): HeroStatus {
  const scenarioFixed = isFixed(scenario, fixed);
  const committed = committedRecords(scenario, fixed);
  const total = scenario.chain.length;
  const open = total - committed.length;
  const gap = gapRecord(scenario);
  const latest = scenarioFixed && gap ? gap : committed[committed.length - 1];
  return {
    committed: committed.length,
    total,
    open,
    latestHash: latest ? eventHash(scenario, latest) : '',
    ledgerLine: `${committed.length} of ${total} records committed`,
    exportBadge: open ? `${committed.length} of ${total} ready` : 'Ready to export',
    exportLine: open
      ? `${open} record still open. Export lists it separately until corrected.`
      : `All ${committed.length} records committed. SHA-256 manifest attached.`,
    exportReady: open === 0,
  };
}

export interface LedgerEntry {
  n: number;
  ts: string;
  scenarioId: string;
  hue: string;
  label: string;
  lot: string;
  eventHash: string;
  chainHash: string;
}

const pad2 = (n: number) => String(n).padStart(2, '0');

/** Every committed record across all chains, hashed against the one before. */
export function deriveLedger(all: readonly Scenario[], fixed: FixedMap): LedgerEntry[] {
  let prev = 'genesis';
  let n = 1040;
  const entries: LedgerEntry[] = [];
  for (const scenario of all) {
    const scenarioFixed = isFixed(scenario, fixed);
    for (const record of scenario.chain) {
      if (record.gap && !scenarioFixed) continue;
      const eh = eventHash(scenario, record);
      const ch = stableHash(prev + eh);
      prev = ch;
      n += 1;
      entries.push({
        n,
        ts: `${record.date}T${pad2(8 + (n % 9))}:${pad2((n * 7) % 60)}:00-07:00`,
        scenarioId: scenario.id,
        hue: scenario.hue,
        label: `${shortLabel(scenario)} · ${record.cte}`,
        lot: record.gap ? scenario.lot : record.kdes.lot,
        eventHash: eh,
        chainHash: ch,
      });
    }
  }
  return entries;
}

export const CSV_HEADER = 'ftl_food,cte,firm,location,date,traceability_lot_code,quantity,state';

const DQ = String.fromCharCode(34);
const csvCell = (value: string) => DQ + value.split(DQ).join(DQ + DQ) + DQ;

/** One FDA-shaped sortable sheet per chain. Open records are marked OPEN, never dropped. */
export function buildCsv(scenario: Scenario, fixed: FixedMap): string {
  const scenarioFixed = isFixed(scenario, fixed);
  const rows = scenario.chain.map((record) => {
    const open = Boolean(record.gap) && !scenarioFixed;
    const lot = open ? '' : record.gap ? scenario.lot : record.kdes.lot;
    return [
      scenario.ftlCategory,
      record.cte,
      firmName(record.firm),
      record.kdes.location,
      record.date,
      lot,
      record.kdes.qty,
      open ? 'OPEN' : 'COMMITTED',
    ]
      .map(csvCell)
      .join(',');
  });
  return [CSV_HEADER, ...rows].join('\n');
}

export function packageFileName(scenario: Pick<Scenario, 'id'>): string {
  return `fda_sortable_${scenario.id}.csv`;
}

export function buildManifest(file: string, hash: string): string {
  return `${file}\tstand-in-hash\t${hash}\nverify: python verify_chain.py ${file}\n`;
}

export interface Package {
  scenarioId: string;
  food: string;
  hue: string;
  file: string;
  ready: boolean;
  badge: string;
  line: string;
  manifest: string;
  csv: string;
}

export function derivePackages(all: readonly Scenario[], fixed: FixedMap): Package[] {
  return all.map((scenario) => {
    const ready = isFixed(scenario, fixed);
    const gap = gapRecord(scenario);
    const total = scenario.chain.length;
    const committed = total - 1;
    const gapCte = gap?.cte ?? 'record';
    const gapField = gap?.gap?.field.toLowerCase() ?? 'field';
    const csv = buildCsv(scenario, fixed);
    return {
      scenarioId: scenario.id,
      food: shortLabel(scenario),
      hue: scenario.hue,
      file: packageFileName(scenario),
      ready,
      badge: ready ? 'READY' : `${committed} OF ${total} READY`,
      line: ready
        ? `${total} records · all committed`
        : `${committed} committed · 1 open (${gapCte}: ${gapField})`,
      manifest: stableHash(csv),
      csv,
    };
  });
}

export interface OverviewStats {
  total: number;
  committed: number;
  open: number;
  ready: number;
  chains: number;
}

export function openScenarioCount(all: readonly Scenario[], fixed: FixedMap): number {
  return all.filter((scenario) => !isFixed(scenario, fixed)).length;
}

export function overviewStats(all: readonly Scenario[], fixed: FixedMap): OverviewStats {
  const total = all.reduce((sum, scenario) => sum + scenario.chain.length, 0);
  const open = openScenarioCount(all, fixed);
  return { total, committed: total - open, open, ready: all.length - open, chains: all.length };
}

export interface AttentionRow {
  scenarioIndex: number;
  scenarioId: string;
  rowIndex: number;
  hue: string;
  item: string;
  owner: string;
  source: string;
}

export function attentionRows(all: readonly Scenario[], fixed: FixedMap): AttentionRow[] {
  const rows: AttentionRow[] = [];
  all.forEach((scenario, scenarioIndex) => {
    if (isFixed(scenario, fixed)) return;
    const index = gapIndex(scenario);
    const record = scenario.chain[index];
    if (!record?.gap) return;
    rows.push({
      scenarioIndex,
      scenarioId: scenario.id,
      rowIndex: index,
      hue: scenario.hue,
      item: `${shortLabel(scenario)} · ${record.cte} at ${firmName(record.firm)}: ${record.gap.field.toLowerCase()}`,
      owner: record.gap.owner,
      source: fileName(scenario),
    });
  });
  return rows;
}

export interface NextAction {
  n: string;
  label: string;
  view: ViewId;
}

export function nextActions(all: readonly Scenario[], fixed: FixedMap): NextAction[] {
  const open = openScenarioCount(all, fixed);
  const ready = all.length - open;
  const actions: Array<Omit<NextAction, 'n'>> = [];
  if (open) {
    actions.push({ label: `Resolve ${open} open ${open === 1 ? 'fix' : 'fixes'} in imported records`, view: 'fix' });
  }
  actions.push({
    label: open
      ? `Export the ${ready} complete ${ready === 1 ? 'package' : 'packages'}`
      : 'Export all five packages',
    view: 'export',
  });
  actions.push({ label: 'Review the evidence ledger', view: 'ledger' });
  return actions.map((action, i) => ({ ...action, n: String(i + 1).padStart(2, '0') }));
}

export interface FixItem {
  scenarioId: string;
  hue: string;
  food: string;
  cte: string;
  firm: string;
  owner: string;
  field: string;
  cfr: string;
  reason: string;
  done: boolean;
}

export function fixQueue(all: readonly Scenario[], fixed: FixedMap): FixItem[] {
  const items: FixItem[] = [];
  for (const scenario of all) {
    const record = gapRecord(scenario);
    if (!record?.gap) continue;
    items.push({
      scenarioId: scenario.id,
      hue: scenario.hue,
      food: shortLabel(scenario),
      cte: record.cte,
      firm: firmName(record.firm),
      owner: record.gap.owner,
      field: record.gap.field,
      cfr: record.gap.cfr,
      reason: record.gap.reason,
      done: isFixed(scenario, fixed),
    });
  }
  return items;
}
