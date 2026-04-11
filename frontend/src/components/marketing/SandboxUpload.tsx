'use client';

import { useState, useRef } from 'react';
import {
  AlertTriangle, CheckCircle2, Loader2, Upload, XCircle,
  ShieldAlert, ChevronDown, ChevronUp, Download, Info, Pencil,
} from 'lucide-react';
import { usePostHog } from 'posthog-js/react';
import { SandboxGrid } from './sandbox-grid';
import { SandboxResultsCTA } from './sandbox-grid/SandboxResultsCTA';

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
  evidence?: Record<string, unknown>[] | null;
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
  duplicate_warnings?: string[];
  entity_warnings?: string[];
}

export function SandboxUpload() {
  const [csvText, setCsvText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<SandboxResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set());
  const [showGrid, setShowGrid] = useState(false);
  const posthog = usePostHog();

  function trackSandbox(event: string, metadata: Record<string, unknown> = {}) {
    posthog.capture(`SANDBOX_${event}`, {
      ...metadata,
      timestamp: new Date().toISOString(),
    });
  }

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
      trackSandbox('EVALUATE', {
        event_count: data.total_events,
        compliant: data.compliant_events,
        non_compliant: data.non_compliant_events,
        has_failures: data.non_compliant_events > 0,
        rule_failures: data.total_rule_failures,
      });
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

  function handleDownloadReport() {
    if (!result) return;
    const nonCompliantEvents = result.events.filter((ev) => !ev.compliant);
    const reportDate = new Date().toLocaleString();

    const nonCompliantHtml = nonCompliantEvents
      .map(
        (ev) => `
      <div style="border:1px solid #e5e7eb;border-radius:8px;padding:16px;margin-bottom:12px;">
        <h3 style="margin:0 0 8px;font-size:14px;color:#1f2937;">
          ${ev.traceability_lot_code} &mdash; ${ev.cte_type}
        </h3>
        <p style="margin:0 0 8px;font-size:12px;color:#6b7280;">Product: ${ev.product_description}</p>
        ${ev.all_results
          .filter((r) => r.result === 'fail')
          .map(
            (r) => `
          <div style="border-left:3px solid #ef4444;padding-left:10px;margin-bottom:8px;">
            <div style="font-size:12px;font-weight:600;color:#dc2626;">${r.rule_title}</div>
            ${r.citation ? `<div style="font-size:11px;color:#6b7280;">Citation: ${r.citation}</div>` : ''}
            ${r.why_failed ? `<div style="font-size:11px;color:#374151;margin-top:2px;">${r.why_failed}</div>` : ''}
            ${r.remediation ? `<div style="font-size:11px;color:#4b5563;font-style:italic;margin-top:2px;">Remediation: ${r.remediation}</div>` : ''}
          </div>`
          )
          .join('')}
      </div>`
      )
      .join('');

    const blockedHtml = result.submission_blocked
      ? `<div style="background:#fef2f2;border:2px solid #fca5a5;border-radius:8px;padding:16px;margin-bottom:20px;">
          <h2 style="margin:0 0 8px;font-size:16px;color:#dc2626;">FDA SUBMISSION BLOCKED</h2>
          <ul style="margin:0;padding-left:20px;">
            ${result.blocking_reasons.map((r) => `<li style="font-size:12px;color:#dc2626;margin-bottom:4px;">${r}</li>`).join('')}
          </ul>
        </div>`
      : '';

    const html = `<!DOCTYPE html>
<html><head><title>RegEngine FSMA 204 Compliance Report</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 800px; margin: 0 auto; padding: 40px 24px; color: #1f2937; }
  @media print { body { padding: 20px; } }
</style>
</head><body>
<div style="border-bottom:2px solid #4f46e5;padding-bottom:12px;margin-bottom:24px;">
  <h1 style="margin:0;font-size:22px;color:#4f46e5;">RegEngine FSMA 204 Compliance Report</h1>
  <p style="margin:4px 0 0;font-size:12px;color:#6b7280;">Generated: ${reportDate}</p>
</div>

<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:24px;">
  <div style="background:#f9fafb;border-radius:8px;padding:12px;text-align:center;">
    <div style="font-size:24px;font-weight:700;">${result.total_events}</div>
    <div style="font-size:11px;color:#6b7280;">Total Events</div>
  </div>
  <div style="background:#f0fdf4;border-radius:8px;padding:12px;text-align:center;">
    <div style="font-size:24px;font-weight:700;color:#16a34a;">${result.compliant_events}</div>
    <div style="font-size:11px;color:#6b7280;">Compliant</div>
  </div>
  <div style="background:#fef2f2;border-radius:8px;padding:12px;text-align:center;">
    <div style="font-size:24px;font-weight:700;color:#dc2626;">${result.non_compliant_events}</div>
    <div style="font-size:11px;color:#6b7280;">Non-Compliant</div>
  </div>
  <div style="background:#fffbeb;border-radius:8px;padding:12px;text-align:center;">
    <div style="font-size:24px;font-weight:700;color:#d97706;">${result.total_rule_failures}</div>
    <div style="font-size:11px;color:#6b7280;">Rule Failures</div>
  </div>
</div>

${blockedHtml}

${nonCompliantEvents.length > 0 ? `<h2 style="font-size:16px;margin-bottom:12px;">Non-Compliant Events</h2>${nonCompliantHtml}` : ''}

<div style="border-top:1px solid #e5e7eb;margin-top:32px;padding-top:12px;text-align:center;">
  <p style="font-size:11px;color:#9ca3af;">Generated by RegEngine &mdash; www.regengine.co</p>
</div>
</body></html>`;

    const reportWindow = window.open('', '_blank');
    if (reportWindow) {
      reportWindow.document.write(html);
      reportWindow.document.close();
      reportWindow.focus();
      setTimeout(() => reportWindow.print(), 300);
    }
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
                <>Evaluate Against FSMA 204 Rules</>
              )}
            </button>
            <span className="text-[0.65rem] text-[var(--re-text-disabled)]">
              No data stored. Results are ephemeral.
            </span>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="mx-4 mb-4 rounded-lg border border-re-danger/20 bg-re-danger-muted0/5 p-3">
            <div className="flex items-center gap-2">
              <XCircle className="w-4 h-4 text-re-danger" />
              <span className="text-[0.75rem] text-re-danger">{error}</span>
            </div>
          </div>
        )}

        {/* Grid Editor Mode */}
        {result && showGrid && (
          <div className="border-t border-[var(--re-surface-border)]">
            <SandboxGrid
              initialCsv={csvText}
              initialResult={result}
              onBack={() => setShowGrid(false)}
            />
          </div>
        )}

        {/* Results */}
        {result && !showGrid && (
          <div className="border-t border-[var(--re-surface-border)] p-4 space-y-4">
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

            {/* Actions Row */}
            <div className="flex items-center justify-between">
              {result.non_compliant_events > 0 && (
                <button
                  onClick={() => { trackSandbox('OPEN_GRID', { defect_count: result.non_compliant_events }); setShowGrid(true); }}
                  className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-4 py-2 rounded-lg text-[0.75rem] font-semibold transition-all hover:bg-[var(--re-brand-dark)] cursor-pointer"
                >
                  <Pencil className="w-4 h-4" />
                  Fix Issues in Spreadsheet
                </button>
              )}
              <div className="ml-auto">
                <button
                  onClick={() => { trackSandbox('REPORT_DL'); handleDownloadReport(); }}
                  className="inline-flex items-center gap-2 bg-white border border-re-border text-re-text-disabled px-4 py-2 rounded-lg text-[0.75rem] font-medium transition-all hover:bg-re-surface-card cursor-pointer"
                >
                  <Download className="w-4 h-4" />
                  Download Compliance Report
                </button>
              </div>
            </div>

            {/* Blocking Banner */}
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
                    {result.non_compliant_events} event{result.non_compliant_events !== 1 ? 's' : ''} need{result.non_compliant_events === 1 ? 's' : ''} attention — review issues below
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
                    ev.compliant ? 'border-re-brand/20' : 'border-re-danger/20'
                  }`}
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
                          <span className="text-[0.65rem] font-medium text-re-warning">KDE Validation Errors:</span>
                          {ev.kde_errors.map((err, j) => (
                            <div key={j} className="text-[0.65rem] text-re-warning flex items-start gap-1.5 ml-2">
                              <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                              {err}
                            </div>
                          ))}
                        </div>
                      )}

                      {/* Rule Results — grouped by Structural vs Relational, failures first */}
                      {(() => {
                        const relationalCategories = new Set(['temporal_ordering', 'quantity_consistency']);
                        const isRelational = (r: RuleResult) => relationalCategories.has(r.category) ||
                          r.category === 'lot_linkage' && (r.rule_title.includes('Identity') || r.rule_title.includes('Mass'));

                        const failed = ev.all_results.filter((r) => r.result === 'fail');
                        const warned = ev.all_results.filter((r) => r.result === 'warn');
                        const passed = ev.all_results.filter((r) => r.result === 'pass');
                        const skipped = ev.all_results.filter((r) => r.result === 'skip');

                        const structuralFailed = failed.filter((r) => !isRelational(r));
                        const relationalFailed = failed.filter((r) => isRelational(r));
                        const structuralWarned = warned.filter((r) => !isRelational(r));
                        const relationalWarned = warned.filter((r) => isRelational(r));

                        const renderRule = (rule: RuleResult, j: number) => (
                          <div
                            key={j}
                            className={`flex items-start gap-2 text-[0.65rem] ${
                              rule.result === 'pass' ? 'text-re-brand' :
                              rule.result === 'fail' ? 'text-re-danger' :
                              rule.result === 'warn' ? 'text-re-warning' :
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
                        );

                        return (
                          <div className="space-y-2">
                            {/* Relational integrity failures (cross-event logic) */}
                            {(relationalFailed.length > 0 || relationalWarned.length > 0) && (
                              <div className="space-y-1">
                                <span className="text-[0.65rem] font-medium text-re-danger flex items-center gap-1">
                                  <ShieldAlert className="w-3 h-3" />
                                  Supply Chain Integrity ({relationalFailed.length + relationalWarned.length}):
                                </span>
                                {[...relationalFailed, ...relationalWarned].map(renderRule)}
                              </div>
                            )}

                            {/* Structural failures (missing/malformed data) */}
                            {(structuralFailed.length > 0 || structuralWarned.length > 0) && (
                              <div className="space-y-1">
                                <span className="text-[0.65rem] font-medium text-re-warning flex items-center gap-1">
                                  <AlertTriangle className="w-3 h-3" />
                                  Missing Data ({structuralFailed.length + structuralWarned.length}):
                                </span>
                                {[...structuralFailed, ...structuralWarned].map(renderRule)}
                              </div>
                            )}

                            {/* Passed rules */}
                            {passed.length > 0 && (
                              <div className="space-y-1">
                                <span className="text-[0.65rem] font-medium text-re-brand flex items-center gap-1">
                                  <CheckCircle2 className="w-3 h-3" />
                                  Passed ({passed.length}):
                                </span>
                                {passed.map(renderRule)}
                              </div>
                            )}

                            {skipped.length > 0 && (
                              <div className="space-y-1">
                                {skipped.map(renderRule)}
                              </div>
                            )}
                          </div>
                        );
                      })()}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Duplicate Warnings */}
            {result.duplicate_warnings && result.duplicate_warnings.length > 0 && (
              <div className="rounded-lg border border-re-warning/30 bg-re-warning-muted0/10 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="w-4 h-4 text-re-warning" />
                  <span className="text-[0.75rem] font-semibold text-re-warning">Duplicate Warnings</span>
                </div>
                <ul className="space-y-1">
                  {result.duplicate_warnings.map((w, i) => (
                    <li key={i} className="text-[0.65rem] text-re-warning flex items-start gap-1.5">
                      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      {w}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Entity Warnings */}
            {result.entity_warnings && result.entity_warnings.length > 0 && (
              <div className="rounded-lg border border-re-warning/30 bg-re-warning-muted0/10 p-4">
                <div className="flex items-center gap-2 mb-2">
                  <AlertTriangle className="w-4 h-4 text-re-warning" />
                  <span className="text-[0.75rem] font-semibold text-re-warning">Entity Warnings</span>
                </div>
                <ul className="space-y-1">
                  {result.entity_warnings.map((w, i) => (
                    <li key={i} className="text-[0.65rem] text-re-warning flex items-start gap-1.5">
                      <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                      {w}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Fix and Re-Upload Guidance */}
            {result.non_compliant_events > 0 && (
              <div className="rounded-lg border border-indigo-500/30 bg-indigo-500/10 p-4">
                <div className="flex items-center gap-2 mb-3">
                  <Info className="w-4 h-4 text-indigo-400" />
                  <span className="text-[0.8rem] font-semibold text-indigo-300">How to Fix These Issues</span>
                </div>
                <ol className="space-y-2 ml-1">
                  <li className="flex items-start gap-2 text-[0.7rem] text-[var(--re-text-secondary)]">
                    <span className="bg-indigo-500/20 text-indigo-300 rounded-full w-5 h-5 flex items-center justify-center text-[0.6rem] font-bold flex-shrink-0 mt-0.5">1</span>
                    <span>Review the failed rules above &mdash; each includes the specific CFR citation and what&apos;s missing</span>
                  </li>
                  <li className="flex items-start gap-2 text-[0.7rem] text-[var(--re-text-secondary)]">
                    <span className="bg-indigo-500/20 text-indigo-300 rounded-full w-5 h-5 flex items-center justify-center text-[0.6rem] font-bold flex-shrink-0 mt-0.5">2</span>
                    <span>Update your CSV to add the missing fields or correct formatting</span>
                  </li>
                  <li className="flex items-start gap-2 text-[0.7rem] text-[var(--re-text-secondary)]">
                    <span className="bg-indigo-500/20 text-indigo-300 rounded-full w-5 h-5 flex items-center justify-center text-[0.6rem] font-bold flex-shrink-0 mt-0.5">3</span>
                    <span>Paste your corrected CSV above and re-evaluate</span>
                  </li>
                </ol>
                <div className="mt-3 pt-3 border-t border-indigo-500/20">
                  <a
                    href="/onboarding/bulk-upload"
                    className="text-[0.7rem] text-indigo-400 hover:text-indigo-300 hover:underline transition-colors"
                  >
                    Ready to commit your data? Go to Bulk Upload &rarr;
                  </a>
                </div>
              </div>
            )}

            {/* Conversion CTA */}
            {result.non_compliant_events > 0 && (
              <SandboxResultsCTA
                mode="failures"
                defectCount={result.non_compliant_events}
                eventCount={result.total_events}
                onTrack={trackSandbox}
              />
            )}
            {result.non_compliant_events === 0 && result.total_events > 0 && (
              <SandboxResultsCTA
                mode="all_clear"
                eventCount={result.total_events}
                onTrack={trackSandbox}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
