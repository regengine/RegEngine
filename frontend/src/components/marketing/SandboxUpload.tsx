'use client';

import { useState } from 'react';
import {
  AlertTriangle, CheckCircle2, Loader2, Upload, XCircle,
  ShieldAlert, ChevronDown, ChevronUp,
} from 'lucide-react';

const SAMPLE_CSV = `cte_type,traceability_lot_code,product_description,quantity,unit_of_measure,location_name,timestamp,harvest_date,reference_document,cooling_date,ship_date,ship_from_location,ship_to_location,tlc_source_reference,receive_date,receiving_location,immediate_previous_source
harvesting,LOT-2026-001,Romaine Lettuce,2000,lbs,Valley Fresh Farms,2026-03-12T08:00:00Z,2026-03-12,,,,,,,,,
shipping,LOT-2026-001,Romaine Lettuce,2000,lbs,Valley Fresh DC,2026-03-13T06:00:00Z,,BOL-4421,,,Valley Fresh Farms,FreshCo Distribution,Valley Fresh Farms LLC,,,
receiving,LOT-2026-001,Romaine Lettuce,1900,lbs,FreshCo Distribution,2026-03-13T14:00:00Z,,INV-8832,,,,,,2026-03-13,FreshCo DC East,Valley Fresh Farms LLC`;

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

interface SandboxResult {
  total_events: number;
  compliant_events: number;
  non_compliant_events: number;
  total_kde_errors: number;
  total_rule_failures: number;
  submission_blocked: boolean;
  blocking_reasons: string[];
  events: EventEvaluation[];
}

