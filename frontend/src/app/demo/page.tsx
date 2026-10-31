'use client';

import { useCallback, useSyncExternalStore } from 'react';
import { DemoShell } from '@/components/demo-workspace/DemoShell';
import { useDemoWorkspace } from '@/components/demo-workspace/useDemoWorkspace';
import { ExportView } from '@/components/demo-workspace/views/ExportView';
import { FixQueueView } from '@/components/demo-workspace/views/FixQueueView';
import { ImportView } from '@/components/demo-workspace/views/ImportView';
import { LedgerView } from '@/components/demo-workspace/views/LedgerView';
import { OverviewView } from '@/components/demo-workspace/views/OverviewView';
import {
  attentionRows,
  deriveLedger,
  derivePackages,
  fixQueue,
  nextActions,
  openScenarioCount,
  overviewStats,
  parseView,
  type ViewId,
} from '@/lib/demo-workspace/model';

const TITLES: Record<ViewId, [string, string]> = {
  overview: [
    'Overview',
    'Where the records stand, what is wrong, and what to do next. Everything here is driven by five imported supplier files.',
  ],
  import: [
    'Import · Inflow workbench',
    'Each supplier file, record by record, checked against the Key Data Elements its event type requires. Click a record.',
  ],
  fix: [
    'Fix queue',
    'Every gap with a reason, a rule, an owner and a recovery path. Sending the correction link lets the supplier answer without an account.',
  ],
  ledger: ['Evidence ledger', 'Accepted records, hashed against the one before them. Nothing is edited in place; corrections append.'],
  export: ['Export packages', 'One FDA-shaped sortable spreadsheet per chain, with a SHA-256 manifest you can verify yourself.'],
};

function subscribeHash(onChange: () => void) {
  window.addEventListener('hashchange', onChange);
  return () => window.removeEventListener('hashchange', onChange);
}

const readHash = () => parseView(window.location.hash);
const serverView = (): ViewId => 'overview';

export default function DemoWorkspacePage() {
  const view = useSyncExternalStore(subscribeHash, readHash, serverView);
  const ws = useDemoWorkspace('workspace');
  const { all, scenario, state } = ws;

  const go = useCallback((next: ViewId) => {
    try {
      window.history.replaceState(null, '', `#${next}`);
    } catch {
      // Navigation state is cosmetic; the view still changes below.
    }
    window.dispatchEvent(new Event('hashchange'));
  }, []);

  const openRecord = useCallback(
    (scenarioIndex: number, rowIndex: number) => {
      ws.openRecord(scenarioIndex, rowIndex);
      go('import');
    },
    [go, ws],
  );

  const [title, subtitle] = TITLES[view];

  return (
    <div className="re-display-outfit min-h-screen bg-re-surface-base text-re-text-primary">
      <DemoShell
        view={view}
        onNavigate={go}
        openCount={openScenarioCount(all, state.fixed)}
        title={title}
        subtitle={subtitle}
        legend={all}
        onResetAll={ws.resetAll}
      >
        {view === 'overview' && (
          <OverviewView
            stats={overviewStats(all, state.fixed)}
            attention={attentionRows(all, state.fixed)}
            actions={nextActions(all, state.fixed)}
            onOpenRecord={openRecord}
            onNavigate={go}
          />
        )}
        {view === 'import' && (
          <ImportView
            all={all}
            scenario={scenario}
            selected={state.sel}
            row={state.row}
            fixed={state.fixed}
            onPickScenario={ws.pickScenario}
            onPickRow={ws.pickRow}
            onFix={() => ws.fix()}
          />
        )}
        {view === 'fix' && <FixQueueView items={fixQueue(all, state.fixed)} onFix={ws.fix} />}
        {view === 'ledger' && <LedgerView entries={deriveLedger(all, state.fixed)} />}
        {view === 'export' && <ExportView packages={derivePackages(all, state.fixed)} />}
      </DemoShell>
    </div>
  );
}
