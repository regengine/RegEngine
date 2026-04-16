'use client';

import { useState, useRef, useCallback, useEffect, useMemo } from 'react';
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from '@tanstack/react-table';
import { usePostHog } from 'posthog-js/react';
import { useGridHistory } from './use-grid-history';
import { buildCellErrorMap } from './cell-error-map';
import { FixItTooltip } from './FixItTooltip';
import { MassFillDialog } from './MassFillDialog';
import { AddEventModal } from './AddEventModal';
import { GridToolbar } from './GridToolbar';
import { generateComplianceReport } from './SandboxPdfReport';
import { TracePanel } from './TracePanel';
import { SandboxResultsCTA } from './SandboxResultsCTA';
import { ExportLeadGate } from './ExportLeadGate';
import { cellKey } from './types';
import type { CellErrorMap, CellFixedSet } from './types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SandboxResult {
  total_events: number;
  compliant_events: number;
  non_compliant_events: number;
  total_kde_errors: number;
  total_rule_failures: number;
  submission_blocked: boolean;
  blocking_reasons: string[];
  events: {
    event_index: number;
    cte_type: string;
    traceability_lot_code: string;
    product_description: string;
    kde_errors: string[];
    rules_evaluated: number;
    rules_passed: number;
    rules_failed: number;
    rules_warned: number;
    compliant: boolean;
    blocking_defects: {
      rule_title: string;
      severity: string;
      result: string;
      why_failed: string | null;
      citation: string | null;
      remediation: string | null;
      category: string;
      evidence?: Record<string, unknown>[] | null;
    }[];
    all_results: {
      rule_title: string;
      severity: string;
      result: string;
      why_failed: string | null;
      citation: string | null;
      remediation: string | null;
      category: string;
      evidence?: Record<string, unknown>[] | null;
    }[];
  }[];
  duplicate_warnings?: string[];
  entity_warnings?: string[];
}

interface SandboxGridProps {
  initialCsv: string;
  initialResult: SandboxResult;
  onBack: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function parseCsvToGrid(csv: string): { headers: string[]; rows: string[][] } {
  const lines = csv.trim().split('\n');
  if (lines.length < 1) return { headers: [], rows: [] };

  const headers = lines[0].split(',').map((h) => h.trim());
  const rows: string[][] = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;

    // Simple CSV parse — handle quoted fields
    const cells: string[] = [];
    let current = '';
    let inQuotes = false;
    for (let j = 0; j < line.length; j++) {
      const ch = line[j];
      if (ch === '"') {
        inQuotes = !inQuotes;
      } else if (ch === ',' && !inQuotes) {
        cells.push(current.trim());
        current = '';
      } else {
        current += ch;
      }
    }
    cells.push(current.trim());

    // Pad or truncate to match header length
    while (cells.length < headers.length) cells.push('');
    rows.push(cells.slice(0, headers.length));
  }

  return { headers, rows };
}