export function SandboxUpload() {
  const [csvText, setCsvText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<SandboxResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set());

  function loadSample() {
    setCsvText(SAMPLE_CSV);
    setResult(null);
    setError(null);
  }

  async function evaluate() {
    if (!csvText.trim()) return;
    setIsLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch('/api/ingestion/api/v1/sandbox/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv: csvText }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data: SandboxResult = await res.json();
      setResult(data);
      // Auto-expand non-compliant events
      const nonCompliant = new Set<number>();
      data.events.forEach((ev) => {
        if (!ev.compliant) nonCompliant.add(ev.event_index);
      });
      setExpandedEvents(nonCompliant);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Evaluation failed');
    } finally {
      setIsLoading(false);
    }
  }

  function toggleEvent(index: number) {
    setExpandedEvents((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  return (
    <div className="w-full">
      <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden">
        {/* Header */}
        <div className="px-4 py-3 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Upload className="w-4 h-4 text-[var(--re-brand)]" />
            <span className="text-[0.8rem] font-semibold text-[var(--re-text-primary)]">
              Try Your Own Data
            </span>
          </div>
          <button
            onClick={loadSample}
            className="text-[0.7rem] text-[var(--re-brand)] hover:underline cursor-pointer"
          >
            Load sample CSV
          </button>
        </div>

        {/* Input */}
        <div className="p-4">
          <textarea
            value={csvText}
            onChange={(e) => { setCsvText(e.target.value); setResult(null); setError(null); }}
            placeholder="Paste your CSV here — include headers like cte_type, traceability_lot_code, product_description, quantity, unit_of_measure..."
            rows={6}
            className="w-full bg-[var(--re-surface-base)] border border-[var(--re-surface-border)] rounded-lg p-3 font-mono text-[0.7rem] text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)]/30 resize-y"
          />

          <div className="flex items-center gap-3 mt-3">
            <button
              onClick={evaluate}
              disabled={isLoading || !csvText.trim()}
              className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-5 py-2 rounded-lg text-[0.8rem] font-semibold transition-all hover:bg-[var(--re-brand-dark)] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Evaluating...
                </>
              ) : (
                <>Evaluate Against 25 FSMA Rules</>
              )}
            </button>
            <span className="text-[0.65rem] text-[var(--re-text-disabled)]">
              No data stored. Results are ephemeral.
            </span>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mx-4 mb-4 rounded-lg border border-red-500/20 bg-red-500/5 p-3">
            <div className="flex items-center gap-2">
              <XCircle className="w-4 h-4 text-red-400" />
              <span className="text-[0.75rem] text-red-400">{error}</span>
            </div>
          </div>
        )}

        {/* Results */}
        {result && (
          <div className="border-t border-[var(--re-surface-border)] p-4 space-y-4">
            {/* Summary Bar */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: 'Events', value: result.total_events, color: 'text-[var(--re-text-primary)]' },
                { label: 'Compliant', value: result.compliant_events, color: 'text-emerald-400' },
                { label: 'Non-compliant', value: result.non_compliant_events, color: result.non_compliant_events > 0 ? 'text-red-400' : 'text-[var(--re-text-primary)]' },
                { label: 'Rule Failures', value: result.total_rule_failures, color: result.total_rule_failures > 0 ? 'text-amber-400' : 'text-[var(--re-text-primary)]' },
              ].map((stat) => (
                <div key={stat.label} className="bg-[var(--re-surface-elevated)] rounded-lg p-3 text-center">
                  <div className={`text-xl font-bold font-mono ${stat.color}`}>{stat.value}</div>
                  <div className="text-[0.65rem] text-[var(--re-text-muted)]">{stat.label}</div>
                </div>
              ))}
            </div>

            {/* Blocking Banner */}
            {result.submission_blocked && (
              <div className="rounded-lg border-2 border-red-500/30 bg-red-500/10 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <ShieldAlert className="w-5 h-5 text-red-400" />
                  <span className="text-[0.8rem] font-semibold text-red-400">
                    FDA SUBMISSION BLOCKED — {result.blocking_reasons.length} critical defect{result.blocking_reasons.length !== 1 ? 's' : ''}
                  </span>
                </div>
                <ul className="space-y-1">
                  {result.blocking_reasons.slice(0, 10).map((reason, i) => (
                    <li key={i} className="text-[0.65rem] text-red-400 flex items-start gap-1.5">
                      <XCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      {reason}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {!result.submission_blocked && (
              <div className="rounded-lg border-2 border-emerald-500/30 bg-emerald-500/10 p-4">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-400" />
                  <span className="text-[0.8rem] font-semibold text-emerald-400">
                    ALL EVENTS COMPLIANT — Ready for FDA submission
                  </span>
                </div>
              </div>
            )}

            {/* Per-Event Results */}
            <div className="space-y-2">
              {result.events.map((ev) => (
                <div
                  key={ev.event_index}
                  className={`rounded-lg border ${
                    ev.compliant ? 'border-emerald-500/20' : 'border-red-500/20'
                  }`}
                >
                  <button
                    onClick={() => toggleEvent(ev.event_index)}
                    className="w-full px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-[var(--re-surface-elevated)]/50 transition-colors"
                  >
                    <div className="flex items-center gap-2">
                      {ev.compliant
                        ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        : <XCircle className="w-4 h-4 text-red-400" />}
                      <span className="font-mono text-[0.75rem] font-medium text-[var(--re-text-primary)]">
                        {ev.traceability_lot_code}
                      </span>
                      <span className="text-[0.65rem] text-[var(--re-text-muted)] bg-[var(--re-surface-elevated)] px-2 py-0.5 rounded">
                        {ev.cte_type}
                      </span>
                      <span className="text-[0.65rem] text-[var(--re-text-secondary)]">
                        {ev.product_description}
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
                      {/* KDE Errors */}
                      {ev.kde_errors.length > 0 && (
                        <div className="space-y-1">
                          <span className="text-[0.65rem] font-medium text-amber-400">KDE Validation Errors:</span>
                          {ev.kde_errors.map((err, j) => (
                            <div key={j} className="text-[0.65rem] text-amber-400 flex items-start gap-1.5 ml-2">
                              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                              {err}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Rule Results */}
                      <div className="space-y-1">
                        {ev.all_results.map((rule, j) => (
                          <div
                            key={j}
                            className={`flex items-start gap-2 text-[0.65rem] ${
                              rule.result === 'pass' ? 'text-emerald-400' :
                              rule.result === 'fail' ? 'text-red-400' :
                              rule.result === 'warn' ? 'text-amber-400' :
                              'text-[var(--re-text-disabled)]'
                            }`}
                          >
                            {rule.result === 'pass'
                              ? <CheckCircle2 className="w-3 h-3 mt-0.5 flex-shrink-0" />
                              : rule.result === 'fail'
                              ? <XCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                              : <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />}
                            <div>
                              <span className="font-medium">{rule.rule_title}</span>
                              {rule.citation && (
                                <span className="text-[var(--re-text-disabled)] ml-1">({rule.citation})</span>
                              )}
                              {rule.why_failed && (
                                <div className="text-[0.6rem] opacity-80 mt-0.5">{rule.why_failed}</div>
                              )}
                              {rule.remediation && rule.result === 'fail' && (
                                <div className="text-[0.6rem] text-[var(--re-text-muted)] mt-0.5 italic">{rule.remediation}</div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
