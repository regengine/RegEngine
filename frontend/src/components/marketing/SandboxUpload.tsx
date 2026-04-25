'use client';

import { fetchWithCsrf } from '@/lib/fetch-with-csrf';
import { useState, useRef, useEffect, useCallback } from 'react';
import {
  AlertTriangle, CheckCircle2, Loader2, Upload, XCircle,
  ShieldAlert, ChevronDown, ChevronUp, Download, Info, Pencil,
  Database, FileUp, Clock, Sparkles, Share2, Check, Link2,
  X, File,
} from 'lucide-react';
import { usePostHog } from 'posthog-js/react';
import { SandboxGrid } from './sandbox-grid';
import { SandboxResultsCTA } from './sandbox-grid/SandboxResultsCTA';
import { generateComplianceReport } from './sandbox-grid/SandboxPdfReport';
import { NormalizationReview } from './NormalizationReview';
import { ExportLeadGate } from './sandbox-grid/ExportLeadGate';
import { SANDBOX_SAMPLES, SAMPLE_CSV_DEFAULT } from './sandbox-samples';

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

interface NormalizationAction {
  field: string;
  original: string;
  normalized: string;
  action_type: string;
  reasoning?: string;
  event_index?: number;
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

export function SandboxUpload() {
  const [csvText, setCsvText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [result, setResult] = useState<SandboxResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedEvents, setExpandedEvents] = useState<Set<number>>(new Set());
  const [showGrid, setShowGrid] = useState(false);
  const [sampleMenuOpen, setSampleMenuOpen] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [rateLimitedUntil, setRateLimitedUntil] = useState<number | null>(null);
  const [rateLimitCountdown, setRateLimitCountdown] = useState(0);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [isSharing, setIsSharing] = useState(false);
  const [shareCopied, setShareCopied] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState<{ name: string; lines: number; content: string }[]>([]);
  const [includeCustomRules, setIncludeCustomRules] = useState(false);
  const [erpPreset, setErpPreset] = useState<string>('');
  const [leadGateOpen, setLeadGateOpen] = useState(false);
  const [leadGateAction, setLeadGateAction] = useState<'pdf' | 'share' | null>(null);
  const sampleMenuRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const posthog = usePostHog();

  const MAX_FILE_SIZE = 2 * 1024 * 1024; // 2MB

  // Rate limit countdown timer
  useEffect(() => {
    if (!rateLimitedUntil) return;
    const tick = () => {
      const remaining = Math.ceil((rateLimitedUntil - Date.now()) / 1000);
      if (remaining <= 0) {
        setRateLimitedUntil(null);
        setRateLimitCountdown(0);
      } else {
        setRateLimitCountdown(remaining);
      }
    };
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, [rateLimitedUntil]);

  // Merge multiple CSV files: use first file's headers, skip headers on subsequent files
  function mergeCsvFiles(files: { content: string }[]): string {
    if (files.length === 0) return '';
    if (files.length === 1) return files[0].content;

    const lines0 = files[0].content.trim().split('\n');
    const header = lines0[0];
    const merged = [header];

    for (const f of files) {
      const lines = f.content.trim().split('\n');
      // Skip header row if it looks like the same headers
      const startIdx = lines[0]?.toLowerCase().includes('cte') || lines[0]?.toLowerCase().includes('lot') ? 1 : 0;
      for (let i = startIdx; i < lines.length; i++) {
        if (lines[i].trim()) merged.push(lines[i]);
      }
    }
    return merged.join('\n');
  }

  // File drop/pick handler — supports multiple files
  const handleFile = useCallback((file: File) => {
    if (file.size > MAX_FILE_SIZE) {
      setError(`File too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Sandbox limit is 2MB.`);
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const text = e.target?.result as string;
      const lines = text.trim().split('\n').length - 1; // exclude header

      setUploadedFiles((prev) => {
        if (prev.length >= 5) {
          setError('Maximum 5 files in sandbox.');
          return prev;
        }
        const next = [...prev, { name: file.name, lines, content: text }];
        const merged = mergeCsvFiles(next);
        setCsvText(merged);
        return next;
      });
      setResult(null);
      setError(null);
      trackSandbox('FILE_UPLOAD', { file_name: file.name, file_size: file.size });
    };
    reader.readAsText(file);
  }, []);

  // Close sample menu on outside click
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (sampleMenuRef.current && !sampleMenuRef.current.contains(e.target as Node)) {
        setSampleMenuOpen(false);
      }
    }
    if (sampleMenuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }
  }, [sampleMenuOpen]);

  function trackSandbox(event: string, metadata: Record<string, unknown> = {}) {
    posthog.capture(`SANDBOX_${event}`, {
      ...metadata,
      timestamp: new Date().toISOString(),
    });
  }

  function loadSample(sampleId?: string) {
    if (sampleId) {
      const sample = SANDBOX_SAMPLES.find((s) => s.id === sampleId);
      if (sample) {
        setCsvText(sample.csv);
        trackSandbox('LOAD_SAMPLE', { sample_id: sample.id, cte_type: sample.cteType, mess_level: sample.messLevel });
      }
    } else {
      setCsvText(SAMPLE_CSV_DEFAULT);
      trackSandbox('LOAD_SAMPLE', { sample_id: 'default' });
    }
    setResult(null);
    setError(null);
    setUploadedFiles([]);
    setSampleMenuOpen(false);
  }

  async function evaluate() {
    if (!csvText.trim()) return;
    setIsLoading(true);
    setError(null);
    setResult(null);
    setShareUrl(null);

    try {
      const res = await fetchWithCsrf('/api/ingestion/api/v1/sandbox/evaluate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          csv: csvText,
          include_custom_rules: includeCustomRules,
          ...(erpPreset ? { erp_preset: erpPreset } : {}),
        }),
      });

      if (res.status === 429) {
        const retryAfter = parseInt(res.headers.get('Retry-After') || '60', 10);
        setRateLimitedUntil(Date.now() + retryAfter * 1000);
        setIsLoading(false);
        return;
      }

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
    generateComplianceReport(result);
  }

  function handleApplyNormalizations(changes: { field: string; original: string; normalized: string; action_type: string }[]) {
    if (!csvText) return;
    let updated = csvText;

    for (const change of changes) {
      if (change.action_type === 'header_alias') {
        // Replace the column header in the first line
        const lines = updated.split('\n');
        if (lines.length > 0) {
          // Case-insensitive header replacement
          const headerRegex = new RegExp(
            `(?<=^|,)\\s*${change.original.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s*(?=,|$)`,
            'i',
          );
          lines[0] = lines[0].replace(headerRegex, change.normalized);
          updated = lines.join('\n');
        }
      } else if (change.action_type === 'cte_type_normalize') {
        // Replace CTE type values in data rows (not the header)
        const lines = updated.split('\n');
        for (let i = 1; i < lines.length; i++) {
          // Replace exact CTE type value in the row
          const cells = lines[i].split(',');
          for (let j = 0; j < cells.length; j++) {
            if (cells[j].trim().toLowerCase() === change.original.toLowerCase()) {
              cells[j] = cells[j].replace(new RegExp(change.original.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'i'), change.normalized);
            }
          }
          lines[i] = cells.join(',');
        }
        updated = lines.join('\n');
      }
    }

    setCsvText(updated);
    setResult(null);
    trackSandbox('NORMALIZATIONS_APPLIED', { count: changes.length });
  }

  async function handleShare() {
    if (!result || !csvText.trim()) return;
    setIsSharing(true);
    try {
      const res = await fetchWithCsrf('/api/ingestion/api/v1/sandbox/share', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv: csvText, result }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: 'Share failed' }));
        setError(err.detail || 'Share failed');
        return;
      }
      const data = await res.json();
      const fullUrl = `${window.location.origin}${data.share_url}`;
      setShareUrl(fullUrl);
      trackSandbox('SHARE', { share_id: data.share_id });
    } catch {
      setError('Failed to create share link');
    } finally {
      setIsSharing(false);
    }
  }

  function copyShareUrl() {
    if (!shareUrl) return;
    navigator.clipboard.writeText(shareUrl);
    setShareCopied(true);
    setTimeout(() => setShareCopied(false), 2000);
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
          <div className="relative" ref={sampleMenuRef}>
            <button
              onClick={() => setSampleMenuOpen(!sampleMenuOpen)}
              className="inline-flex items-center gap-1.5 text-[0.7rem] text-[var(--re-brand)] hover:underline cursor-pointer"
            >
              <Database className="w-3 h-3" />
              Load sample data
              <ChevronDown className={`w-3 h-3 transition-transform ${sampleMenuOpen ? 'rotate-180' : ''}`} />
            </button>

            {sampleMenuOpen && (
              <div className="absolute right-0 top-full mt-1 w-96 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-lg shadow-xl z-50 overflow-hidden">
                <div className="px-3 py-2 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)]">
                  <span className="text-[0.65rem] font-medium text-[var(--re-text-muted)] uppercase tracking-wider">
                    Choose a vendor scenario — see what RegEngine normalizes
                  </span>
                </div>
                <div className="max-h-96 overflow-y-auto">
                  {SANDBOX_SAMPLES.map((sample) => (
                    <button
                      key={sample.id}
                      onClick={() => loadSample(sample.id)}
                      className="w-full text-left px-3 py-2.5 hover:bg-[var(--re-surface-elevated)] transition-colors border-b border-[var(--re-surface-border)] last:border-b-0 cursor-pointer group"
                    >
                      <div className="flex items-center justify-between mb-0.5">
                        <span className="text-[0.75rem] font-medium text-[var(--re-text-primary)]">
                          {sample.label}
                        </span>
                        <span className={`text-[0.6rem] px-1.5 py-0.5 rounded font-medium shrink-0 ml-2 ${
                          sample.messLevel === 'Low' ? 'bg-green-500/10 text-green-400' :
                          sample.messLevel === 'Low–Medium' ? 'bg-green-500/10 text-green-400' :
                          sample.messLevel === 'Medium' ? 'bg-yellow-500/10 text-yellow-400' :
                          sample.messLevel === 'Medium–High' ? 'bg-orange-500/10 text-orange-400' :
                          sample.messLevel === 'High' ? 'bg-red-500/10 text-red-400' :
                          sample.messLevel === 'Very High' ? 'bg-red-600/10 text-red-500' :
                          sample.messLevel === 'Extreme' ? 'bg-purple-600/10 text-purple-400' :
                          'bg-indigo-500/10 text-indigo-400'
                        }`}>
                          {sample.messLevel}
                        </span>
                      </div>
                      <div className="text-[0.6rem] text-[var(--re-text-muted)]">
                        {sample.persona} — {sample.messDescription}
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1.5 opacity-60 group-hover:opacity-100 transition-opacity">
                        {sample.normalizationHits.slice(0, 3).map((hit, i) => (
                          <span
                            key={i}
                            className="text-[0.55rem] px-1.5 py-0.5 rounded bg-[var(--re-surface-base)] text-[var(--re-text-disabled)] border border-[var(--re-surface-border)]"
                          >
                            {hit.split('(')[0].trim()}
                          </span>
                        ))}
                        {sample.normalizationHits.length > 3 && (
                          <span className="text-[0.55rem] px-1.5 py-0.5 text-[var(--re-text-disabled)]">
                            +{sample.normalizationHits.length - 3} more
                          </span>
                        )}
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Input */}
        <div className="p-4">
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv,.tsv,.txt"
            multiple
            className="hidden"
            onChange={(e) => {
              const files = e.target.files;
              if (files) {
                for (let i = 0; i < files.length; i++) handleFile(files[i]);
              }
              e.target.value = '';
            }}
          />
          <div
            onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={(e) => {
              e.preventDefault();
              setIsDragOver(false);
              const files = e.dataTransfer.files;
              for (let i = 0; i < files.length; i++) handleFile(files[i]);
            }}
            className="relative"
          >
            {isDragOver && (
              <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg border-2 border-dashed border-[var(--re-brand)] bg-[var(--re-brand)]/10 backdrop-blur-sm">
                <div className="flex items-center gap-2 text-[var(--re-brand)] font-semibold text-sm">
                  <FileUp className="w-5 h-5" />
                  Drop your CSV here
                </div>
              </div>
            )}
            <textarea
              value={csvText}
              onChange={(e) => { setCsvText(e.target.value); setResult(null); setError(null); }}
              placeholder="Paste your CSV here or drag-and-drop a .csv file — include headers like cte_type, traceability_lot_code, product_description, quantity, unit_of_measure..."
              rows={6}
              className="w-full bg-[var(--re-surface-base)] border border-[var(--re-surface-border)] rounded-lg p-3 font-mono text-[0.7rem] text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)]/30 resize-y"
            />
          </div>

          {/* Uploaded files strip */}
          {uploadedFiles.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-2">
              {uploadedFiles.map((f, i) => (
                <span
                  key={i}
                  className="inline-flex items-center gap-1 px-2 py-1 rounded bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] text-[0.6rem] text-[var(--re-text-secondary)]"
                >
                  <File className="w-3 h-3" />
                  {f.name}
                  <span className="text-[var(--re-text-disabled)]">({f.lines} rows)</span>
                  <button
                    onClick={() => {
                      setUploadedFiles((prev) => {
                        const next = prev.filter((_, j) => j !== i);
                        setCsvText(next.length > 0 ? mergeCsvFiles(next) : '');
                        return next;
                      });
                      setResult(null);
                    }}
                    className="ml-0.5 text-[var(--re-text-disabled)] hover:text-re-danger transition-colors"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
              {uploadedFiles.length >= 2 && (
                <span className="text-[0.6rem] text-[var(--re-text-disabled)] self-center">
                  {uploadedFiles.reduce((sum, f) => sum + f.lines, 0)} total rows
                </span>
              )}
            </div>
          )}

          <div className="flex items-center gap-3 mt-3">
            <button
              onClick={evaluate}
              disabled={isLoading || !csvText.trim() || !!rateLimitedUntil}
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
            <button
              onClick={() => fileInputRef.current?.click()}
              className="inline-flex items-center gap-1.5 text-[0.75rem] text-[var(--re-text-secondary)] hover:text-[var(--re-text-primary)] transition-colors cursor-pointer"
            >
              <FileUp className="w-3.5 h-3.5" />
              {uploadedFiles.length > 0 ? 'Add File' : 'Upload CSV'}
            </button>
            <select
              value={erpPreset}
              onChange={(e) => { setErpPreset(e.target.value); setResult(null); }}
              className="text-[0.7rem] bg-[var(--re-surface-base)] border border-[var(--re-surface-border)] rounded px-2 py-1 text-[var(--re-text-secondary)] cursor-pointer"
            >
              <option value="">Auto-detect columns</option>
              <option value="produce_pro">Produce Pro</option>
              <option value="sap_b1">SAP Business One</option>
              <option value="aptean">Aptean (Freshlynx)</option>
            </select>
            <label className="inline-flex items-center gap-1.5 text-[0.7rem] text-[var(--re-text-secondary)] cursor-pointer select-none">
              <input
                type="checkbox"
                checked={includeCustomRules}
                onChange={(e) => { setIncludeCustomRules(e.target.checked); setResult(null); }}
                className="w-3.5 h-3.5 rounded border-[var(--re-surface-border)] accent-[var(--re-brand)]"
              />
              Custom Rules
            </label>
            <span className="text-[0.65rem] text-[var(--re-text-disabled)] ml-auto">
              No data stored. Results are ephemeral.
            </span>
          </div>
        </div>

        {/* Rate Limit Warning */}
        {rateLimitedUntil && (
          <div className="mx-4 mb-4 rounded-lg border border-amber-500/30 bg-amber-500/10 p-3">
            <div className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-400" />
              <span className="text-[0.75rem] text-amber-300">
                Evaluation limit reached. Try again in <span className="font-mono font-bold">{rateLimitCountdown}s</span>
              </span>
            </div>
          </div>
        )}

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

            {/* Normalization Review — accept/reject individual, by event, or bulk */}
            {result.normalizations && result.normalizations.length > 0 && (
              <NormalizationReview
                normalizations={result.normalizations}
                onApply={handleApplyNormalizations}
              />
            )}

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
              <div className="ml-auto flex items-center gap-2">
                {shareUrl ? (
                  <button
                    onClick={copyShareUrl}
                    className="inline-flex items-center gap-2 bg-green-500/10 border border-green-500/30 text-green-400 px-4 py-2 rounded-lg text-[0.75rem] font-medium transition-all hover:bg-green-500/20 cursor-pointer"
                  >
                    {shareCopied ? <Check className="w-4 h-4" /> : <Link2 className="w-4 h-4" />}
                    {shareCopied ? 'Copied!' : 'Copy Share Link'}
                  </button>
                ) : (
                  <button
                    onClick={() => { setLeadGateAction('share'); setLeadGateOpen(true); }}
                    disabled={isSharing}
                    className="inline-flex items-center gap-2 bg-white border border-re-border text-re-text-disabled px-4 py-2 rounded-lg text-[0.75rem] font-medium transition-all hover:bg-re-surface-card cursor-pointer disabled:opacity-50"
                  >
                    {isSharing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Share2 className="w-4 h-4" />}
                    {isSharing ? 'Sharing...' : 'Share Results'}
                  </button>
                )}
                <button
                  onClick={() => { setLeadGateAction('pdf'); setLeadGateOpen(true); }}
                  className="inline-flex items-center gap-2 bg-white border border-re-border text-re-text-disabled px-4 py-2 rounded-lg text-[0.75rem] font-medium transition-all hover:bg-re-surface-card cursor-pointer"
                >
                  <Download className="w-4 h-4" />
                  PDF Report
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

                        const isCustom = (r: RuleResult) => r.category === 'custom_business_rule';
                        const structuralFailed = failed.filter((r) => !isRelational(r) && !isCustom(r));
                        const relationalFailed = failed.filter((r) => isRelational(r));
                        const structuralWarned = warned.filter((r) => !isRelational(r) && !isCustom(r));
                        const relationalWarned = warned.filter((r) => isRelational(r));
                        const customResults = [...failed.filter(isCustom), ...warned.filter(isCustom), ...passed.filter(isCustom)];

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

                            {/* Custom business rules */}
                            {customResults.length > 0 && (
                              <div className="space-y-1 border-t border-dashed border-[var(--re-surface-border)] pt-2 mt-2">
                                <span className="text-[0.65rem] font-medium text-purple-400 flex items-center gap-1">
                                  <Sparkles className="w-3 h-3" />
                                  Custom Business Rules ({customResults.length}):
                                </span>
                                {customResults.map(renderRule)}
                                <div className="text-[0.55rem] text-[var(--re-text-disabled)] italic mt-1">
                                  Build your own rules in RegEngine&apos;s rule builder &mdash; temperature thresholds, supplier certifications, and more
                                </div>
                              </div>
                            )}

                            {/* Passed rules */}
                            {passed.filter((r) => !isCustom(r)).length > 0 && (
                              <div className="space-y-1">
                                <span className="text-[0.65rem] font-medium text-re-brand flex items-center gap-1">
                                  <CheckCircle2 className="w-3 h-3" />
                                  Passed ({passed.filter((r) => !isCustom(r)).length}):
                                </span>
                                {passed.filter((r) => !isCustom(r)).map(renderRule)}
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

      {/* Lead gate for PDF download + share */}
      <ExportLeadGate
        open={leadGateOpen}
        onOpenChange={setLeadGateOpen}
        onExport={() => {
          if (leadGateAction === 'pdf') {
            trackSandbox('REPORT_DL');
            handleDownloadReport();
          } else if (leadGateAction === 'share') {
            handleShare();
          }
          setLeadGateAction(null);
        }}
        onTrack={trackSandbox}
        defectCount={result?.non_compliant_events}
        eventCount={result?.total_events}
      />
    </div>
  );
}
