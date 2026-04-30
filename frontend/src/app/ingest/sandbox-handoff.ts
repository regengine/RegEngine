export const SANDBOX_HANDOFF_STORAGE_KEY = 'regengine:sandbox-handoff';

export type SandboxOperationalHandoff = {
  version: 1;
  source: 'free-sandbox' | 'inflow-lab-feeder';
  createdAt: string;
  summary: {
    totalEvents: number;
    passedChecks: number;
    needsWork: number;
    blockers: number;
  };
  csv?: string;
  detectedColumns?: string[];
  diagnosis?: unknown;
  corrections?: unknown;
};

export type SandboxHandoffView = {
  handoff: SandboxOperationalHandoff;
  detectedColumns: string[];
  totalEvents: number;
  passedChecks: number;
  needsWork: number;
  blockerCount: number;
  blockers: string[];
  nextMappingAction: string;
};

type ParseResult =
  | { ok: true; view: SandboxHandoffView }
  | { ok: false; error: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function toNumber(value: unknown, fallback = 0) {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}

function toOptionalNumber(value: unknown) {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function csvColumns(csv?: string) {
  const headerLine = csv?.split(/\r?\n/).find((line) => line.trim().length > 0);
  if (!headerLine) return [];

  return headerLine
    .split(',')
    .map((column) => column.trim().replace(/^"|"$/g, ''))
    .filter(Boolean);
}

function diagnosisBlockers(diagnosis: unknown) {
  if (!isRecord(diagnosis)) return [];

  const blockingReasons = diagnosis.blocking_reasons;
  if (Array.isArray(blockingReasons)) {
    return blockingReasons.filter((reason): reason is string => typeof reason === 'string' && reason.trim().length > 0);
  }

  return [];
}

function diagnosisEventCounts(diagnosis: unknown) {
  if (!isRecord(diagnosis)) return {};

  return {
    totalEvents: toOptionalNumber(diagnosis.total_events),
    passedEvents: toOptionalNumber(diagnosis.compliant_events),
    needsWorkEvents: toOptionalNumber(diagnosis.non_compliant_events),
  };
}

function nextMappingAction(handoff: SandboxOperationalHandoff, detectedColumns: string[], blockers: string[]) {
  if (handoff.summary.blockers > 0 || blockers.length > 0) {
    return 'Resolve sandbox blockers before creating a production import mapping.';
  }

  if (detectedColumns.length === 0) {
    return 'Add or confirm source headers, then map each column to a RegEngine field.';
  }

  if (handoff.summary.needsWork > 0) {
    return 'Review suggested corrections, then map detected source columns to canonical fields.';
  }

  return 'Map detected columns to canonical fields and save this as a test-run source mapping.';
}

export function parseSandboxHandoff(raw: string | null): ParseResult {
  if (!raw) {
    return { ok: false, error: 'No sandbox handoff was found in this browser session.' };
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { ok: false, error: 'The sandbox handoff could not be read. Return to the sandbox and save the test run again.' };
  }

  if (!isRecord(parsed) || parsed.version !== 1 || !isRecord(parsed.summary)) {
    return { ok: false, error: 'The sandbox handoff uses an unsupported format.' };
  }

  if (parsed.source !== 'free-sandbox' && parsed.source !== 'inflow-lab-feeder') {
    return { ok: false, error: 'The sandbox handoff source is not recognized.' };
  }

  const summary = parsed.summary;
  const handoff: SandboxOperationalHandoff = {
    version: 1,
    source: parsed.source,
    createdAt: typeof parsed.createdAt === 'string' ? parsed.createdAt : '',
    summary: {
      totalEvents: toNumber(summary.totalEvents),
      passedChecks: toNumber(summary.passedChecks),
      needsWork: toNumber(summary.needsWork),
      blockers: toNumber(summary.blockers),
    },
    csv: typeof parsed.csv === 'string' ? parsed.csv : undefined,
    detectedColumns: Array.isArray(parsed.detectedColumns)
      ? parsed.detectedColumns.filter((column): column is string => typeof column === 'string' && column.trim().length > 0)
      : undefined,
    diagnosis: parsed.diagnosis,
    corrections: parsed.corrections,
  };

  const detectedColumns = handoff.detectedColumns?.length ? handoff.detectedColumns : csvColumns(handoff.csv);
  const diagnosisCounts = diagnosisEventCounts(handoff.diagnosis);
  const blockers = diagnosisBlockers(handoff.diagnosis);
  const blockerCount = Math.max(handoff.summary.blockers, blockers.length);
  const totalEvents = diagnosisCounts.totalEvents ?? handoff.summary.totalEvents;
  const needsWork = diagnosisCounts.needsWorkEvents ?? handoff.summary.needsWork;
  const passedChecks = diagnosisCounts.passedEvents ?? handoff.summary.passedChecks;

  return {
    ok: true,
    view: {
      handoff,
      detectedColumns,
      totalEvents,
      passedChecks,
      needsWork,
      blockerCount,
      blockers,
      nextMappingAction: nextMappingAction(handoff, detectedColumns, blockers),
    },
  };
}

export function readSandboxHandoffFromSession(): ParseResult {
  if (typeof window === 'undefined') {
    return { ok: false, error: 'Sandbox handoff is only available in the browser session.' };
  }

  return parseSandboxHandoff(window.sessionStorage.getItem(SANDBOX_HANDOFF_STORAGE_KEY));
}
