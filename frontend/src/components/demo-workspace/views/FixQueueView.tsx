'use client';

import { HueDot } from '@/components/demo-workspace/HueDot';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { StatusBadge } from '@/components/ui/status-badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { FixItem } from '@/lib/demo-workspace/model';

const HEAD = 'h-10 bg-transparent font-mono text-label uppercase tracking-[0.08em] text-re-text-muted';

export function FixQueueView({ items, onFix }: { items: FixItem[]; onFix: (scenarioId: string) => void }) {
  return (
    <Card>
      <Table>
        <caption className="sr-only">Fix queue</caption>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead className={HEAD}>Status</TableHead>
            <TableHead className={HEAD}>Action</TableHead>
            <TableHead className={HEAD}>Food · CTE · firm · owner</TableHead>
            <TableHead className={HEAD}>Missing field · rule</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.scenarioId} className="hover:bg-transparent">
              <TableCell className="whitespace-nowrap align-top">
                <StatusBadge state={item.done ? 'corrected' : 'needs-correction'} size="sm" />
              </TableCell>
              <TableCell className="whitespace-nowrap align-top">
                {item.done ? (
                  <span className="text-small font-semibold text-re-success">✓ Committed</span>
                ) : (
                  <Button type="button" variant="primary" size="sm" onClick={() => onFix(item.scenarioId)}>
                    Send correction link
                  </Button>
                )}
              </TableCell>
              <TableCell className="min-w-[180px] align-top text-re-text-secondary">
                <span className="inline-flex items-center gap-2">
                  <HueDot hue={item.hue} />
                  {item.food} · {item.cte}
                </span>
                <span className="block pl-4 text-small text-re-text-muted">
                  {item.firm} · owner {item.owner}
                </span>
              </TableCell>
              <TableCell className="min-w-[240px] align-top">
                <p className="font-semibold text-re-text-primary">
                  {item.field} <span className="font-mono text-small font-normal text-re-text-muted">{item.cfr}</span>
                </p>
                <p className="text-small leading-relaxed text-re-text-tertiary">{item.reason}</p>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Card>
  );
}
