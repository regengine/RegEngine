'use client';

import { FoodTabs } from '@/components/demo-workspace/FoodTabs';
import { RecordDetail } from '@/components/demo-workspace/RecordDetail';
import { RecordTable } from '@/components/demo-workspace/RecordTable';
import { WorkbenchHeader } from '@/components/demo-workspace/WorkbenchHeader';
import { Card } from '@/components/ui/card';
import { deriveRows, detailFor, fileName, shortLabel, type FixedMap, type Scenario } from '@/lib/demo-workspace/model';
import { cn } from '@/lib/utils';

interface ImportViewProps {
  all: readonly Scenario[];
  scenario: Scenario;
  selected: number;
  row: number | null;
  fixed: FixedMap;
  onPickScenario: (index: number) => void;
  onPickRow: (index: number) => void;
  onFix: () => void;
}

export function ImportView({ all, scenario, selected, row, fixed, onPickScenario, onPickRow, onFix }: ImportViewProps) {
  const rows = deriveRows(scenario, fixed);
  const detail = detailFor(scenario, row, fixed, 'workspace');

  return (
    <>
      <FoodTabs all={all} selected={selected} onPick={onPickScenario} className="mb-3.5" />
      <Card className="mb-4 overflow-hidden">
        <WorkbenchHeader file={fileName(scenario)} checkLine={`checked ${rows.length} of ${rows.length} records`} />
        <RecordTable
          rows={rows}
          hue={scenario.hue}
          selected={row}
          onPick={onPickRow}
          variant="workspace"
          caption={`${shortLabel(scenario)} supplier records`}
        />
      </Card>
      {detail && (
        <Card className={cn('px-5 py-4', detail.kind === 'gap' && 'border-re-warning-border')}>
          <RecordDetail detail={detail} surface="workspace" onFix={onFix} />
        </Card>
      )}
    </>
  );
}
