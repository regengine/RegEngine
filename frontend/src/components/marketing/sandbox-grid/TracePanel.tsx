'use client';

import { useState, useCallback, useRef } from 'react';
import {
  Search, GitBranch, ArrowUpRight, ArrowDownRight,
  Loader2, Download, MapPin, Package, Clock, X,
  ChevronRight,
} from 'lucide-react';
import { usePostHog } from 'posthog-js/react';
import { SandboxResultsCTA } from './SandboxResultsCTA';

// ---------------------------------------------------------------------------
// Types (mirrors backend TraceGraphResponse)
// ---------------------------------------------------------------------------

interface TraceNode {
  event_index: number;
  cte_type: string;
  traceability_lot_code: string;
  product_description: string;
  quantity: number | null;
  unit_of_measure: string;
  timestamp: string;
  location_name: string;
  facility_from: string;
  facility_to: string;
  depth: number;
}

interface TraceEdge {
  from_event_index: number;
  to_event_index: number;
  link_type: string;
  lot_code: string;
}

interface TraceGraphResponse {
  seed_tlc: string;
  direction: string;
  nodes: TraceNode[];
  edges: TraceEdge[];
  lots_touched: string[];
  facilities: string[];
  max_depth: number;
  total_quantity: number;
}

interface TracePanelProps {
  csv: string;
  /** Available TLCs from current grid data for autocomplete */
  availableTlcs: string[];
  onHighlightEvent?: (eventIndex: number) => void;
}

// ---------------------------------------------------------------------------
// CTE type → visual config
// ---------------------------------------------------------------------------

const CTE_COLORS: Record<string, { bg: string; border: string; text: string; icon: string }> = {
  harvesting:     { bg: 'bg-re-success-muted0/15',   border: 'border-green-500/40',   text: 'text-re-success',   icon: '🌱' },
  cooling:        { bg: 'bg-cyan-500/15',     border: 'border-cyan-500/40',    text: 'text-cyan-400',    icon: '❄️' },
  shipping:       { bg: 'bg-re-info-muted0/15',     border: 'border-blue-500/40',    text: 'text-re-info',    icon: '🚛' },
  receiving:      { bg: 'bg-purple-500/15',   border: 'border-purple-500/40',  text: 'text-purple-400',  icon: '📦' },
  transformation: { bg: 'bg-re-warning-muted0/15',    border: 'border-re-warning/40',   text: 'text-re-warning',   icon: '🔄' },
  packing:        { bg: 'bg-orange-500/15',   border: 'border-orange-500/40',  text: 'text-orange-400',  icon: '📋' },
};

const DEFAULT_CTE_COLOR = { bg: 'bg-re-surface-card0/15', border: 'border-re-border/40', text: 'text-re-text-tertiary', icon: '📄' };

