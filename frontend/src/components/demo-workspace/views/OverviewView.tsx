'use client';

import { HueDot } from '@/components/demo-workspace/HueDot';
import { Card } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/status-badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { AttentionRow, NextAction, OverviewStats, ViewId } from '@/lib/demo-workspace/model';
import { cn } from '@/lib/utils';

interface OverviewViewProps {
  stats: OverviewStats;
  attention: AttentionRow[];
  actions: NextAction[];
  onOpenRecord: (scenarioIndex: number, rowIndex: number) => void;
  onNavigate: (view: ViewId) => void;
}

const HEAD = 'h-10 bg-transparent font-mono text-label uppercase tracking-[0.08em] text-re-text-muted';

export function OverviewView({ stats, attention, actions, onOpenRecord, onNavigate }: OverviewViewProps) {
  const tiles = [
    { label: 'Records imported', value: String(stats.total), note: `${stats.chains} supplier files · 5 FTL foods`, tone: 'text-re-text-primary' },
    { label: 'Committed to ledger', value: String(stats.committed), note: 'hash-chained, clears on reset', tone: 'text-re-success' },
    { label: 'Open fixes', value: String(stats.open), note: stats.open ? 'each has an owner' : 'queue is clear', tone: stats.open ? 'text-re-warning' : 'text-re-success' },
    { label: 'Packages ready', value: `${stats.ready} / ${stats.chains}`, note: 'FDA-shaped CSV + manifest', tone: 'text-re-brand' },
  ];

  return (
    <>
      <div className="mb-6 grid grid-cols-[repeat(auto-fit,minmax(140px,1fr))] gap-3.5">
        {tiles.map((tile) => (
          <Card key={tile.label} className="px-4 py-4">
            <p className="mb-2.5 font-mono text-label uppercase tracking-[0.1em] text-re-text-muted">{tile.label}</p>
            <p className={cn('font-display text-title leading-none tabular-nums', tile.tone)}>{tile.value}</p>
            <p className="mt-2 text-small text-re-text-tertiary">{tile.note}</p>
          </Card>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-[repeat(auto-fit,minmax(320px,1fr))]">
        <section className="min-w-0 lg:col-span-full">
          <h2 className="mb-2.5 font-display text-heading text-re-text-primary">Records that need attention</h2>
          <Card>
            {attention.length > 0 ? (
              <Table>
                <caption className="sr-only">Records that need attention</caption>
                <TableHeader>
                  <TableRow className="hover:bg-transparent">
                    <TableHead className={HEAD}>Status</TableHead>
                    <TableHead className={HEAD}>Item</TableHead>
                    <TableHead className={HEAD}>Owner</TableHead>
                    <TableHead className={HEAD}>Source</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {attention.map((row) => (
                    <TableRow
                      key={row.scenarioId}
                      onClick={() => onOpenRecord(row.scenarioIndex, row.rowIndex)}
                      className="cursor-pointer"
                    >
                      <TableCell className="whitespace-nowrap">
                        <StatusBadge state="needs-correction" size="sm" />
                      </TableCell>
                      <TableCell className="text-re-text-secondary">
                        {/* The click bubbles to the row's handler; a native button gives keyboard and screen-reader access. */}
                        <button
                          type="button"
                          className="inline-flex items-center gap-2 rounded-sm text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring"
                        >
                          <HueDot hue={row.hue} />
                          {row.item}
                        </button>
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-re-text-tertiary">{row.owner}</TableCell>
                      <TableCell className="whitespace-nowrap font-mono text-small text-re-text-muted">{row.source}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            ) : (
              <p className="px-6 py-7 text-center text-ui text-re-text-tertiary">
                ✓ Nothing needs attention. Every imported record is committed.
              </p>
            )}
          </Card>
        </section>

        <section className="min-w-0">
          <h2 className="mb-2.5 font-display text-heading text-re-text-primary">Next actions</h2>
          <Card>
            <ol>
              {actions.map((action) => (
                <li key={action.n} className="border-b border-re-border-subtle last:border-0">
                  <button
                    type="button"
                    onClick={() => onNavigate(action.view)}
                    className="flex w-full items-start gap-3 px-4 py-3 text-left text-ui text-re-text-secondary transition-colors duration-120 hover:text-re-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-re-focus-ring motion-reduce:transition-none"
                  >
                    <span className="mt-0.5 font-mono text-small text-re-text-muted">{action.n}</span>
                    <span className="flex-1">{action.label}</span>
                    <span aria-hidden="true" className="text-re-brand">→</span>
                  </button>
                </li>
              ))}
            </ol>
          </Card>
        </section>
      </div>
    </>
  );
}
