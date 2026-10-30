'use client';

import Link from 'next/link';
import { FoodTabs } from '@/components/demo-workspace/FoodTabs';
import { LiveDot } from '@/components/demo-workspace/HueDot';
import { RecordDetail } from '@/components/demo-workspace/RecordDetail';
import { RecordTable } from '@/components/demo-workspace/RecordTable';
import { StatusStrip } from '@/components/demo-workspace/StatusStrip';
import { WorkbenchHeader } from '@/components/demo-workspace/WorkbenchHeader';
import { useDemoWorkspace } from '@/components/demo-workspace/useDemoWorkspace';
import { Card } from '@/components/ui/card';
import {
  deriveRows,
  detailFor,
  fileName,
  gapIndex,
  heroStatus,
  isFixed,
  shortLabel,
  windowRows,
} from '@/lib/demo-workspace/model';

/**
 * The interactive Inflow Workbench mock in the landing hero. Runs on the same
 * static dataset and derivations as /demo; one record per chain is missing a
 * field and the visitor can "send the correction link" to watch it commit.
 */
export function HeroWorkbench() {
  const { all, scenario, state, pickScenario, pickRow, fix, reset, toggleExpanded } = useDemoWorkspace('landing');
  const rows = deriveRows(scenario, state.fixed);
  const gapIdx = gapIndex(scenario);
  const { visible, hidden } = windowRows(rows, gapIdx, state.expanded);
  const detail = detailFor(scenario, state.row, state.fixed, 'landing');
  const status = heroStatus(scenario, state.fixed);
  const fixed = isFixed(scenario, state.fixed);
  const showHint = !fixed && !state.touched;

  return (
    <div className="flex min-w-0 flex-col gap-2.5">
      <Card className="overflow-hidden rounded-xl">
        <WorkbenchHeader file={fileName(scenario)} checkLine={`checked ${rows.length} of ${rows.length}`} />

        <FoodTabs all={all} selected={state.sel} onPick={pickScenario} size="sm" className="border-b border-re-border-subtle px-3 py-2.5" />

        {showHint && (
          <p className="flex items-center gap-2 border-b border-re-border-subtle px-3 py-2 text-small font-semibold text-re-brand">
            <LiveDot />
            One record is missing a required field. Click it to see what and who fixes it.
          </p>
        )}

        <RecordTable
          rows={visible}
          hue={scenario.hue}
          selected={state.row}
          onPick={pickRow}
          variant="hero"
          caption={`${shortLabel(scenario)} supplier records`}
        />

        {(hidden > 0 || state.expanded) && (
          <button
            type="button"
            onClick={toggleExpanded}
            className="block w-full border-b border-re-border-subtle px-3 py-2 text-left text-small text-re-text-muted transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-re-focus-ring motion-reduce:transition-none"
          >
            {state.expanded ? 'Show fewer records' : `Show ${hidden} more record${hidden === 1 ? '' : 's'} in this chain`}
          </button>
        )}

        {detail && (
          <div className="border-b border-re-border-subtle bg-re-surface-base px-4 py-3.5">
            <RecordDetail detail={detail} surface="landing" onFix={() => fix()} onReset={reset} />
          </div>
        )}

        <StatusStrip status={status} />
      </Card>

      <p className="text-small leading-relaxed text-re-text-muted">
        Synthetic data modelled on FDA major recall notices; firms, lots and gaps are invented.{' '}
        <Link href="/demo" className="font-semibold text-re-brand no-underline hover:underline">
          Open the full demo workspace →
        </Link>{' '}
        No account needed. CSV upload and the JSON events API are live today; the workbench view ships next.
      </p>
    </div>
  );
}
