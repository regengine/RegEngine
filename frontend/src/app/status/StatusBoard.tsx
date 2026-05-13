'use client';

import { useEffect, useState } from 'react';
import { CheckCircle2, AlertTriangle, XCircle, RefreshCw, Circle } from 'lucide-react';

interface ServiceCheck {
  name: string;
  status: 'healthy' | 'unhealthy' | 'unreachable' | 'not_configured';
  code?: number;
  latencyMs?: number;
}

interface HealthPayload {
  status: 'healthy' | 'degraded';
  timestamp: string;
  services: ServiceCheck[];
  summary: { healthy: number; total: number };
}

type FetchState =
  | { kind: 'loading' }
  | { kind: 'ok'; data: HealthPayload; fetchedAt: Date }
  | { kind: 'error'; message: string; fetchedAt: Date };

const REFRESH_INTERVAL_MS = 30_000;

export function StatusBoard() {
  const [state, setState] = useState<FetchState>({ kind: 'loading' });

  async function load() {
    try {
      const res = await fetch('/api/health', { cache: 'no-store' });
      const data = (await res.json()) as HealthPayload;
      setState({ kind: 'ok', data, fetchedAt: new Date() });
    } catch (err) {
      setState({
        kind: 'error',
        message: err instanceof Error ? err.message : 'Failed to fetch /api/health',
        fetchedAt: new Date(),
      });
    }
  }

  useEffect(() => {
    void load();
    const id = setInterval(load, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 shadow-sm">
      <div className="flex items-center justify-between mb-5">
        <OverallBadge state={state} />
        <button
          type="button"
          onClick={() => void load()}
          className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-3 py-1.5 text-xs font-medium text-[var(--re-text-secondary)] hover:border-[var(--re-brand)]/40 transition-colors"
          aria-label="Refresh status"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Refresh
        </button>
      </div>

      {state.kind === 'ok' && (
        <div className="space-y-2">
          {state.data.services.map((svc) => (
            <ServiceRow key={svc.name} svc={svc} />
          ))}
        </div>
      )}

      {state.kind === 'loading' && (
        <div className="text-sm text-[var(--re-text-muted)] py-4">Checking service health…</div>
      )}

      {state.kind === 'error' && (
        <div className="text-sm text-[var(--re-danger)] py-4">
          Could not reach /api/health: {state.message}
        </div>
      )}

      {(state.kind === 'ok' || state.kind === 'error') && (
        <p className="text-xs text-[var(--re-text-disabled)] mt-5 pt-4 border-t border-[var(--re-surface-border)]">
          Last checked {state.fetchedAt.toLocaleString()} · Auto-refreshes every 30 seconds
        </p>
      )}
    </div>
  );
}

function OverallBadge({ state }: { state: FetchState }) {
  if (state.kind === 'loading') {
    return (
      <div className="flex items-center gap-2">
        <Circle className="h-5 w-5 text-[var(--re-text-disabled)]" />
        <span className="font-display text-xl font-semibold text-[var(--re-text-primary)]">
          Checking…
        </span>
      </div>
    );
  }
  if (state.kind === 'error') {
    return (
      <div className="flex items-center gap-2">
        <XCircle className="h-5 w-5 text-[var(--re-danger)]" />
        <span className="font-display text-xl font-semibold text-[var(--re-text-primary)]">
          Status unavailable
        </span>
      </div>
    );
  }
  const healthy = state.data.status === 'healthy';
  return (
    <div className="flex items-center gap-2">
      {healthy ? (
        <CheckCircle2 className="h-5 w-5 text-[var(--re-success)]" />
      ) : (
        <AlertTriangle className="h-5 w-5 text-[var(--re-warning)]" />
      )}
      <span className="font-display text-xl font-semibold text-[var(--re-text-primary)]">
        {healthy ? 'All systems operational' : 'Degraded service'}
      </span>
      <span className="ml-2 text-sm text-[var(--re-text-muted)]">
        {state.data.summary.healthy} / {state.data.summary.total} healthy
      </span>
    </div>
  );
}

function ServiceRow({ svc }: { svc: ServiceCheck }) {
  const tone =
    svc.status === 'healthy'
      ? 'border-l-[var(--re-success)]'
      : svc.status === 'not_configured'
        ? 'border-l-[var(--re-text-disabled)]'
        : 'border-l-[var(--re-danger)]';

  const label =
    svc.status === 'healthy'
      ? 'Operational'
      : svc.status === 'unhealthy'
        ? `Unhealthy${svc.code ? ` (HTTP ${svc.code})` : ''}`
        : svc.status === 'unreachable'
          ? 'Unreachable'
          : 'Not configured';

  return (
    <div
      className={`flex items-center justify-between rounded-lg border border-[var(--re-surface-border)] border-l-4 ${tone} bg-[var(--re-surface-elevated)] px-4 py-3`}
    >
      <div>
        <div className="text-sm font-medium text-[var(--re-text-primary)] capitalize">
          {svc.name}
        </div>
        <div className="text-xs text-[var(--re-text-muted)] mt-0.5">{label}</div>
      </div>
      {svc.latencyMs !== undefined && svc.status !== 'not_configured' && (
        <div className="text-xs font-mono text-[var(--re-text-disabled)]">
          {svc.latencyMs}ms
        </div>
      )}
    </div>
  );
}
