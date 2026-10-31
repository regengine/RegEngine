'use client';

import type { KeyboardEvent } from 'react';
import { StatusBadge } from '@/components/ui/status-badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import type { Row } from '@/lib/demo-workspace/model';
import { cn } from '@/lib/utils';
import { HueDot } from './HueDot';

interface RecordTableProps {
  rows: Row[];
  hue: string;
  selected: number | null;
  onPick: (index: number) => void;
  /** `hero` is the three-column landing mock; `workspace` is the four-column import view. */
  variant: 'hero' | 'workspace';
  caption: string;
}

const HEAD = 'h-9 bg-transparent font-mono text-label uppercase tracking-[0.08em] text-re-text-muted';

export function RecordTable({ rows, hue, selected, onPick, variant, caption }: RecordTableProps) {
  const hero = variant === 'hero';

  const onKeyDown = (event: KeyboardEvent<HTMLTableRowElement>, index: number) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onPick(index);
  };

  return (
    <Table className={cn(hero ? 'text-[0.8125rem]' : 'text-ui')}>
      <caption className="sr-only">{caption}</caption>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead className={HEAD}>{hero ? 'CTE · firm' : 'CTE'}</TableHead>
          {!hero && <TableHead className={HEAD}>Firm</TableHead>}
          <TableHead className={HEAD}>Traceability lot code</TableHead>
          <TableHead className={HEAD}>State</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((row) => {
          const isSelected = selected === row.index;
          return (
            <TableRow
              key={row.index}
              tabIndex={0}
              aria-selected={isSelected}
              data-state={isSelected ? 'selected' : undefined}
              data-gap={row.openGap ? 'open' : undefined}
              onClick={() => onPick(row.index)}
              onKeyDown={(event) => onKeyDown(event, row.index)}
              className={cn(
                'cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-re-focus-ring',
                row.openGap && 'bg-re-warning-bg/40',
                isSelected && 'ring-1 ring-inset ring-re-brand data-[state=selected]:bg-transparent',
              )}
            >
              <TableCell
                className={cn(
                  'whitespace-nowrap border-l-2',
                  row.openGap ? 'border-l-re-warning' : 'border-l-transparent',
                )}
              >
                <span className="flex items-center gap-2">
                  <HueDot hue={hue} />
                  <span>{row.cte}</span>
                </span>
                {hero && (
                  <span className="block max-w-[170px] truncate pl-4 text-small font-normal text-re-text-muted">
                    {row.firm}
                  </span>
                )}
              </TableCell>
              {!hero && (
                <TableCell>
                  {row.firm}
                  <span className="block text-small text-re-text-muted">
                    {row.place} · <span className="font-mono">{row.date}</span>
                  </span>
                </TableCell>
              )}
              <TableCell
                className={cn(
                  'whitespace-nowrap font-mono text-small',
                  row.openGap ? 'text-re-warning' : 'text-re-text-primary',
                )}
              >
                {row.lot}
              </TableCell>
              <TableCell className="whitespace-nowrap">
                <StatusBadge state={row.state} size="sm" />
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
