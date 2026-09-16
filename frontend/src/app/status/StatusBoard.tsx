'use client';

import { useEffect, useState } from 'react';
import { RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { StatusBadge, type ComplianceState } from '@/components/ui/status-badge';

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

  // Mount-time fetch plus a refresh interval. Writing the response into state
  // is the whole purpose of the effect; there is no render-time equivalent for
  // a network result.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void load();
    const id = setInterval(load, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <Card padding="spacious">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <OverallBadge state={state} />
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => void load()}
          aria-label="Refresh status"
          leadingIcon={<RefreshCw className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />}
        >
          Refresh
        </Button>
      </div>

      {state.kind === 'ok' && (
        <div className="space-y-2">
          {state.data.services.map((svc) => (
            <ServiceRow key={svc.name} svc={svc} />
          ))}
        </div>
      )}

      {state.kind === 'loading' && (
        <div className="space-y-2" aria-busy="true">
          <p className="py-1 text-ui text-re-text-tertiary">Checking service health…</p>
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      )}

      {state.kind === 'error' && (
        <Callout tone="danger" role="alert">
          Could not reach /api/health: {state.message}
        </Callout>
      )}

      {(state.kind === 'ok' || state.kind === 'error') && (
        <p className="mt-5 border-t border-re-border-subtle pt-4 font-mono text-label text-re-text-muted">
          Last checked {state.fetchedAt.toLocaleString()} · Auto-refreshes every 30 seconds
        </p>
      )}
    </Card>
  );
}

function OverallBadge({ state }: { state: FetchState }) {
  if (state.kind === 'loading') {
    return <StatusBadge state="pending" label="Checking…" />;
  }
  if (state.kind === 'error') {
    return <StatusBadge state="non-compliant" label="Status unavailable" />;
  }
  const healthy = state.data.status === 'healthy';
  return (
    <div className="flex flex-wrap items-center gap-2">
      <StatusBadge
        state={healthy ? 'compliant' : 'at-risk'}
        label={healthy ? 'All systems operational' : 'Degraded service'}
      />
      <span className="text-ui text-re-text-tertiary">
        {state.data.summary.healthy} / {state.data.summary.total} healthy
      </span>
    </div>
  );
}

const SERVICE_STATE: Record<ServiceCheck['status'], ComplianceState> = {
  healthy: 'compliant',
  unhealthy: 'non-compliant',
  unreachable: 'non-compliant',
  not_configured: 'unknown',
};

function ServiceRow({ svc }: { svc: ServiceCheck }) {
  const label =
    svc.status === 'healthy'
      ? 'Operational'
      : svc.status === 'unhealthy'
        ? `Unhealthy${svc.code ? ` (HTTP ${svc.code})` : ''}`
        : svc.status === 'unreachable'
          ? 'Unreachable'
          : 'Not configured';

  return (
    <Card
      variant="inset"
      padding="compact"
      className="flex flex-wrap items-center justify-between gap-3"
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-subheading capitalize text-re-text-primary">{svc.name}</span>
        <StatusBadge state={SERVICE_STATE[svc.status]} label={label} size="sm" />
      </div>
      {svc.latencyMs !== undefined && svc.status !== 'not_configured' && (
        <span className="font-mono text-[0.8125rem] tabular-nums text-re-text-tertiary">
          {svc.latencyMs}ms
        </span>
      )}
    </Card>
  );
}
