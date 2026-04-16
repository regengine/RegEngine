'use client';

import {
  AlertTriangle, CheckCircle2, XCircle, ShieldAlert,
  ChevronDown, ChevronUp, Download, Sparkles, ArrowRight, Link2,
} from 'lucide-react';
import { useState } from 'react';
import { generateComplianceReport } from '@/components/marketing/sandbox-grid/SandboxPdfReport';

// ---------------------------------------------------------------------------
// Types (mirrors SandboxUpload)
// ---------------------------------------------------------------------------

interface RuleResult {
  rule_title: string;
  severity: string;
  result: string;
  why_failed: string | null;
  citation: string | null;
  remediation: string | null;
  category: string;
}

interface EventEvaluation {
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
  blocking_defects: RuleResult[];
  all_results: RuleResult[];
}

interface NormalizationAction {
  field: string;
  original: string;
  normalized: string;
  action_type: string;
}

interface SandboxResult {
  total_events: number;
  compliant_events: number;
  non_compliant_events: number;
  total_kde_errors: number;
  total_rule_failures: number;
  submission_blocked: boolean;
  blocking_reasons: string[];
  events: EventEvaluation[];
  duplicate_warnings?: string[];
  entity_warnings?: string[];
  normalizations?: NormalizationAction[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SharedSandboxResult({ result, shareId }: { result: SandboxResult; shareId: string }) {
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(() => {
    const nonCompliant = new Set<number>();
    result.events.forEach((ev) => {
      if (!ev.compliant) nonCompliant.add(ev.event_index);
    });
    return nonCompliant;
  });

  function toggleEvent(index: number) {
    setExpandedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      <div className="max-w-4xl mx-auto px-4 py-8">
        {/* Shared banner */}
        <div className="mb-6 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Link2 className="w-4 h-4 text-[var(--re-text-muted)]" />
            <span className="text-[0.75rem] text-[var(--re-text-secondary)]">
              Shared sandbox result
            </span>
          </div>
          <a
            href="/#sandbox"
            className="text-[0.75rem] text-[var(--re-brand)] hover:underline"
          >
            Try your own data &rarr;
          </a>
        </div>

        {/* Results card */}
        <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center justify-between">
            <span className="text-[0.8rem] font-semibold text-[var(--re-text-primary)]">
              FSMA 204 Compliance Assessment
            </span>
            <button
              onClick={() => generateComplianceReport(result)}
              className="inline-flex items-center gap-2 bg-white border border-re-border text-re-text-disabled px-3 py-1.5 rounded-lg text-[0.7rem] font-medium transition-all hover:bg-re-surface-card cursor-pointer"
            >
              <Download className="w-3.5 h-3.5" />
              Download PDF
            </button>
          </div>

          <div className="p-4 space-y-4">
            {/* Summary Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Events', value: result.total_events, color: 'text-[var(--re-text-primary)]' },
                { label: 'Compliant', value: result.compliant_events, color: 'text-re-brand' },
                { label: 'Non-compliant', value: result.non_compliant_events, color: result.non_compliant_events > 0 ? 'text-re-danger' : 'text-[var(--re-text-primary)]' },
                { label: 'Rule Failures', value: result.total_rule_failures, color: result.total_rule_failures > 0 ? 'text-re-warning' : 'text-[var(--re-text-primary)]' },
              ].map((stat) => (
                <div key={stat.label} className="bg-[var(--re-surface-elevated)] rounded-lg p-3 text-center">
                  <div className={`text-xl font-bold font-mono ${stat.color}`}>{stat.value}</div>
                  <div className="text-[0.65rem] text-[var(--re-text-muted)]">{stat.label}</div>
                </div>
              ))}
            </div>

            {/* Normalization Diff */}
            {result.normalizations && result.normalizations.length > 0 && (
              <div className="rounded-lg border border-[var(--re-brand)]/20 bg-[var(--re-brand)]/5 overflow-hidden">
                <button
                  onClick={() => {
                    setExpandedEvents((prev) => {
                      const next = new Set(prev);
                      if (next.has(-1)) next.delete(-1);
                      else next.add(-1);
                      return next;
                    });
                  }}
                  className="w-full px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-[var(--re-brand)]/10 transition-colors"
                >
                  <div className="flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-[var(--re-brand)]" />
                    <span className="text-[0.8rem] font-semibold text-[var(--re-brand)]">
                      What RegEngine Normalized
                    </span>
                    <span className="text-[0.65rem] px-1.5 py-0.5 rounded-full bg-[var(--re-brand)]/15 text-[var(--re-brand)] font-mono">
                      {result.normalizations.length}
                    </span>
                  </div>
                  {expandedEvents.has(-1)
                    ? <ChevronUp className="w-4 h-4 text-[var(--re-brand)]" />
                    : <ChevronDown className="w-4 h-4 text-[var(--re-brand)]" />}
                </button>

                {expandedEvents.has(-1) && (
                  <div className="border-t border-[var(--re-brand)]/10 px-4 py-3">
                    {(() => {
                      const grouped: Record<string, NormalizationAction[]> = {};
                      for (const n of result.normalizations!) {
                        const label = n.action_type === 'header_alias' ? 'Headers Mapped'
                          : n.action_type === 'uom_normalize' ? 'Units Standardized'
                          : n.action_type === 'cte_type_normalize' ? 'CTE Types Resolved'
                          : 'Other';
                        (grouped[label] ??= []).push(n);
                      }
                      return Object.entries(grouped).map(([label, items]) => (
                        <div key={label} className="mb-3 last:mb-0">
                          <div className="text-[0.65rem] font-medium text-[var(--re-text-muted)] uppercase tracking-wider mb-1.5">
                            {label}
                          </div>
                          <div className="space-y-1">
                            {items.map((n, i) => (
                              <div key={i} className="flex items-center gap-2 text-[0.7rem]">
                                <code className="px-1.5 py-0.5 rounded bg-red-500/10 text-red-400 font-mono text-[0.65rem]">
                                  {n.original}
                                </code>
                                <ArrowRight className="w-3 h-3 text-[var(--re-text-disabled)]" />
                                <code className="px-1.5 py-0.5 rounded bg-green-500/10 text-green-400 font-mono text-[0.65rem]">
                                  {n.normalized}
                                </code>
                              </div>
                            ))}
                          </div>
                        </div>
                      ));
                    })()}
                  </div>
                )}
              </div>
            )}

            {/* Status Banner */}
            {result.submission_blocked && (
              <div className="rounded-lg border-2 border-re-danger/30 bg-re-danger-muted0/10 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <ShieldAlert className="w-5 h-5 text-re-danger" />
                  <span className="text-[0.8rem] font-semibold text-re-danger">
                    FDA SUBMISSION BLOCKED — {result.blocking_reasons.length} critical defect{result.blocking_reasons.length !== 1 ? 's' : ''}
                  </span>
                </div>
                <ul className="space-y-1">
                  {result.blocking_reasons.slice(0, 10).map((reason, i) => (
                    <li key={i} className="text-[0.65rem] text-re-danger flex items-start gap-1.5">
                      <XCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!result.submission_blocked && result.non_compliant_events === 0 && (
              <div className="rounded-lg border-2 border-re-brand/30 bg-re-brand-muted p-4">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-re-brand" />
                  <span className="text-[0.8rem] font-semibold text-re-brand">
                    ALL EVENTS COMPLIANT — Ready for FDA submission
                  </span>
                </div>
              </div>
            )}

            {!result.submission_blocked && result.non_compliant_events > 0 && (
              <div className="rounded-lg border-2 border-re-warning/30 bg-re-warning-muted0/10 p-4">
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-5 h-5 text-re-warning" />
                  <span className="text-[0.8rem] font-semibold text-re-warning">
                    {result.non_compliant_events} event{result.non_compliant_events !== 1 ? 's' : ''} need attention
                  </span>
                </div>
              </div>
            )}

            {/* Per-Event Results */}
            <div className="space-y-2">
              {result.events.map((ev) => (
                <div
                  key={ev.event_index}
                  className={`rounded-lg border ${ev.compliant ? 'border-re-brand/20' : 'border-re-danger/20'}`}
                >
                  <button
                    onClick={() => toggleEvent(ev.event_index)}
                    className="w-full px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-[var(--re-surface-elevated)]/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      {ev.compliant
                        ? <CheckCircle2 className="w-4 h-4 text-re-brand" />
                        : <XCircle className="w-4 h-4 text-re-danger" />}
                      <span className="font-mono text-[0.75rem] font-medium text-[var(--re-text-primary)]">
                        {ev.traceability_lot_code}
                      </span>
                      <span className="text-[0.65rem] text-[var(--re-text-muted)] bg-[var(--re-surface-elevated)] px-2 py-0.5 rounded">
                        {ev.cte_type}
                      </span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-[0.6rem] text-[var(--re-text-disabled)]">
                        {ev.rules_passed}/{ev.rules_evaluated} passed
                      </span>
                      {expandedEvents.has(ev.event_index)
                        ? <ChevronUp className="w-4 h-4 text-[var(--re-text-disabled)]" />
                        : <ChevronDown className="w-4 h-4 text-[var(--re-text-disabled)]" />}
                    </div>
                  </button>

                  {expandedEvents.has(ev.event_index) && (
                    <div className="border-t border-[var(--re-surface-border)] px-4 py-3 space-y-2">
                      {ev.kde_errors.length > 0 && (
                        <div className="space-y-1">
                          <span className="text-[0.65rem] font-medium text-re-warning">KDE Validation Errors:</span>
                          {ev.kde_errors.map((err, j) => (
                            <div key={j} className="text-[0.65rem] text-re-warning flex items-start gap-1.5 ml-2">
                              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                              {err}
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="space-y-1">
                        {ev.all_results
                          .filter((r) => r.result === 'fail' || r.result === 'warn')
                          .map((r, j) => (
                            <div
                              key={j}
                              className={`flex items-start gap-2 text-[0.65rem] ${
                                r.result === 'fail' ? 'text-re-danger' : 'text-re-warning'
                              }`}
                            >
                              {r.result === 'fail'
                                ? <XCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                                : <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />}
                              <div>
                                <span className="font-medium">{r.rule_title}</span>
                                {r.citation && (
                                  <span className="text-[var(--re-text-disabled)] ml-1">({r.citation})</span>
                                )}
                                {r.why_failed && (
                                  <div className="text-[0.6rem] opacity-80 mt-0.5">{r.why_failed}</div>
                                )}
                              </div>
                            </div>
                          ))}
                        {ev.all_results.filter((r) => r.result === 'pass').length > 0 && (
                          <div className="text-[0.65rem] text-re-brand flex items-center gap-1">
                            <CheckCircle2 className="w-3 h-3" />
                            {ev.all_results.filter((r) => r.result === 'pass').length} rules passed
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* CTA */}
            <div className="rounded-lg border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/5 p-4 text-center">
              <p className="text-[0.8rem] font-semibold text-[var(--re-brand)] mb-2">
                Ready to automate FSMA 204 compliance?
              </p>
              <a
                href="/#sandbox"
                className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-5 py-2 rounded-lg text-[0.8rem] font-semibold transition-all hover:bg-[var(--re-brand-dark)]"
              >
                Try Your Own Data
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
