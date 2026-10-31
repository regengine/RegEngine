import { Badge } from '@/components/ui/badge';
import type { HeroStatus } from '@/lib/demo-workspace/model';
import { cn } from '@/lib/utils';

/** Ledger and export cells under the hero workbench table. */
export function StatusStrip({ status }: { status: HeroStatus }) {
  return (
    <div className="grid grid-cols-[repeat(auto-fit,minmax(220px,1fr))]">
      <div className="border-r border-re-border-subtle px-4 py-3">
        <p className="mb-1.5 font-mono text-label uppercase tracking-[0.1em] text-re-text-muted">
          Evidence ledger · append-only
        </p>
        <p className="text-[0.8125rem] font-semibold text-re-text-primary">{status.ledgerLine}</p>
        <p className="truncate font-mono text-small text-re-text-muted">latest {status.latestHash}</p>
      </div>
      <div
        className={cn(
          'px-4 py-3 transition-colors duration-240 motion-reduce:transition-none',
          status.exportReady && 'bg-re-success-bg/60',
        )}
      >
        <div className="mb-1.5 flex items-center justify-between gap-2">
          <span className="font-mono text-label uppercase tracking-[0.1em] text-re-text-muted">Export package</span>
          <Badge tone={status.exportReady ? 'success' : 'warning'} size="sm">
            {status.exportBadge}
          </Badge>
        </div>
        <p className="font-mono text-small font-semibold text-re-text-primary">fda_sortable_export.csv</p>
        <p className="text-small leading-snug text-re-text-tertiary">{status.exportLine}</p>
      </div>
    </div>
  );
}
