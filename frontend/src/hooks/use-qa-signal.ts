import type { ComplianceState } from '@/components/ui/status-badge';
import { useAuth } from '@/lib/auth-context';
import { useQAHealth } from '@/hooks/use-api';
import type { QAHealthResponse, QAHealthStatus } from '@/types/api';

/**
 * The one reading of QA health that every dashboard surface uses. The QA
 * Health widget and the "Needs attention" panel both call useQASignal(), so
 * they cannot disagree: a failed load is "failed" in both, never "passing",
 * and a missing ready_percent is null ("unknown"), never 0%.
 */
export type QASignalStatus = 'disabled' | 'loading' | 'failed' | QAHealthStatus;

export interface QASignal {
  status: QASignalStatus;
  label: string;
  state: ComplianceState;
  /** True only when the release gate reported "passing". */
  passing: boolean;
  /** Null when the figure is not known — render "unknown", not 0. */
  readyPercent: number | null;
  blockingCount: number | null;
  advisoryCount: number | null;
}

const STATUS_COPY: Record<QAHealthStatus, { label: string; state: ComplianceState }> = {
  passing: { label: 'Release gate passing', state: 'compliant' },
  degraded: { label: 'Advisory issues', state: 'at-risk' },
  unavailable: { label: 'QA signal unavailable', state: 'unknown' },
  invalid_artifact: { label: 'QA artifact invalid', state: 'non-compliant' },
  failing: { label: 'Release gate failing', state: 'non-compliant' },
};

const UNKNOWN = { readyPercent: null, blockingCount: null, advisoryCount: null, passing: false };

export function deriveQASignal(input: {
  enabled: boolean;
  isLoading: boolean;
  error: unknown;
  data: QAHealthResponse | null | undefined;
}): QASignal {
  if (!input.enabled) {
    return { status: 'disabled', label: 'QA signal not available', state: 'unknown', ...UNKNOWN };
  }
  if (input.isLoading) {
    return { status: 'loading', label: 'Checking QA signal', state: 'in-progress', ...UNKNOWN };
  }
  const overall = input.data?.overall;
  if (input.error || !overall) {
    return { status: 'failed', label: 'QA signal failed', state: 'unknown', ...UNKNOWN };
  }
  // An unrecognised status is treated as failing, never as passing.
  const status: QAHealthStatus = overall.status in STATUS_COPY ? overall.status : 'failing';
  const copy = STATUS_COPY[status];
  return {
    status,
    label: copy.label,
    state: copy.state,
    passing: status === 'passing',
    readyPercent: typeof overall.ready_percent === 'number' ? overall.ready_percent : null,
    blockingCount: typeof overall.blocking_count === 'number' ? overall.blocking_count : null,
    advisoryCount: typeof overall.advisory_count === 'number' ? overall.advisory_count : null,
  };
}

/** QA health is sysadmin-only; for everyone else the signal is "disabled". */
export function useQASignal() {
  const { user } = useAuth();
  const enabled = Boolean(user?.is_sysadmin);
  const query = useQAHealth(enabled);
  return {
    ...deriveQASignal({ enabled, isLoading: query.isLoading, error: query.error, data: query.data }),
    refetch: query.refetch,
  };
}
