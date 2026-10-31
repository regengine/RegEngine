'use client';

import { HueDot } from '@/components/demo-workspace/HueDot';
import { Card } from '@/components/ui/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { LedgerEntry } from '@/lib/demo-workspace/model';

const HEAD = 'h-10 bg-transparent font-mono text-label uppercase tracking-[0.08em] text-re-text-muted';

export function LedgerView({ entries }: { entries: LedgerEntry[] }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap justify-between gap-3 border-b border-re-border-subtle bg-re-surface-elevated px-4 py-2.5">
        <span className="font-mono text-label uppercase tracking-[0.1em] text-re-text-tertiary">
          Evidence ledger · append-only · chain_hash = SHA-256(previous ‖ event)
        </span>
        <span className="font-mono text-label text-re-brand">{entries.length} entries · chain verified</span>
      </div>
      <Table className="text-[0.8125rem]">
        <caption className="sr-only">Evidence ledger entries</caption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className={HEAD}>Committed</TableHead>
            <TableHead className={HEAD}>Food · CTE</TableHead>
            <TableHead className={HEAD}>Traceability lot code</TableHead>
            <TableHead className={HEAD}>Chain hash</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {entries.map((entry) => (
            <TableRow key={entry.n} className="hover:bg-transparent">
              <TableCell className="whitespace-nowrap font-mono text-small font-normal text-re-text-secondary">{entry.ts}</TableCell>
              <TableCell className="whitespace-nowrap text-re-text-secondary">
                <span className="inline-flex items-center gap-2">
                  <HueDot hue={entry.hue} />
                  {entry.label}
                </span>
              </TableCell>
              <TableCell className="whitespace-nowrap font-mono text-small">{entry.lot}</TableCell>
              <TableCell className="whitespace-nowrap font-mono text-small text-re-brand">{entry.chainHash}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