function gridToCsv(headers: string[], rows: string[][]): string {
  const headerLine = headers.join(',');
  const dataLines = rows.map((row) =>
    row.map((cell) => (cell.includes(',') ? `"${cell}"` : cell)).join(',')
  );
  return [headerLine, ...dataLines].join('\n');
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SandboxGrid({ initialCsv, initialResult, onBack }: SandboxGridProps) {
  // Parse CSV into headers + 2D data
  const { headers, rows: initialRows } = useMemo(() => parseCsvToGrid(initialCsv), [initialCsv]);

  // Grid data with undo/redo
  const history = useGridHistory(initialRows);

  // Evaluation state
  const [result, setResult] = useState<SandboxResult>(initialResult);
  const [isEvaluating, setIsEvaluating] = useState(false);
  const [rateLimitMsg, setRateLimitMsg] = useState<string | null>(null);

  // Editing state
  const [editingCell, setEditingCell] = useState<{ row: number; col: number } | null>(null);
  const [editValue, setEditValue] = useState('');
  const editInputRef = useRef<HTMLInputElement>(null);

  // Track which cells the user has edited (for green highlighting)
  const [fixedCells, setFixedCells] = useState<CellFixedSet>(new Set());

  // Mass fill dialog
  const [massFillOpen, setMassFillOpen] = useState(false);

  // Trace panel
  const [showTrace, setShowTrace] = useState(false);

  // Lead gate for export
  const [leadGateOpen, setLeadGateOpen] = useState(false);
  const pendingExportRef = useRef<(() => void) | null>(null);

  // PostHog tracking
  const posthog = usePostHog();
  const hasTrackedFirstEdit = useRef(false);
  const hasTrackedAllClear = useRef(false);

  function trackSandbox(event: string, metadata: Record<string, unknown> = {}) {
    posthog.capture(`SANDBOX_${event}`, {
      ...metadata,
      timestamp: new Date().toISOString(),
    });
  }

  // Add event modal (guided resolution)
  const [addEventModal, setAddEventModal] = useState<{
    open: boolean;
    cteType: string;
    prefill: Record<string, string>;
  } | null>(null);

  // Debounce re-evaluation + abort stale requests
  const debounceRef = useRef<NodeJS.Timeout>();
  const abortRef = useRef<AbortController | null>(null);
  const evalGenRef = useRef(0); // generation counter to discard stale responses

  // Build cell error map from current evaluation result
  const cellErrors: CellErrorMap = useMemo(
    () => buildCellErrorMap(result.events, headers),
    [result, headers],
  );

  // Count defects
  const criticalDefects = useMemo(() => {
    let count = 0;
    for (const ev of result.events) {
      count += ev.blocking_defects.length;
    }
    return count;
  }, [result]);

  const totalDefects = useMemo(() => {
    return result.total_rule_failures + result.total_kde_errors;
  }, [result]);

  // Track "all clear" milestone
  useEffect(() => {
    if (totalDefects === 0 && result.total_events > 0 && !hasTrackedAllClear.current) {
      hasTrackedAllClear.current = true;
      trackSandbox('ALL_CLEAR', { event_count: result.total_events });
    }
  }, [totalDefects, result.total_events]);

  // Extract unique TLCs from grid data for trace autocomplete
  const availableTlcs = useMemo(() => {
    const tlcColIdx = headers.findIndex(
      (h) => h.toLowerCase().replace(/\s+/g, '_') === 'traceability_lot_code'
    );
    if (tlcColIdx < 0) return [];
    const seen = new Set<string>();
    for (const row of history.data) {
      const val = row[tlcColIdx]?.trim();
      if (val) seen.add(val);
    }
    return Array.from(seen).sort();
  }, [headers, history.data]);

  // ---------------------------------------------------------------------------
  // Re-evaluation
  // ---------------------------------------------------------------------------

  const evaluateCsv = useCallback(async (csv: string) => {
    // Abort any in-flight request so stale responses can't overwrite fresh state
    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    const gen = ++evalGenRef.current;

    setIsEvaluating(true);
    try {
      const res = await fetch('/api/ingestion/api/v1/sandbox/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv }),
        signal: controller.signal,
      });

      // Discard if a newer evaluation has already been launched
      if (gen !== evalGenRef.current) return;

      if (res.status === 429) {
        const retryAfter = parseInt(res.headers.get('Retry-After') || '60', 10);
        setRateLimitMsg(`Rate limit reached. Auto-retrying in ${retryAfter}s...`);
        setTimeout(() => {
          setRateLimitMsg(null);
          scheduleReEval(history.data);
        }, retryAfter * 1000);
        return;
      }

      if (res.ok) {
        setRateLimitMsg(null);
        const data: SandboxResult = await res.json();
        setResult(data);

        // Remove fixed-cell markers for cells that still have errors
        setFixedCells((prev) => {
          const next = new Set(prev);
          const newErrors = buildCellErrorMap(data.events, headers);
          for (const key of prev) {
            if (newErrors.has(key)) {
              next.delete(key); // Fix didn't work
            }
          }
          return next;
        });
      }
    } catch (err: unknown) {
      // Ignore aborted requests; silently fail on network errors
      if (err instanceof DOMException && err.name === 'AbortError') return;
    } finally {
      if (gen === evalGenRef.current) {
        setIsEvaluating(false);
      }
    }
  }, [headers]);

  const scheduleReEval = useCallback((newData: string[][]) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      const csv = gridToCsv(headers, newData);
      evaluateCsv(csv);
    }, 800);
  }, [headers, evaluateCsv]);

  // Cleanup debounce + abort on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, []);

  // ---------------------------------------------------------------------------
  // Cell editing
  // ---------------------------------------------------------------------------

  function startEditing(row: number, col: number) {
    setEditingCell({ row, col });
    setEditValue(history.data[row]?.[col] || '');
    // Focus the input after render
    setTimeout(() => editInputRef.current?.focus(), 0);
  }

  function commitEdit() {
    if (!editingCell) return;
    const { row, col } = editingCell;
    const oldValue = history.data[row]?.[col] || '';

    if (editValue !== oldValue) {
      if (!hasTrackedFirstEdit.current) {
        hasTrackedFirstEdit.current = true;
        trackSandbox('GRID_EDIT', { row, column: headers[col] });
      }
      const newData = history.data.map((r, ri) =>
        ri === row ? r.map((c, ci) => (ci === col ? editValue : c)) : [...r]
      );
      history.push(newData);
      setFixedCells((prev) => new Set(prev).add(cellKey(row, headers[col])));
      scheduleReEval(newData);
    }

    setEditingCell(null);
  }

  function cancelEdit() {
    setEditingCell(null);
  }

  // ---------------------------------------------------------------------------
  // Mass fill
  // ---------------------------------------------------------------------------

  function handleMassFill(column: string, value: string, onlyEmpty: boolean) {
    const colIdx = headers.indexOf(column);
    if (colIdx < 0) return;

    const newData = history.data.map((row, rowIdx) => {
      const newRow = [...row];
      if (onlyEmpty ? !newRow[colIdx]?.trim() : true) {
        newRow[colIdx] = value;
        setFixedCells((prev) => new Set(prev).add(cellKey(rowIdx, column)));
      }
      return newRow;
    });

    history.push(newData);
    scheduleReEval(newData);
  }

  // ---------------------------------------------------------------------------
  // Guided Resolution handlers
  // ---------------------------------------------------------------------------

  function handleAddRow(cteType: string, prefill: Record<string, string>) {
    setAddEventModal({ open: true, cteType, prefill });
  }

  function handleAddRowConfirm(values: Record<string, string>) {
    // Map values to a row array matching our headers
    const newRow = headers.map((h) => {
      const lowerH = h.toLowerCase().replace(/\s+/g, '_');
      // Try exact match, then check values keys
      return values[h] || values[lowerH] || '';
    });

    const newData = [...history.data.map((r) => [...r]), newRow];
    history.push(newData);
    scheduleReEval(newData);
    setAddEventModal(null);
  }

  function handleEditCellFromTooltip(row: number, column: string) {
    const colIdx = headers.findIndex(
      (h) => h.toLowerCase().replace(/\s+/g, '_') === column.toLowerCase().replace(/\s+/g, '_')
    );
    if (colIdx >= 0) {
      startEditing(row, colIdx);
    }
  }

  function handleMassFillFromTooltip(column: string, value: string) {
    const colIdx = headers.findIndex(
      (h) => h.toLowerCase().replace(/\s+/g, '_') === column.toLowerCase().replace(/\s+/g, '_')
    );
    if (colIdx < 0) return;

    const newData = history.data.map((row, rowIdx) => {
      const newRow = [...row];
      newRow[colIdx] = value;
      setFixedCells((prev) => new Set(prev).add(cellKey(rowIdx, headers[colIdx])));
      return newRow;
    });

    history.push(newData);
    scheduleReEval(newData);
  }

  // ---------------------------------------------------------------------------
  // Undo/redo with keyboard
  // ---------------------------------------------------------------------------

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'z') {
        if (e.shiftKey) {
          e.preventDefault();
          history.redo();
        } else {
          e.preventDefault();
          history.undo();
        }
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [history]);

  // Re-evaluate after undo/redo
  const prevDataRef = useRef(history.data);
  useEffect(() => {
    if (prevDataRef.current !== history.data) {
      prevDataRef.current = history.data;
      scheduleReEval(history.data);
    }
  }, [history.data, scheduleReEval]);

  // ---------------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------------

  function doExportCsv() {
    trackSandbox('EXPORT_CSV', { event_count: result.total_events, defect_count: totalDefects });
    const csv = gridToCsv(headers, history.data);
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `regengine-corrected-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  function handleExportCsv() {
    // Show lead gate before export
    pendingExportRef.current = doExportCsv;
    setLeadGateOpen(true);
  }

  // ---------------------------------------------------------------------------
  // TanStack Table
  // ---------------------------------------------------------------------------

  const columnHelper = createColumnHelper<string[]>();

  const columns = useMemo(() => {
    return [
      // Row number column
      columnHelper.display({
        id: '_row_num',
        header: () => <span className="text-[0.6rem] text-[var(--re-text-disabled)]">#</span>,
        cell: (info) => (
          <span className="text-[0.6rem] text-[var(--re-text-disabled)] font-mono">
            {info.row.index + 1}
          </span>
        ),
        size: 32,
      }),
      // Data columns
      ...headers.map((header, colIdx) =>
        columnHelper.accessor((row) => row[colIdx], {
          id: header,
          header: () => (
            <span className="text-[0.65rem] font-semibold text-[var(--re-text-secondary)] truncate">
              {header}
            </span>
          ),
          cell: (info) => {
            const rowIdx = info.row.index;
            const value = info.getValue() || '';
            const key = cellKey(rowIdx, header);
            const errors = cellErrors.get(key) || [];
            const isFixed = fixedCells.has(key) && errors.length === 0;
            const hasError = errors.length > 0;
            const isEditing = editingCell?.row === rowIdx && editingCell?.col === colIdx;

            if (isEditing) {
              return (
                <input
                  ref={editInputRef}
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={commitEdit}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitEdit();
                    if (e.key === 'Escape') cancelEdit();
                    if (e.key === 'Tab') {
                      e.preventDefault();
                      commitEdit();
                      // Move to next cell
                      const nextCol = e.shiftKey ? colIdx - 1 : colIdx + 1;
                      if (nextCol >= 0 && nextCol < headers.length) {
                        setTimeout(() => startEditing(rowIdx, nextCol), 0);
                      }
                    }
                  }}
                  className="w-full bg-white text-re-text-primary px-1.5 py-0.5 text-[0.65rem] font-mono rounded border-2 border-[var(--re-brand)] outline-none"
                />
              );
            }

            const cellContent = (
              <div
                onDoubleClick={() => startEditing(rowIdx, colIdx)}
                className={`
                  px-1.5 py-1 text-[0.65rem] font-mono cursor-text truncate rounded-sm transition-colors
                  ${hasError
                    ? 'bg-re-danger-muted0/15 text-re-danger border border-re-danger/30'
                    : isFixed
                    ? 'bg-re-brand/15 text-re-brand-light border border-re-brand/30'
                    : 'text-[var(--re-text-primary)] hover:bg-[var(--re-surface-base)]'
                  }
                  ${!value ? 'italic text-[var(--re-text-disabled)]' : ''}
                `}
                title={hasError ? 'Double-click to edit' : value}
              >
                {value || (hasError ? 'empty' : '\u00A0')}
              </div>
            );

            if (hasError) {
              return (
                <FixItTooltip
                  errors={errors}
                  rowIndex={rowIdx}
                  onAddRow={handleAddRow}
                  onEditCell={handleEditCellFromTooltip}
                  onMassFill={handleMassFillFromTooltip}
                >
                  {cellContent}
                </FixItTooltip>
              );
            }

            return cellContent;
          },
          size: Math.max(100, Math.min(200, header.length * 10 + 40)),
        })
      ),
    ];
  }, [headers, cellErrors, fixedCells, editingCell, editValue, columnHelper]);

  const table = useReactTable({
    data: history.data,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (headers.length === 0) {
    return <div className="p-4 text-[var(--re-text-muted)]">No data to display.</div>;
  }

  return (
    <div className="w-full border border-[var(--re-surface-border)] rounded-xl overflow-hidden bg-[var(--re-surface-card)]">
      <GridToolbar
        criticalDefects={criticalDefects}
        totalDefects={totalDefects}
        canUndo={history.canUndo}
        canRedo={history.canRedo}
        isEvaluating={isEvaluating}
        rateLimitMsg={rateLimitMsg}
        showTrace={showTrace}
        onUndo={history.undo}
        onRedo={history.redo}
        onMassFill={() => setMassFillOpen(true)}
        onExportCsv={handleExportCsv}
        onPdfReport={() => generateComplianceReport(result)}
        onBack={onBack}
        onToggleTrace={() => setShowTrace((v) => !v)}
      />

      {/* Grid */}
      <div className="overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-[var(--re-surface-border)]">
                {headerGroup.headers.map((header) => (
                  <th
                    key={header.id}
                    className="px-2 py-2 text-left bg-[var(--re-surface-elevated)] sticky top-0"
                    style={{ width: header.getSize(), minWidth: header.getSize() }}
                  >
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => {
              // Check if this row's event is non-compliant
              const evResult = result.events[row.index];
              const rowHasIssues = evResult && !evResult.compliant;

              return (
                <tr
                  key={row.id}
                  data-row-index={row.index}
                  className={`border-b border-[var(--re-surface-border)]/50 transition-all ${
                    rowHasIssues ? 'bg-re-danger-muted0/[0.03]' : ''
                  } hover:bg-[var(--re-surface-elevated)]/30`}
                >
                  {row.getVisibleCells().map((cell) => (
                    <td
                      key={cell.id}
                      className="px-1 py-0.5"
                      style={{ width: cell.column.getSize(), minWidth: cell.column.getSize() }}
                    >
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Footer hint */}
      <div className="px-4 py-2 border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
        <span className="text-[0.6rem] text-[var(--re-text-disabled)]">
          Double-click a cell to edit. Hover red cells for fix suggestions. Changes auto-validate.
          Ctrl+Z to undo.
        </span>
      </div>

      {/* Trace Panel */}
      {showTrace && (
        <div className="border-t border-[var(--re-surface-border)]">
          <TracePanel
            csv={gridToCsv(headers, history.data)}
            availableTlcs={availableTlcs}
            onHighlightEvent={(eventIndex) => {
              // Scroll the row into view and briefly highlight it
              const row = document.querySelector(`[data-row-index="${eventIndex}"]`);
              if (row) {
                row.scrollIntoView({ behavior: 'smooth', block: 'center' });
                row.classList.add('ring-2', 'ring-[var(--re-brand)]');
                setTimeout(() => row.classList.remove('ring-2', 'ring-[var(--re-brand)]'), 2000);
              }
            }}
          />
        </div>
      )}

      <MassFillDialog
        open={massFillOpen}
        onOpenChange={setMassFillOpen}
        headers={headers}
        onApply={handleMassFill}
      />

      {/* Conversion CTA — appears when all defects are fixed */}
      {totalDefects === 0 && result.total_events > 0 && (
        <div className="px-4 py-3 border-t border-[var(--re-surface-border)]">
          <SandboxResultsCTA
            mode="all_clear"
            eventCount={result.total_events}
            onTrack={trackSandbox}
          />
        </div>
      )}

      {addEventModal && (
        <AddEventModal
          open={addEventModal.open}
          onClose={() => setAddEventModal(null)}
          onConfirm={handleAddRowConfirm}
          cteType={addEventModal.cteType}
          prefill={addEventModal.prefill}
        />
      )}

      <ExportLeadGate
        open={leadGateOpen}
        onOpenChange={setLeadGateOpen}
        onExport={() => { pendingExportRef.current?.(); pendingExportRef.current = null; }}
        onTrack={trackSandbox}
        defectCount={totalDefects}
        eventCount={result.total_events}
      />
    </div>
  );
}
