export const SANDBOX_HANDOFF_STORAGE_KEY = 'regengine:sandbox-handoff';

type SandboxRuleResult = {
  result: string;
};

type SandboxEventEvaluation = {
  rules_passed: number;
  blocking_defects?: unknown[];
  all_results?: SandboxRuleResult[];
};

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

type SandboxHandoffResult = {
  total_events: number;
  non_compliant_events: number;
  total_rule_failures: number;
  blocking_reasons: string[];
  events: SandboxEventEvaluation[];
};

function parseCsvHeader(csv: string) {
  const headerLine = csv.split(/\r?\n/, 1)[0] ?? '';
  const columns: string[] = [];
  let current = '';
  let inQuotes = false;

  for (let index = 0; index < headerLine.length; index += 1) {
    const char = headerLine[index];
    const next = headerLine[index + 1];

    if (char === '"' && next === '"') {
      current += '"';
      index += 1;
    } else if (char === '"') {
      inQuotes = !inQuotes;
    } else if (char === ',' && !inQuotes) {
      columns.push(current.trim().replace(/^\uFEFF/, ''));
      current = '';
    } else {
      current += char;
    }
  }

  columns.push(current.trim());
  return columns.filter(Boolean);
}

function countPassedChecks(result: SandboxHandoffResult) {
  const eventPassedChecks = result.events.reduce((total, event) => total + (event.rules_passed || 0), 0);
  if (eventPassedChecks > 0) return eventPassedChecks;

  return result.events.reduce(
    (total, event) => total + (event.all_results || []).filter((rule) => rule.result === 'pass').length,
    0,
  );
}

function countBlockers(result: SandboxHandoffResult) {
  const eventBlockers = result.events.reduce((total, event) => total + (event.blocking_defects?.length || 0), 0);
  return Math.max(result.blocking_reasons.length, eventBlockers);
}

export function buildSandboxOperationalHandoff({
  csv,
  result,
  diagnosis,
  corrections,
  createdAt = new Date().toISOString(),
}: {
  csv: string;
  result: SandboxHandoffResult;
  diagnosis?: unknown;
  corrections?: unknown;
  createdAt?: string;
}): SandboxOperationalHandoff {
  return {
    version: 1,
    source: 'free-sandbox',
    createdAt,
    summary: {
      totalEvents: result.total_events,
      passedChecks: countPassedChecks(result),
      needsWork: result.non_compliant_events,
      blockers: countBlockers(result),
    },
    csv,
    detectedColumns: parseCsvHeader(csv),
    diagnosis,
    corrections,
  };
}

export function saveSandboxOperationalHandoff(handoff: SandboxOperationalHandoff, storage: Storage = window.sessionStorage) {
  storage.setItem(SANDBOX_HANDOFF_STORAGE_KEY, JSON.stringify(handoff));
}
