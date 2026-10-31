'use client';

import { useCallback, useMemo, useState } from 'react';
import {
  trackResetDemo,
  trackRowClick,
  trackScenarioTab,
  trackSendCorrectionLink,
  trackToggleRows,
} from '@/lib/conversion-events';
import {
  gapRecord,
  scenarios,
  type DemoSurface,
  type FixedMap,
  type Scenario,
} from '@/lib/demo-workspace/model';

export interface DemoWorkspaceState {
  sel: number;
  row: number | null;
  fixed: FixedMap;
  /** True once the visitor has clicked a row; hides the guided caption. */
  touched: boolean;
  /** Hero table shows the whole chain instead of four rows. */
  expanded: boolean;
}

const INITIAL: DemoWorkspaceState = { sel: 0, row: null, fixed: {}, touched: false, expanded: false };

/** Visitor state shared by the landing hero and the public workspace. */
export function useDemoWorkspace(surface: DemoSurface) {
  const all: readonly Scenario[] = useMemo(() => scenarios(), []);
  const [state, setState] = useState<DemoWorkspaceState>(INITIAL);
  const scenario = all[state.sel] ?? all[0];

  const pickScenario = useCallback(
    (index: number) => {
      const next = all[index];
      if (!next) return;
      trackScenarioTab(surface, next.id);
      setState((s) => ({ ...s, sel: index, row: null, expanded: false }));
    },
    [all, surface],
  );

  const pickRow = useCallback(
    (index: number) => {
      const record = scenario.chain[index];
      if (!record) return;
      trackRowClick(surface, scenario.id, record.cte, Boolean(record.gap));
      setState((s) => ({ ...s, row: index, touched: true }));
    },
    [scenario, surface],
  );

  /** Jump to a record in another chain (overview attention table). */
  const openRecord = useCallback((scenarioIndex: number, rowIndex: number) => {
    setState((s) => ({ ...s, sel: scenarioIndex, row: rowIndex, touched: true }));
  }, []);

  const fix = useCallback(
    (scenarioId: string = scenario.id) => {
      const target = all.find((s) => s.id === scenarioId);
      if (!target) return;
      trackSendCorrectionLink(surface, target.id, gapRecord(target)?.cte ?? '');
      setState((s) => ({ ...s, fixed: { ...s.fixed, [target.id]: true } }));
    },
    [all, scenario.id, surface],
  );

  const reset = useCallback(() => {
    trackResetDemo(surface, scenario.id);
    setState((s) => {
      const fixed = { ...s.fixed };
      delete fixed[scenario.id];
      return { ...s, fixed, row: null };
    });
  }, [scenario.id, surface]);

  const resetAll = useCallback(() => {
    trackResetDemo(surface);
    setState((s) => ({ ...s, fixed: {}, row: null }));
  }, [surface]);

  const toggleExpanded = useCallback(() => {
    trackToggleRows(surface, scenario.id);
    setState((s) => ({ ...s, expanded: !s.expanded }));
  }, [scenario.id, surface]);

  return { all, scenario, state, pickScenario, pickRow, openRecord, fix, reset, resetAll, toggleExpanded };
}
