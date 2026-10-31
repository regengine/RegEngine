'use client';

import { Button } from '@/components/ui/button';
import type { Detail, DemoSurface } from '@/lib/demo-workspace/model';
import { cn } from '@/lib/utils';

interface RecordDetailProps {
  detail: Detail;
  surface: DemoSurface;
  onFix: () => void;
  onReset?: () => void;
  className?: string;
}

const LABEL_TONE: Record<Detail['kind'], string> = {
  gap: 'text-re-warning',
  corrected: 'text-re-state-corrected',
  committed: 'text-re-brand',
};

/** The panel under a workbench table once a record is selected. */
export function RecordDetail({ detail, surface, onFix, onReset, className }: RecordDetailProps) {
  const landing = surface === 'landing';
  const owner = detail.kv.find(([key]) => key === 'Owner')?.[1];

  return (
    <div className={cn('grid gap-5 md:grid-cols-[minmax(0,1fr)_auto]', className)}>
      <div className="min-w-0">
        <p className={cn('mb-1.5 font-mono text-label uppercase tracking-[0.1em]', LABEL_TONE[detail.kind])}>
          {detail.label}
        </p>
        <p className={cn('font-semibold text-re-text-primary', landing ? 'text-small' : 'text-subheading')}>
          {detail.title}
        </p>
        <p className={cn('mt-1 text-re-text-tertiary', landing ? 'text-small leading-relaxed' : 'text-ui leading-relaxed')}>
          {detail.body}
        </p>

        {detail.canFix && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <Button type="button" variant="primary" size={landing ? 'sm' : 'md'} onClick={onFix}>
              Send correction link to supplier
            </Button>
            <span className="text-small text-re-text-muted">
              {landing && owner
                ? `Assigns ${owner} · supplier replies through a single-use link`
                : 'Single-use link · supplier answers without an account'}
            </span>
          </div>
        )}

        {detail.kind === 'corrected' && (
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <span className="text-small font-semibold text-re-success">
              {landing
                ? '✓ Supplier corrected the record. Committed to the ledger.'
                : '✓ Corrected by the supplier and committed to the ledger.'}
            </span>
            {onReset && (
              <Button type="button" variant="ghost" size="sm" onClick={onReset}>
                Reset demo
              </Button>
            )}
          </div>
        )}
      </div>

      <dl className="grid grid-cols-[auto_auto] content-start gap-x-4 gap-y-1 font-mono text-small">
        {detail.kv.map(([key, value]) => (
          <div key={key} className="contents">
            <dt className="whitespace-nowrap text-re-text-muted">{key}</dt>
            <dd className="text-re-text-secondary">{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