function getCteVisual(cteType: string) {
  return CTE_COLORS[cteType.toLowerCase()] || DEFAULT_CTE_COLOR;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TracePanel({ csv, availableTlcs, onHighlightEvent }: TracePanelProps) {
  const [tlcInput, setTlcInput] = useState('');
  const [direction, setDirection] = useState<'both' | 'upstream' | 'downstream'>('both');
  const [isTracing, setIsTracing] = useState(false);
  const [traceResult, setTraceResult] = useState<TraceGraphResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const posthog = usePostHog();

  function trackSandbox(event: string, metadata: Record<string, unknown> = {}) {
    posthog.capture(`SANDBOX_${event}`, {
      ...metadata,
      timestamp: new Date().toISOString(),
    });
  }

  const filteredTlcs = availableTlcs.filter(
    (t) => t.toLowerCase().includes(tlcInput.toLowerCase()) && t !== tlcInput
  ).slice(0, 8);

  const runTrace = useCallback(async (tlc?: string) => {
    const code = (tlc || tlcInput).trim();
    if (!code || !csv.trim()) return;

    if (abortRef.current) abortRef.current.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setIsTracing(true);
    setError(null);
    setTraceResult(null);

    try {
      const res = await fetch('/api/ingestion/api/v1/sandbox/trace', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv, tlc: code, direction, max_depth: 10 }),
        signal: controller.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data: TraceGraphResponse = await res.json();
      setTraceResult(data);
      trackSandbox('TRACE_RUN', {
        direction,
        seed_tlc: code,
        node_count: data.nodes.length,
        lot_count: data.lots_touched.length,
        facility_count: data.facilities.length,
        max_depth: data.max_depth,
      });
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') return;
      setError(err instanceof Error ? err.message : 'Trace failed');
    } finally {
      setIsTracing(false);
    }
  }, [csv, tlcInput, direction]);

  const handleExportTrace = useCallback(() => {
    if (!traceResult) return;

    // Build CSV export: one row per node
    const headers = ['depth', 'cte_type', 'lot_code', 'product', 'quantity', 'uom', 'timestamp', 'location', 'from', 'to'];
    const rows = traceResult.nodes
      .sort((a, b) => a.depth - b.depth || a.timestamp.localeCompare(b.timestamp))
      .map((n) => [
        n.depth,
        n.cte_type,
        n.traceability_lot_code,
        n.product_description,
        n.quantity ?? '',
        n.unit_of_measure,
        n.timestamp,
        n.location_name,
        n.facility_from,
        n.facility_to,
      ].map((v) => {
        const s = String(v);
        return s.includes(',') ? `"${s}"` : s;
      }).join(','));

    const csvContent = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `regengine-trace-${traceResult.seed_tlc}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [traceResult]);

  const handleExportFdaFormat = useCallback(() => {
    if (!traceResult) return;
    trackSandbox('FDA_EXPORT', {
      seed_tlc: traceResult.seed_tlc,
      node_count: traceResult.nodes.length,
      lot_count: traceResult.lots_touched.length,
    });

    // FDA 204 sortable spreadsheet format
    const headers = [
      'Traceability Lot Code', 'CTE Type', 'Product Description',
      'Quantity', 'Unit of Measure', 'Event Timestamp',
      'Location / Facility', 'Ship From', 'Ship To',
      'Trace Depth', 'Link to Seed TLC',
    ];
    const rows = traceResult.nodes
      .sort((a, b) => a.depth - b.depth || a.timestamp.localeCompare(b.timestamp))
      .map((n) => [
        n.traceability_lot_code,
        n.cte_type,
        n.product_description,
        n.quantity ?? '',
        n.unit_of_measure,
        n.timestamp,
        n.location_name,
        n.facility_from,
        n.facility_to,
        n.depth,
        n.depth === 0 ? 'SEED' : `${n.depth} hop${n.depth > 1 ? 's' : ''} from ${traceResult.seed_tlc}`,
      ].map((v) => {
        const s = String(v);
        return s.includes(',') ? `"${s}"` : s;
      }).join(','));

    const csvContent = [headers.join(','), ...rows].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `fda-204-trace-${traceResult.seed_tlc}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }, [traceResult]);

  // Group nodes by lot code for the genealogy view
  const lotGroups = traceResult
    ? (() => {
        const groups = new Map<string, TraceNode[]>();
        for (const n of traceResult.nodes) {
          const list = groups.get(n.traceability_lot_code) || [];
          list.push(n);
          groups.set(n.traceability_lot_code, list);
        }
        return groups;
      })()
    : null;

  return (
    <div className="border border-[var(--re-surface-border)] rounded-xl overflow-hidden bg-[var(--re-surface-card)]">
      {/* Header */}
      <div className="flex items-center gap-2 px-4 py-2.5 bg-[var(--re-surface-elevated)] border-b border-[var(--re-surface-border)]">
        <GitBranch className="w-4 h-4 text-[var(--re-brand)]" />
        <span className="text-[0.75rem] font-semibold text-[var(--re-text-primary)]">
          Trace-Back / Recall Readiness
        </span>
        <span className="text-[0.6rem] text-[var(--re-text-disabled)] ml-1">
          FDA 204(d) one-click trace
        </span>
      </div>

      {/* Search bar */}
      <div className="px-4 py-3 border-b border-[var(--re-surface-border)] space-y-2">
        <div className="flex gap-2">
          <div className="relative flex-1">
            <input
              type="text"
              value={tlcInput}
              onChange={(e) => {
                setTlcInput(e.target.value);
                setShowSuggestions(true);
              }}
              onFocus={() => setShowSuggestions(true)}
              onBlur={() => setTimeout(() => setShowSuggestions(false), 200)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  setShowSuggestions(false);
                  runTrace();
                }
              }}
              placeholder="Enter TLC to trace (e.g., LOT-2026-001)"
              className="w-full bg-[var(--re-surface-base)] border border-[var(--re-surface-border)] rounded-lg px-3 py-2 pl-8 text-[0.7rem] font-mono text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)]/30"
            />
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--re-text-disabled)]" />

            {/* TLC autocomplete */}
            {showSuggestions && filteredTlcs.length > 0 && (
              <div className="absolute z-50 top-full left-0 right-0 mt-1 bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] rounded-lg shadow-xl overflow-hidden">
                {filteredTlcs.map((t) => (
                  <button
                    key={t}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => {
                      setTlcInput(t);
                      setShowSuggestions(false);
                      runTrace(t);
                    }}
                    className="w-full px-3 py-1.5 text-left text-[0.65rem] font-mono text-[var(--re-text-primary)] hover:bg-[var(--re-surface-base)] transition-colors"
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Direction selector */}
          <div className="flex rounded-lg border border-[var(--re-surface-border)] overflow-hidden">
            {(['upstream', 'both', 'downstream'] as const).map((d) => (
              <button
                key={d}
                onClick={() => setDirection(d)}
                className={`px-2.5 py-1.5 text-[0.6rem] font-medium transition-colors ${
                  direction === d
                    ? 'bg-[var(--re-brand)] text-white'
                    : 'bg-[var(--re-surface-base)] text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]'
                }`}
              >
                {d === 'upstream' && <ArrowUpRight className="w-3 h-3 inline mr-0.5" />}
                {d === 'downstream' && <ArrowDownRight className="w-3 h-3 inline mr-0.5" />}
                {d === 'both' && <GitBranch className="w-3 h-3 inline mr-0.5" />}
                {d.charAt(0).toUpperCase() + d.slice(1)}
              </button>
            ))}
          </div>

          <button
            onClick={() => runTrace()}
            disabled={!tlcInput.trim() || isTracing}
            className="px-4 py-2 bg-[var(--re-brand)] text-white rounded-lg text-[0.7rem] font-semibold hover:bg-[var(--re-brand-dark)] disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center gap-1.5"
          >
            {isTracing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Search className="w-3.5 h-3.5" />}
            Trace
          </button>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="px-4 py-2 bg-re-danger-muted0/10 border-b border-re-danger/20">
          <p className="text-[0.65rem] text-re-danger">{error}</p>
        </div>
      )}

      {/* Results */}
      {traceResult && (
        <div className="divide-y divide-[var(--re-surface-border)]">
          {/* Summary stats */}
          <div className="px-4 py-3 grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="text-center">
              <div className="text-lg font-bold text-[var(--re-text-primary)]">{traceResult.nodes.length}</div>
              <div className="text-[0.6rem] text-[var(--re-text-muted)]">Events</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-[var(--re-text-primary)]">{traceResult.lots_touched.length}</div>
              <div className="text-[0.6rem] text-[var(--re-text-muted)]">Lot Codes</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-[var(--re-text-primary)]">{traceResult.facilities.length}</div>
              <div className="text-[0.6rem] text-[var(--re-text-muted)]">Facilities</div>
            </div>
            <div className="text-center">
              <div className="text-lg font-bold text-[var(--re-text-primary)]">{traceResult.max_depth}</div>
              <div className="text-[0.6rem] text-[var(--re-text-muted)]">Max Depth</div>
            </div>
          </div>

          {/* Genealogy map — lot groups with event nodes */}
          <div className="px-4 py-3">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-[0.7rem] font-semibold text-[var(--re-text-secondary)]">
                Supply Chain Genealogy
              </h4>
              <div className="flex gap-1.5">
                <button
                  onClick={handleExportTrace}
                  className="flex items-center gap-1 px-2 py-1 rounded-md text-[0.6rem] text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] hover:bg-[var(--re-surface-base)] transition-all"
                  title="Export trace CSV"
                >
                  <Download className="w-3 h-3" />
                  CSV
                </button>
                <button
                  onClick={handleExportFdaFormat}
                  className="flex items-center gap-1 px-2 py-1 rounded-md text-[0.6rem] font-medium bg-[var(--re-brand)]/10 text-[var(--re-brand)] hover:bg-[var(--re-brand)]/20 transition-all"
                  title="Export FDA 204 trace format"
                >
                  <Download className="w-3 h-3" />
                  FDA 204
                </button>
              </div>
            </div>

            {/* Lot group cards */}
            <div className="space-y-2">
              {lotGroups && Array.from(lotGroups.entries())
                .sort(([, a], [, b]) => {
                  const minA = Math.min(...a.map((n) => n.depth));
                  const minB = Math.min(...b.map((n) => n.depth));
                  return minA - minB;
                })
                .map(([lotCode, nodes]) => {
                  const isSeed = lotCode === traceResult.seed_tlc;
                  const sortedNodes = [...nodes].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
                  const product = sortedNodes[0]?.product_description || '';

                  return (
                    <div
                      key={lotCode}
                      className={`rounded-lg border ${
                        isSeed
                          ? 'border-[var(--re-brand)]/50 bg-[var(--re-brand)]/5'
                          : 'border-[var(--re-surface-border)] bg-[var(--re-surface-base)]'
                      }`}
                    >
                      {/* Lot header */}
                      <div className="flex items-center gap-2 px-3 py-2">
                        <Package className={`w-3.5 h-3.5 ${isSeed ? 'text-[var(--re-brand)]' : 'text-[var(--re-text-muted)]'}`} />
                        <span className={`text-[0.7rem] font-mono font-bold ${isSeed ? 'text-[var(--re-brand)]' : 'text-[var(--re-text-primary)]'}`}>
                          {lotCode}
                        </span>
                        {isSeed && (
                          <span className="px-1.5 py-0.5 rounded-full bg-[var(--re-brand)]/20 text-[var(--re-brand)] text-[0.55rem] font-bold">
                            SEED
                          </span>
                        )}
                        {product && (
                          <span className="text-[0.6rem] text-[var(--re-text-muted)] ml-auto">{product}</span>
                        )}
                      </div>

                      {/* Event nodes for this lot */}
                      <div className="px-3 pb-2 flex flex-wrap gap-1.5">
                        {sortedNodes.map((node) => {
                          const vis = getCteVisual(node.cte_type);
                          return (
                            <button
                              key={`${node.event_index}-${node.cte_type}`}
                              onClick={() => onHighlightEvent?.(node.event_index)}
                              className={`flex items-center gap-1.5 px-2 py-1 rounded-md border ${vis.bg} ${vis.border} hover:brightness-125 transition-all cursor-pointer`}
                              title={`Row ${node.event_index + 1}: ${node.cte_type} at ${node.location_name || node.facility_from || '?'}`}
                            >
                              <span className="text-[0.6rem]">{vis.icon}</span>
                              <span className={`text-[0.6rem] font-semibold ${vis.text}`}>
                                {node.cte_type}
                              </span>
                              {node.quantity != null && (
                                <span className="text-[0.55rem] text-[var(--re-text-muted)]">
                                  {node.quantity} {node.unit_of_measure}
                                </span>
                              )}
                              {(node.location_name || node.facility_from) && (
                                <>
                                  <span className="text-[var(--re-text-disabled)]">·</span>
                                  <span className="text-[0.55rem] text-[var(--re-text-muted)] truncate max-w-[120px]">
                                    {node.location_name || node.facility_from}
                                  </span>
                                </>
                              )}
                            </button>
                          );
                        })}
                      </div>

                      {/* Show linkages from this lot to others */}
                      {traceResult.edges
                        .filter((e) =>
                          nodes.some((n) => n.event_index === e.from_event_index) &&
                          e.link_type.includes('transformation')
                        )
                        .map((edge, i) => {
                          const targetNode = traceResult.nodes.find((n) => n.event_index === edge.to_event_index);
                          if (!targetNode || targetNode.traceability_lot_code === lotCode) return null;
                          return (
                            <div key={i} className="px-3 pb-1.5 flex items-center gap-1.5">
                              <ChevronRight className="w-3 h-3 text-[var(--re-text-disabled)]" />
                              <span className="text-[0.55rem] text-[var(--re-text-muted)]">
                                {edge.link_type === 'transformation_input' ? 'feeds into' : 'produces'}
                              </span>
                              <span className="text-[0.6rem] font-mono text-re-warning">
                                {targetNode.traceability_lot_code}
                              </span>
                            </div>
                          );
                        })}
                    </div>
                  );
                })}
            </div>
          </div>

          {/* Conversion CTA — after successful trace */}
          {traceResult.nodes.length > 0 && (
            <div className="px-4 py-3">
              <SandboxResultsCTA
                mode="trace_complete"
                lotCount={traceResult.lots_touched.length}
                facilityCount={traceResult.facilities.length}
                onTrack={trackSandbox}
              />
            </div>
          )}

          {/* Empty state */}
          {traceResult.nodes.length === 0 && (
            <div className="px-4 py-8 text-center">
              <Search className="w-8 h-8 text-[var(--re-text-disabled)] mx-auto mb-2" />
              <p className="text-[0.7rem] text-[var(--re-text-muted)]">
                No events found for TLC &quot;{traceResult.seed_tlc}&quot;
              </p>
              <p className="text-[0.6rem] text-[var(--re-text-disabled)] mt-1">
                Check that the lot code exists in your CSV data.
              </p>
            </div>
          )}
        </div>
      )}

      {/* Initial empty state */}
      {!traceResult && !isTracing && !error && (
        <div className="px-4 py-6 text-center">
          <GitBranch className="w-8 h-8 text-[var(--re-text-disabled)] mx-auto mb-2" />
          <p className="text-[0.7rem] text-[var(--re-text-muted)]">
            Enter a Traceability Lot Code to trace its journey
          </p>
          <p className="text-[0.6rem] text-[var(--re-text-disabled)] mt-1">
            Upstream traces find source materials. Downstream traces find where product went.
          </p>
          {availableTlcs.length > 0 && (
            <div className="flex flex-wrap gap-1 justify-center mt-3">
              {availableTlcs.slice(0, 5).map((t) => (
                <button
                  key={t}
                  onClick={() => {
                    setTlcInput(t);
                    runTrace(t);
                  }}
                  className="px-2 py-1 rounded-md bg-[var(--re-surface-base)] border border-[var(--re-surface-border)] text-[0.6rem] font-mono text-[var(--re-text-secondary)] hover:border-[var(--re-brand)]/50 hover:text-[var(--re-brand)] transition-all"
                >
                  {t}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
