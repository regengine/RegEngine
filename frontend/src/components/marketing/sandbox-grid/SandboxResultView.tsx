'use client';

// #2757 — extracted verbatim from the shared-result page so /sandbox and
// /sandbox/results/[id] render one diagnosis, not two that drift apart.
// Presentational only: no fetching, no analytics. Callers own those.

import {
  AlertTriangle, CheckCircle2, XCircle, ShieldAlert,
  ChevronDown, ChevronUp, Download, Sparkles, ArrowRight,
} from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { StatTile } from '@/components/ui/stat-tile';
import { generateComplianceReport } from '@/components/marketing/sandbox-grid/SandboxPdfReport';

// ---------------------------------------------------------------------------
// Types (mirror services/ingestion/app/sandbox/models.py)
// ---------------------------------------------------------------------------

export interface RuleResult {
  rule_title: string;
  severity: string;
  result: string;
  why_failed: string | null;
  citation: string | null;
  remediation: string | null;
  category: string;
}

export interface EventEvaluation {
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

export interface NormalizationAction {
  field: string;
  original: string;
  normalized: string;
  action_type: string;
}

export interface SandboxResult {
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

export function SandboxResultView({
  result,
  footer,
}: {
  result: SandboxResult;
  /** CTA slot rendered below the per-event list. */
  footer?: ReactNode;
}) {
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
    <Card>
      <CardHeader className="flex-col items-stretch gap-3 sm:flex-row sm:items-center">
        <CardTitle>FSMA 204 Sandbox Diagnosis</CardTitle>
        <Button
          className="w-fit shrink-0"
          variant="secondary"
          size="sm"
          onClick={() => generateComplianceReport(result)}
          leadingIcon={<Download strokeWidth={1.75} aria-hidden="true" />}
        >
          Download PDF
        </Button>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* Summary Bar */}
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <StatTile label="Events" value={result.total_events} />
          <StatTile label="Passed checks" value={result.compliant_events} />
          <StatTile label="Need work" value={result.non_compliant_events} />
          <StatTile label="Rule issues" value={result.total_rule_failures} />
        </div>

