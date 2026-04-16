'use client';

import { useState, useMemo, useCallback } from 'react';
import {
  Sparkles, ArrowRight, ChevronDown, ChevronUp,
  Check, X, CheckCheck, XCircle, Info,
} from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface NormalizationAction {
  field: string;
  original: string;
  normalized: string;
  action_type: string;
  reasoning?: string;
  event_index?: number;
}

type Decision = 'pending' | 'accepted' | 'rejected';

interface NormalizationWithDecision extends NormalizationAction {
  id: string;
  decision: Decision;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface NormalizationReviewProps {
  normalizations: NormalizationAction[];
  /** Called when the user applies accepted changes. Receives a map of original→normalized for accepted items. */
  onApply: (changes: { field: string; original: string; normalized: string; action_type: string }[]) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const ACTION_LABELS: Record<string, string> = {
  header_alias: 'Headers Mapped',
  uom_normalize: 'Units Standardized',
  cte_type_normalize: 'CTE Types Resolved',
};

function groupLabel(actionType: string): string {
  return ACTION_LABELS[actionType] || 'Other';
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function NormalizationReview({ normalizations, onApply }: NormalizationReviewProps) {
  const [expanded, setExpanded] = useState(false);
  const [items, setItems] = useState<NormalizationWithDecision[]>(() =>
    normalizations.map((n, i) => ({
      ...n,
      id: `${n.action_type}-${n.original}-${i}`,
      decision: 'pending' as Decision,
    })),
  );
  const [applied, setApplied] = useState(false);

  const counts = useMemo(() => {
    let accepted = 0, rejected = 0, pending = 0;
    for (const item of items) {
      if (item.decision === 'accepted') accepted++;
      else if (item.decision === 'rejected') rejected++;
      else pending++;
    }
    return { accepted, rejected, pending, total: items.length };
  }, [items]);

  const setDecision = useCallback((id: string, decision: Decision) => {
    setItems((prev) => prev.map((item) =>
      item.id === id ? { ...item, decision } : item,
    ));
    setApplied(false);
  }, []);

  const setAllDecisions = useCallback((decision: Decision) => {
    setItems((prev) => prev.map((item) => ({ ...item, decision })));
    setApplied(false);
  }, []);

  const setGroupDecision = useCallback((actionType: string, decision: Decision) => {
    setItems((prev) => prev.map((item) =>
      item.action_type === actionType ? { ...item, decision } : item,
    ));
    setApplied(false);
  }, []);

  const setEventDecision = useCallback((eventIndex: number, decision: Decision) => {
    setItems((prev) => prev.map((item) =>
      item.event_index === eventIndex ? { ...item, decision } : item,
    ));
    setApplied(false);
  }, []);

  const handleApply = useCallback(() => {
    const accepted = items
      .filter((item) => item.decision === 'accepted')
      .map(({ field, original, normalized, action_type }) => ({
        field, original, normalized, action_type,
      }));
    onApply(accepted);
    setApplied(true);
  }, [items, onApply]);

  // Group items by action_type
  const grouped = useMemo(() => {
    const groups: Record<string, NormalizationWithDecision[]> = {};
    for (const item of items) {
      const key = item.action_type;
      (groups[key] ??= []).push(item);
    }
    return groups;
  }, [items]);

  // Unique event indices for per-event controls
  const eventIndices = useMemo(() => {
    const indices = new Set<number>();
    for (const item of items) {
      if (item.event_index !== undefined && item.event_index >= 0) {
        indices.add(item.event_index);
      }
    }
    return Array.from(indices).sort((a, b) => a - b);
  }, [items]);

  if (items.length === 0) return null;

  return (
    <div className="rounded-lg border border-[var(--re-brand)]/20 bg-[var(--re-brand)]/5 overflow-hidden">
      {/* Header */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-[var(--re-brand)]/10 transition-colors"
      >
        <div className="flex items-center gap-2">
          <Sparkles className="w-4 h-4 text-[var(--re-brand)]" />
          <span className="text-[0.8rem] font-semibold text-[var(--re-brand)]">
            Suggested Normalizations
          </span>
          <span className="text-[0.65rem] px-1.5 py-0.5 rounded-full bg-[var(--re-brand)]/15 text-[var(--re-brand)] font-mono">
            {counts.total}
          </span>
          {counts.accepted > 0 && (
            <span className="text-[0.6rem] px-1.5 py-0.5 rounded-full bg-green-500/15 text-green-400 font-mono">
              {counts.accepted} accepted
            </span>
          )}
          {counts.rejected > 0 && (
            <span className="text-[0.6rem] px-1.5 py-0.5 rounded-full bg-red-500/15 text-red-400 font-mono">
              {counts.rejected} rejected
            </span>
          )}
        </div>
        {expanded
          ? <ChevronUp className="w-4 h-4 text-[var(--re-brand)]" />
          : <ChevronDown className="w-4 h-4 text-[var(--re-brand)]" />}
      </button>

      {expanded && (
        <div className="border-t border-[var(--re-brand)]/10">
          {/* Bulk actions bar */}
          <div className="px-4 py-2 flex items-center gap-2 border-b border-[var(--re-brand)]/10 bg-[var(--re-surface-elevated)]">
            <span className="text-[0.6rem] text-[var(--re-text-muted)] uppercase tracking-wider font-medium mr-1">
              Bulk:
            </span>
            <button
              onClick={() => setAllDecisions('accepted')}
              className="inline-flex items-center gap-1 px-2 py-1 rounded text-[0.6rem] font-medium bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors cursor-pointer"
            >
              <CheckCheck className="w-3 h-3" />
              Accept All
            </button>
            <button
              onClick={() => setAllDecisions('rejected')}
              className="inline-flex items-center gap-1 px-2 py-1 rounded text-[0.6rem] font-medium bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors cursor-pointer"
            >
              <XCircle className="w-3 h-3" />
              Reject All
            </button>
            <button
              onClick={() => setAllDecisions('pending')}
              className="inline-flex items-center gap-1 px-2 py-1 rounded text-[0.6rem] font-medium bg-[var(--re-surface-base)] text-[var(--re-text-muted)] hover:bg-[var(--re-surface-border)] transition-colors cursor-pointer"
            >
              Reset
            </button>

            {/* Per-event controls (if there are event-specific normalizations) */}
            {eventIndices.length > 0 && (
              <>
                <div className="w-px h-4 bg-[var(--re-surface-border)] mx-1" />
                <span className="text-[0.6rem] text-[var(--re-text-muted)] uppercase tracking-wider font-medium mr-1">
                  By Event:
                </span>
                <div className="flex items-center gap-1 overflow-x-auto">
                  {eventIndices.map((idx) => {
                    const eventItems = items.filter((it) => it.event_index === idx);
                    const allAccepted = eventItems.every((it) => it.decision === 'accepted');
                    const allRejected = eventItems.every((it) => it.decision === 'rejected');
                    return (
                      <button
                        key={idx}
                        onClick={() => setEventDecision(idx, allAccepted ? 'rejected' : 'accepted')}
                        className={`px-1.5 py-0.5 rounded text-[0.55rem] font-mono cursor-pointer transition-colors ${
                          allAccepted ? 'bg-green-500/15 text-green-400' :
                          allRejected ? 'bg-red-500/15 text-red-400' :
                          'bg-[var(--re-surface-base)] text-[var(--re-text-disabled)]'
                        }`}
                        title={`Toggle all normalizations for event ${idx + 1}`}
                      >
                        #{idx + 1}
                      </button>
                    );
                  })}
                </div>
              </>
            )}
          </div>

          {/* Grouped normalizations */}
          <div className="px-4 py-3">
            {Object.entries(grouped).map(([actionType, groupItems]) => (
              <div key={actionType} className="mb-4 last:mb-0">
                <div className="flex items-center justify-between mb-2">
                  <div className="text-[0.65rem] font-medium text-[var(--re-text-muted)] uppercase tracking-wider">
                    {groupLabel(actionType)}
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setGroupDecision(actionType, 'accepted')}
                      className="text-[0.55rem] px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 hover:bg-green-500/20 transition-colors cursor-pointer"
                    >
                      Accept group
                    </button>
                    <button
                      onClick={() => setGroupDecision(actionType, 'rejected')}
                      className="text-[0.55rem] px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-colors cursor-pointer"
                    >
                      Reject group
                    </button>
                  </div>
                </div>

                <div className="space-y-1.5">
                  {groupItems.map((item) => (
                    <div
                      key={item.id}
                      className={`flex items-start gap-2 p-2 rounded transition-colors ${
                        item.decision === 'accepted' ? 'bg-green-500/5 border border-green-500/20' :
                        item.decision === 'rejected' ? 'bg-red-500/5 border border-red-500/20 opacity-60' :
                        'bg-[var(--re-surface-base)] border border-[var(--re-surface-border)]'
                      }`}
                    >
                      {/* Decision buttons */}
                      <div className="flex flex-col gap-0.5 pt-0.5">
                        <button
                          onClick={() => setDecision(item.id, item.decision === 'accepted' ? 'pending' : 'accepted')}
                          className={`p-0.5 rounded transition-colors cursor-pointer ${
                            item.decision === 'accepted'
                              ? 'bg-green-500 text-white'
                              : 'text-[var(--re-text-disabled)] hover:text-green-400 hover:bg-green-500/10'
                          }`}
                          title="Accept this change"
                        >
                          <Check className="w-3 h-3" />
                        </button>
                        <button
                          onClick={() => setDecision(item.id, item.decision === 'rejected' ? 'pending' : 'rejected')}
                          className={`p-0.5 rounded transition-colors cursor-pointer ${
                            item.decision === 'rejected'
                              ? 'bg-red-500 text-white'
                              : 'text-[var(--re-text-disabled)] hover:text-red-400 hover:bg-red-500/10'
                          }`}
                          title="Reject this change"
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </div>

                      {/* Diff content */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 text-[0.7rem]">
                          <code className={`px-1.5 py-0.5 rounded font-mono text-[0.65rem] ${
                            item.decision === 'rejected'
                              ? 'bg-[var(--re-surface-elevated)] text-[var(--re-text-secondary)]'
                              : 'bg-red-500/10 text-red-400 line-through'
                          }`}>
                            {item.original}
                          </code>
                          <ArrowRight className="w-3 h-3 text-[var(--re-text-disabled)] flex-shrink-0" />
                          <code className={`px-1.5 py-0.5 rounded font-mono text-[0.65rem] ${
                            item.decision === 'rejected'
                              ? 'bg-[var(--re-surface-elevated)] text-[var(--re-text-disabled)] line-through'
                              : 'bg-green-500/10 text-green-400'
                          }`}>
                            {item.normalized}
                          </code>
                          {item.event_index !== undefined && item.event_index >= 0 && (
                            <span className="text-[0.55rem] px-1 py-0.5 rounded bg-[var(--re-surface-elevated)] text-[var(--re-text-disabled)] font-mono">
                              Event #{item.event_index + 1}
                            </span>
                          )}
                        </div>
                        {item.reasoning && (
                          <div className="flex items-start gap-1 mt-1">
                            <Info className="w-3 h-3 text-[var(--re-text-disabled)] mt-0.5 flex-shrink-0" />
                            <span className="text-[0.6rem] text-[var(--re-text-muted)] leading-tight">
                              {item.reasoning}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Apply bar */}
          <div className="px-4 py-3 border-t border-[var(--re-brand)]/10 bg-[var(--re-surface-elevated)] flex items-center justify-between">
            <span className="text-[0.65rem] text-[var(--re-text-muted)]">
              {counts.accepted > 0
                ? `${counts.accepted} change${counts.accepted !== 1 ? 's' : ''} will be applied to your CSV`
                : 'Accept changes to apply them to your data'}
            </span>
            <button
              onClick={handleApply}
              disabled={counts.accepted === 0 || applied}
              className={`inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-[0.75rem] font-semibold transition-all cursor-pointer ${
                applied
                  ? 'bg-green-500/20 text-green-400'
                  : counts.accepted > 0
                  ? 'bg-[var(--re-brand)] text-white hover:bg-[var(--re-brand-dark)]'
                  : 'bg-[var(--re-surface-base)] text-[var(--re-text-disabled)] cursor-not-allowed'
              }`}
            >
              {applied ? (
                <><Check className="w-3.5 h-3.5" /> Applied</>
              ) : (
                <><CheckCheck className="w-3.5 h-3.5" /> Apply {counts.accepted} Change{counts.accepted !== 1 ? 's' : ''}</>
              )}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