        {/* Normalization Diff */}
        {result.normalizations && result.normalizations.length > 0 && (
          <div className="overflow-hidden rounded-lg border border-re-border-subtle bg-re-surface-inset">
            <button
              type="button"
              aria-expanded={expandedEvents.has(-1)}
              onClick={() => {
                setExpandedEvents((prev) => {
                  const next = new Set(prev);
                  if (next.has(-1)) next.delete(-1);
                  else next.add(-1);
                  return next;
                });
              }}
              className="flex w-full cursor-pointer items-center justify-between px-4 py-3 text-left transition-colors duration-120 hover:bg-re-surface-card motion-reduce:transition-none"
            >
              <span className="flex items-center gap-2">
                <Sparkles className="h-4 w-4 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                <span className="text-ui font-medium text-re-text-primary">
                  What RegEngine Normalized
                </span>
                <Badge size="sm" mono>
                  {result.normalizations.length}
                </Badge>
              </span>
              {expandedEvents.has(-1)
                ? <ChevronUp className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                : <ChevronDown className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />}
            </button>

            {expandedEvents.has(-1) && (
              <div className="border-t border-re-border-subtle px-4 py-3">
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
                      <div className="mb-1.5 text-label text-re-text-muted">
                        {label}
                      </div>
                      <div className="space-y-1">
                        {items.map((n, i) => (
                          <div key={i} className="flex items-center gap-2">
                            <code className="rounded-sm border border-re-border-subtle bg-re-surface-card px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-tertiary">
                              {n.original}
                            </code>
                            <ArrowRight className="h-3.5 w-3.5 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                            <code className="rounded-sm border border-re-border-subtle bg-re-surface-card px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary">
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
          <Callout tone="danger" role="alert" icon={ShieldAlert}>
            <p className="font-medium text-re-text-primary">
              TEST RUN NEEDS CORRECTION: {result.blocking_reasons.length} blocker{result.blocking_reasons.length !== 1 ? 's' : ''}
            </p>
            <ul className="mt-2 space-y-1">
              {result.blocking_reasons.slice(0, 10).map((reason, i) => (
                <li key={i} className="flex items-start gap-1.5 text-small">
                  <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                  {reason}
                </li>
              ))}
            </ul>
          </Callout>
        )}

        {!result.submission_blocked && result.non_compliant_events === 0 && (
          <Callout tone="success">
            <p className="font-medium text-re-text-primary">
              SANDBOX CHECKS CLEAR: ready to save as a test run
            </p>
          </Callout>
        )}

        {!result.submission_blocked && result.non_compliant_events > 0 && (
          <Callout tone="warning">
            <p className="font-medium text-re-text-primary">
              {result.non_compliant_events} event{result.non_compliant_events !== 1 ? 's' : ''} need attention
            </p>
          </Callout>
        )}

        {/* Per-Event Results */}
        <div className="space-y-2">
          {result.events.map((ev) => (
            <div
              key={ev.event_index}
              className="rounded-lg border border-re-border"
            >
              <button
                type="button"
                aria-expanded={expandedEvents.has(ev.event_index)}
                onClick={() => toggleEvent(ev.event_index)}
                className="flex w-full cursor-pointer items-center justify-between gap-3 px-4 py-3 text-left transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none"
              >
                <span className="flex min-w-0 items-center gap-2">
                  {ev.compliant
                    ? <CheckCircle2 className="h-4 w-4 shrink-0 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                    : <XCircle className="h-4 w-4 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />}
                  <span className="truncate font-mono text-[0.8125rem] font-medium text-re-text-primary">
                    {ev.traceability_lot_code}
                  </span>
                  <Badge size="sm" mono className="shrink-0">
                    {ev.cte_type}
                  </Badge>
                </span>
                <span className="flex shrink-0 items-center gap-3">
                  <span className="text-small tabular-nums text-re-text-tertiary">
                    {ev.rules_passed}/{ev.rules_evaluated} passed
                  </span>
                  {expandedEvents.has(ev.event_index)
                    ? <ChevronUp className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                    : <ChevronDown className="h-4 w-4 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />}
                </span>
              </button>

              {expandedEvents.has(ev.event_index) && (
                <div className="space-y-3 border-t border-re-border-subtle px-4 py-3">
                  {ev.kde_errors.length > 0 && (
                    <div className="space-y-1">
                      <span className="text-ui font-medium text-re-text-primary">KDE Validation Errors:</span>
                      {ev.kde_errors.map((err, j) => (
                        <div key={j} className="ml-2 flex items-start gap-1.5 text-small text-re-text-secondary">
                          <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />
                          {err}
                        </div>
                      ))}
                    </div>
                  )}

                  <div className="space-y-1.5">
                    {ev.all_results
                      .filter((r) => r.result === 'fail' || r.result === 'warn')
                      .map((r, j) => (
                        <div
                          key={j}
                          className="flex items-start gap-2 text-small text-re-text-secondary"
                        >
                          {r.result === 'fail'
                            ? <XCircle className="mt-0.5 h-3 w-3 shrink-0 text-re-danger" strokeWidth={1.75} aria-hidden="true" />
                            : <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-re-warning" strokeWidth={1.75} aria-hidden="true" />}
                          <div>
                            <span className="font-medium text-re-text-primary">{r.rule_title}</span>
                            {r.citation && (
                              <span className="ml-1 font-mono text-re-text-tertiary">({r.citation})</span>
                            )}
                            {r.why_failed && (
                              <div className="mt-0.5 text-re-text-tertiary">{r.why_failed}</div>
                            )}
                          </div>
                        </div>
                      ))}
                    {ev.all_results.filter((r) => r.result === 'pass').length > 0 && (
                      <div className="flex items-center gap-1.5 text-small text-re-text-secondary">
                        <CheckCircle2 className="h-3 w-3 shrink-0 text-re-success" strokeWidth={1.75} aria-hidden="true" />
                        {ev.all_results.filter((r) => r.result === 'pass').length} rules passed
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>

        {footer}
      </CardContent>
    </Card>
  );
}
