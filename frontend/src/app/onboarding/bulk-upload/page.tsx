'use client';

import { useMemo, useState, type ChangeEvent } from 'react';
import Link from 'next/link';
import {
  ArrowRight, CheckCircle2, Download, FileSpreadsheet, Hash,
  Loader2, UploadCloud, ClipboardCheck, Search, ShieldCheck,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import { notifyDashboardRefresh } from '@/hooks/use-dashboard-refresh';
import type {
  SupplierBulkUploadCommitResponse,
  SupplierBulkUploadParseResponse,
  SupplierBulkUploadStatusResponse,
  SupplierBulkUploadValidateResponse,
} from '@/types/api';

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

const STEPS = [
  { label: 'Upload File', Icon: UploadCloud },
  { label: 'Preview', Icon: Search },
  { label: 'Validate', Icon: ClipboardCheck },
  { label: 'Commit', Icon: CheckCircle2 },
];

/* ── FSMA 204 client-side validation (no auth required) ── */

const VALID_EVENT_TYPES = new Set(['R', 'S', 'T', 'C', 'D', 'P', 'H']);
const EVENT_TYPE_LABELS: Record<string, string> = { R: 'Receiving', S: 'Shipping', T: 'Transforming', C: 'Cooling', D: 'Distribution', P: 'Initial Packing', H: 'Harvesting' };

const REQUIRED_COLUMNS = [
  'event_type', 'product_name', 'lot_number',
];
const RECOMMENDED_COLUMNS = [
  'event_datetime', 'product_code', 'quantity', 'unit',
  'origin_facility_code', 'origin_facility_name',
  'destination_facility_code', 'destination_facility_name',
];

interface ValidationIssue {
  severity: 'error' | 'warning';
  row?: number;
  column?: string;
  message: string;
}

interface ClientValidationResult {
  totalRows: number;
  columnsFound: string[];
  requiredColumnsPresent: string[];
  requiredColumnsMissing: string[];
  recommendedColumnsPresent: string[];
  recommendedColumnsMissing: string[];
  eventTypeCounts: Record<string, number>;
  invalidEventTypes: { row: number; value: string }[];
  issues: ValidationIssue[];
  completenessScore: number; // 0-100
  canProceed: boolean; // true if no errors (warnings ok)
  productNames: string[];
  lotNumbers: string[];
  facilityNames: string[];
  dateRange: { earliest: string | null; latest: string | null };
}

function validateCSVLocally(text: string): ClientValidationResult {
  const lines = text.trim().split('\n');
  const result: ClientValidationResult = {
    totalRows: 0, columnsFound: [], requiredColumnsPresent: [], requiredColumnsMissing: [],
    recommendedColumnsPresent: [], recommendedColumnsMissing: [], eventTypeCounts: {},
    invalidEventTypes: [], issues: [], completenessScore: 0, canProceed: true,
    productNames: [], lotNumbers: [], facilityNames: [], dateRange: { earliest: null, latest: null },
  };

  if (lines.length < 2) {
    result.issues.push({ severity: 'error', message: 'File contains no data rows.' });
    result.canProceed = false;
    return result;
  }

  const columns = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, '').toLowerCase());
  result.columnsFound = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
  const dataLines = lines.slice(1).filter(l => l.trim().length > 0);
  result.totalRows = dataLines.length;

  // Column presence checks
  for (const req of REQUIRED_COLUMNS) {
    if (columns.includes(req)) { result.requiredColumnsPresent.push(req); }
    else { result.requiredColumnsMissing.push(req); result.issues.push({ severity: 'error', column: req, message: `Required FSMA 204 column "${req}" is missing.` }); }
  }
  for (const rec of RECOMMENDED_COLUMNS) {
    if (columns.includes(rec)) { result.recommendedColumnsPresent.push(rec); }
    else { result.recommendedColumnsMissing.push(rec); result.issues.push({ severity: 'warning', column: rec, message: `Recommended column "${rec}" not found. Data may be incomplete for full FSMA 204 compliance.` }); }
  }

  // Index lookups
  const idx = (name: string) => columns.indexOf(name);
  const eventTypeIdx = idx('event_type');
  const productNameIdx = idx('product_name');
  const productCodeIdx = idx('product_code');
  const lotIdx = idx('lot_number');
  const datetimeIdx = idx('event_datetime');
  const origFacIdx = idx('origin_facility_name');
  const destFacIdx = idx('destination_facility_name');
  const qtyIdx = idx('quantity');

  const productSet = new Set<string>();
  const lotSet = new Set<string>();
  const facSet = new Set<string>();
  const dates: string[] = [];
  let emptyRequiredCells = 0;
  let totalRequiredCells = 0;

  for (let i = 0; i < dataLines.length; i++) {
    const cells = dataLines[i].split(',').map(c => c.trim().replace(/^"|"$/g, ''));
    const rowNum = i + 2; // 1-indexed, header is row 1

    // Event type validation
    if (eventTypeIdx >= 0) {
      const et = cells[eventTypeIdx]?.trim();
      totalRequiredCells++;
      if (!et) {
        emptyRequiredCells++;
        if (i < 20) result.issues.push({ severity: 'error', row: rowNum, column: 'event_type', message: 'Empty event_type.' });
      } else if (!VALID_EVENT_TYPES.has(et.toUpperCase())) {
        result.invalidEventTypes.push({ row: rowNum, value: et });
        if (result.invalidEventTypes.length <= 10) {
          result.issues.push({ severity: 'error', row: rowNum, column: 'event_type', message: `Invalid event type "${et}". Expected: R, S, T, C, D, P, H.` });
        }
      } else {
        const label = EVENT_TYPE_LABELS[et.toUpperCase()] || et;
        result.eventTypeCounts[label] = (result.eventTypeCounts[label] || 0) + 1;
      }
    }

    // Product name
    if (productNameIdx >= 0) {
      totalRequiredCells++;
      const val = cells[productNameIdx]?.trim();
      if (!val) { emptyRequiredCells++; }
      else { productSet.add(val); }
    }

    // Lot number
    if (lotIdx >= 0) {
      totalRequiredCells++;
      const val = cells[lotIdx]?.trim();
      if (!val) { emptyRequiredCells++; }
      else { lotSet.add(val); }
    }

    // Datetime
    if (datetimeIdx >= 0) {
      const val = cells[datetimeIdx]?.trim();
      if (val) dates.push(val);
    }

    // Facilities
    if (origFacIdx >= 0) { const v = cells[origFacIdx]?.trim(); if (v) facSet.add(v); }
    if (destFacIdx >= 0) { const v = cells[destFacIdx]?.trim(); if (v) facSet.add(v); }

    // Quantity should be numeric
    if (qtyIdx >= 0) {
      const val = cells[qtyIdx]?.trim();
      if (val && isNaN(Number(val))) {
        if (i < 10) result.issues.push({ severity: 'warning', row: rowNum, column: 'quantity', message: `Non-numeric quantity "${val}".` });
      }
    }
  }

  // Summary stats
  result.productNames = Array.from(productSet).slice(0, 15);
  result.lotNumbers = Array.from(lotSet).slice(0, 15);
  result.facilityNames = Array.from(facSet).slice(0, 15);

  if (dates.length > 0) {
    dates.sort();
    result.dateRange = { earliest: dates[0], latest: dates[dates.length - 1] };
  }

  // Truncation notices
  if (result.invalidEventTypes.length > 10) {
    result.issues.push({ severity: 'error', message: `${result.invalidEventTypes.length - 10} additional invalid event_type rows not shown.` });
  }

  // Completeness score
  const colScore = (result.requiredColumnsPresent.length / Math.max(REQUIRED_COLUMNS.length, 1)) * 40;
  const recColScore = (result.recommendedColumnsPresent.length / Math.max(RECOMMENDED_COLUMNS.length, 1)) * 20;
  const cellScore = totalRequiredCells > 0 ? ((totalRequiredCells - emptyRequiredCells) / totalRequiredCells) * 30 : 30;
  const eventScore = result.invalidEventTypes.length === 0 ? 10 : Math.max(0, 10 - result.invalidEventTypes.length);
  result.completenessScore = Math.round(colScore + recColScore + cellScore + eventScore);

  // Can proceed if no errors
  result.canProceed = !result.issues.some(i => i.severity === 'error');

  return result;
}

/* ── Client-side CSV preview (no auth required) ── */
interface CsvPreview {
  totalRows: number;
  columns: string[];
  sampleRows: string[][];
  eventTypeCounts: Record<string, number>;
  productNames: string[];
  lotNumbers: string[];
}

function parseCSVLocally(text: string): CsvPreview {
  const lines = text.trim().split('\n');
  if (lines.length < 2) return { totalRows: 0, columns: [], sampleRows: [], eventTypeCounts: {}, productNames: [], lotNumbers: [] };

  const columns = lines[0].split(',').map(h => h.trim().replace(/^"|"$/g, ''));
  const dataLines = lines.slice(1);

  const eventTypeIdx = columns.findIndex(c => c.toLowerCase() === 'event_type');
  const productIdx = columns.findIndex(c => c.toLowerCase() === 'product_name');
  const lotIdx = columns.findIndex(c => c.toLowerCase() === 'lot_number');

  const eventTypeCounts: Record<string, number> = {};
  const productSet = new Set<string>();
  const lotSet = new Set<string>();

  const sampleRows: string[][] = [];

  for (let i = 0; i < dataLines.length; i++) {
    const cells = dataLines[i].split(',').map(c => c.trim().replace(/^"|"$/g, ''));
    if (i < 5) sampleRows.push(cells);

    if (eventTypeIdx >= 0 && cells[eventTypeIdx]) {
      const et = cells[eventTypeIdx];
      eventTypeCounts[et] = (eventTypeCounts[et] || 0) + 1;
    }
    if (productIdx >= 0 && cells[productIdx]) productSet.add(cells[productIdx]);
    if (lotIdx >= 0 && cells[lotIdx]) lotSet.add(cells[lotIdx]);
  }

  const EVENT_TYPE_MAP: Record<string, string> = { R: 'Receiving', S: 'Shipping', T: 'Transforming', C: 'Cooling', D: 'Distribution', P: 'Initial Packing', H: 'Harvesting' };
  const mappedCounts: Record<string, number> = {};
  for (const [k, v] of Object.entries(eventTypeCounts)) {
    mappedCounts[EVENT_TYPE_MAP[k] || k] = v;
  }

  return {
    totalRows: dataLines.length,
    columns,
    sampleRows,
    eventTypeCounts: mappedCounts,
    productNames: Array.from(productSet).slice(0, 10),
    lotNumbers: Array.from(lotSet).slice(0, 10),
  };
}

function getErrorMessage(err: unknown, fallback: string): string {
  if (err && typeof err === 'object') {
    const candidate = err as {
      message?: unknown;
      response?: {
        data?: unknown;
      };
    };

    const payload = candidate.response?.data;
    if (payload && typeof payload === 'object') {
      const detail = (payload as { detail?: unknown }).detail;
      if (typeof detail === 'string' && detail.trim().length > 0) {
        return detail;
      }
      const error = (payload as { error?: unknown }).error;
      if (typeof error === 'string' && error.trim().length > 0) {
        return error;
      }
    }

    if (typeof candidate.message === 'string') {
      if (candidate.message.toLowerCase().includes('network error')) {
        return 'Network error while reaching bulk upload service. Please retry with CSV/XLSX template or re-login.';
      }
      if (candidate.message.toLowerCase().includes('timeout')) {
        return 'Bulk upload request timed out. Try a smaller file or CSV/XLSX template.';
      }
      if (candidate.message.trim().length > 0) {
        return candidate.message;
      }
    }
  }

  return fallback;
}

function getActiveStep(
  file: File | null,
  csvPreview: CsvPreview | null,
  clientValidation: ClientValidationResult | null,
  parseResult: SupplierBulkUploadParseResponse | null,
  commitResult: SupplierBulkUploadCommitResponse | null,
): number {
  if (commitResult) return 3;
  if (parseResult || clientValidation) return 2;
  if (csvPreview) return 1;
  if (file) return 0;
  return 0;
}

export default function BulkUploadPage() {
  const { isAuthenticated } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [csvText, setCsvText] = useState<string | null>(null);
  const [csvPreview, setCsvPreview] = useState<CsvPreview | null>(null);
  const [clientValidation, setClientValidation] = useState<ClientValidationResult | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [parseResult, setParseResult] = useState<SupplierBulkUploadParseResponse | null>(null);
  const [validateResult, setValidateResult] = useState<SupplierBulkUploadValidateResponse | null>(null);
  const [commitResult, setCommitResult] = useState<SupplierBulkUploadCommitResponse | null>(null);
  const [statusResult, setStatusResult] = useState<SupplierBulkUploadStatusResponse | null>(null);

  const canCommit = useMemo(() => Boolean(validateResult?.preview?.can_commit), [validateResult]);
  const activeStep = getActiveStep(file, csvPreview, clientValidation, parseResult, commitResult);

  const onFileSelected = (event: ChangeEvent<HTMLInputElement>) => {
    const selected = event.target.files?.[0] || null;
    setFile(selected);
    setCsvText(null);
    setCsvPreview(null);
    setClientValidation(null);
    setParseResult(null);
    setValidateResult(null);
    setCommitResult(null);
    setStatusResult(null);
    setError(null);

    // Client-side preview (works without auth)
    if (selected && (selected.name.endsWith('.csv') || selected.type === 'text/csv')) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result;
        if (typeof text === 'string') {
          try {
            setCsvText(text);
            setCsvPreview(parseCSVLocally(text));
          } catch {
            setError('Could not preview this CSV. Try uploading again.');
          }
        }
      };
      reader.readAsText(selected);
    }
  };

  const onParseAndValidate = async () => {
    if (!file) {
      setError('Choose a file before uploading.');
      return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
      setError('Uploaded file exceeds max size of 10 MB.');
      return;
    }

    setIsBusy(true);
    setError(null);
    setClientValidation(null);
    setParseResult(null);
    setValidateResult(null);
    setCommitResult(null);
    setStatusResult(null);

    // If not authenticated, run client-side FSMA 204 validation
    if (!isAuthenticated) {
      try {
        if (!csvText) {
          setError('Could not read file contents for validation. Try re-uploading.');
          return;
        }
        const validation = validateCSVLocally(csvText);
        setClientValidation(validation);
      } catch {
        setError('Validation failed. Please check your file format and try again.');
      } finally {
        setIsBusy(false);
      }
      return;
    }

    // Authenticated: full server-side validation
    try {
      const parsed = await apiClient.parseSupplierBulkUpload(file);
      setParseResult(parsed);

      const validated = await apiClient.validateSupplierBulkUpload(parsed.session_id);
      setValidateResult(validated);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Upload failed. Verify file format and try again.'));
    } finally {
      setIsBusy(false);
    }
  };

  const onCommit = async () => {
    if (!isAuthenticated) {
      setError('Not authenticated. Sign in and try again.');
      return;
    }
    if (!parseResult?.session_id) {
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      const committed = await apiClient.commitSupplierBulkUpload(parseResult.session_id);
      setCommitResult(committed);
      notifyDashboardRefresh();
      const status = await apiClient.getSupplierBulkUploadStatus(parseResult.session_id);
      setStatusResult(status);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Commit failed. Resolve validation issues and retry.'));
    } finally {
      setIsBusy(false);
    }
  };

  const onRefreshStatus = async () => {
    if (!isAuthenticated) {
      setError('Not authenticated. Sign in and try again.');
      return;
    }
    if (!parseResult?.session_id) {
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      const status = await apiClient.getSupplierBulkUploadStatus(parseResult.session_id);
      setStatusResult(status);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Could not refresh status right now.'));
    } finally {
      setIsBusy(false);
    }
  };

  const onDownloadTemplate = async (format: 'csv' | 'xlsx') => {
    if (!isAuthenticated) {
      setError('Not authenticated. Sign in and try again.');
      return;
    }
    setIsBusy(true);
    setError(null);
    try {
      const { blob, filename } = await apiClient.downloadSupplierBulkUploadTemplate(format);
      const href = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = href;
      anchor.download = filename;
      anchor.click();
      URL.revokeObjectURL(href);
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Template download failed.'));
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-primary)] py-6 sm:py-10">
      <div className="mx-auto max-w-4xl px-4">
        {/* Header */}
        <div className="mb-5 sm:mb-6 flex flex-col sm:flex-row items-start sm:justify-between gap-3">
          <div>
            <span className="inline-flex items-center gap-1.5 text-xs font-semibold px-2.5 py-1 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] border border-[var(--re-brand)]/20 mb-3">
              <UploadCloud className="w-3 h-3" />
              Bulk Upload
            </span>
            <h1 className="text-xl sm:text-2xl font-bold text-[var(--re-text-primary)]">Supplier Bulk Upload</h1>
            <p className="mt-1 text-xs sm:text-sm text-[var(--re-text-muted)] max-w-xl">
              Upload facilities, FTL scope, TLCs, and CTE events in one pass. Bulk writes use the same tenant-wide hash/Merkle path as manual entries.
            </p>
          </div>
          <Link href="/onboarding" className="text-sm font-medium text-[var(--re-brand)] hover:opacity-80 flex items-center gap-1 min-h-[44px]">
            Back to Onboarding
          </Link>
        </div>

        {/* Stepper */}
        <div
          className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 mb-6"
          style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
        >
          {/* Mobile: 2×2 grid. Desktop: horizontal row */}
          <div className="grid grid-cols-2 sm:flex sm:items-center sm:justify-between gap-3 sm:gap-0">
            {STEPS.map((step, i) => (
              <div key={step.label} className="flex items-center sm:flex-1">
                <div className="flex flex-col items-center gap-1.5 flex-1">
                  <div
                    className={`w-9 h-9 rounded-full flex items-center justify-center border transition-colors ${
                      i <= activeStep
                        ? 'bg-[var(--re-brand)] border-[var(--re-brand)] text-white'
                        : 'bg-[var(--re-surface-elevated)] border-[var(--re-surface-border)] text-[var(--re-text-disabled)]'
                    }`}
                  >
                    {i < activeStep ? (
                      <CheckCircle2 className="w-4 h-4" />
                    ) : (
                      <step.Icon className="w-4 h-4" />
                    )}
                  </div>
                  <span className={`text-[11px] sm:text-xs font-medium text-center leading-tight ${
                    i <= activeStep ? 'text-[var(--re-brand)]' : 'text-[var(--re-text-disabled)]'
                  }`}>
                    {step.label}
                  </span>
                </div>
                {i < STEPS.length - 1 && (
                  <div className={`hidden sm:block h-px flex-1 mx-2 mt-[-18px] ${
                    i < activeStep ? 'bg-[var(--re-brand)]' : 'bg-[var(--re-surface-border)]'
                  }`} />
                )}
              </div>
            ))}
          </div>
        </div>

        {/* Signed-out hint banner */}
        {!isAuthenticated && (
          <div className="rounded-xl border border-[var(--re-brand)]/20 bg-[var(--re-brand-muted)] p-3 sm:p-4 mb-5 sm:mb-6 flex flex-col sm:flex-row items-start sm:items-center gap-3 sm:gap-4">
            <div className="flex items-center gap-2.5 shrink-0">
              <ShieldCheck className="w-5 h-5 text-[var(--re-brand)]" />
              <span className="text-sm font-semibold text-[var(--re-text-primary)]">Free preview mode</span>
            </div>
            <p className="text-xs text-[var(--re-text-muted)] leading-relaxed">
              Upload a CSV to preview and validate your data against FSMA 204 requirements — no account required. Sign in to commit with cryptographic integrity and generate audit-ready records.
            </p>
          </div>
        )}

        {/* Merkle integrity callout */}
        <div
          className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 sm:p-5 mb-5 sm:mb-6 flex items-start gap-3 sm:gap-4"
          style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
        >
          <div className="w-10 h-10 rounded-lg bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 flex items-center justify-center flex-shrink-0">
            <Hash className="w-5 h-5 text-[var(--re-brand)]" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">Cryptographic integrity built in</h3>
            <p className="text-xs text-[var(--re-text-muted)] leading-relaxed">
              Every bulk-uploaded record is SHA-256 hashed and inserted into the same tenant-wide Merkle tree as manual entries. Audit trails are tamper-evident from the moment data lands.
            </p>
          </div>
        </div>

        {/* Template downloads */}
        <div className="grid sm:grid-cols-2 gap-3 sm:gap-4 mb-5 sm:mb-6">
          <button
            onClick={() => onDownloadTemplate('csv')}
            disabled={isBusy || !isAuthenticated}
            type="button"
            className="group rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 sm:p-5 text-left hover:border-[var(--re-brand)]/30 hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 active:scale-[0.98] min-h-[48px]"
            style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
          >
            <div className="flex items-center sm:items-start gap-3">
              <div className="w-10 h-10 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] flex items-center justify-center flex-shrink-0 group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] transition-colors duration-300">
                <FileSpreadsheet className="w-5 h-5 text-[var(--re-brand)] group-hover:text-white transition-colors duration-300" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-0.5">CSV Template</h3>
                <p className="text-[11px] sm:text-xs text-[var(--re-text-muted)]">Lightweight, universal format</p>
              </div>
            </div>
          </button>
          <button
            onClick={() => onDownloadTemplate('xlsx')}
            disabled={isBusy || !isAuthenticated}
            type="button"
            className="group rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 sm:p-5 text-left hover:border-[var(--re-brand)]/30 hover:-translate-y-0.5 transition-all disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0 active:scale-[0.98] min-h-[48px]"
            style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
          >
            <div className="flex items-center sm:items-start gap-3">
              <div className="w-10 h-10 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] flex items-center justify-center flex-shrink-0 group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] transition-colors duration-300">
                <ClipboardCheck className="w-5 h-5 text-[var(--re-brand)] group-hover:text-white transition-colors duration-300" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-0.5">XLSX Template</h3>
                <p className="text-[11px] sm:text-xs text-[var(--re-text-muted)]">Multi-sheet workbook with validation</p>
              </div>
            </div>
          </button>
        </div>

        {/* Upload + action area */}
        <div
          className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6"
          style={{
            borderTop: '3px solid var(--re-brand)',
            boxShadow: '0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)',
          }}
        >
          {/* File input */}
          <label className="block mb-1 text-sm font-semibold text-[var(--re-text-primary)]">Upload your file</label>
          <p className="text-xs text-[var(--re-text-muted)] mb-3">Accepts CSV, XLSX, JSON, or PDF. Max 10 MB.</p>
          <input
            type="file"
            accept=".csv,.xlsx,.json,.pdf"
            onChange={onFileSelected}
            className="block w-full rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-2.5 text-sm text-[var(--re-text-secondary)] file:mr-3 file:rounded-md file:border-0 file:bg-[var(--re-brand-muted)] file:px-3 file:py-1.5 file:text-xs file:font-semibold file:text-[var(--re-brand)]"
          />

          {/* Action buttons */}
          <div className="mt-5 flex flex-col sm:flex-row flex-wrap gap-2 sm:gap-3">
            <button
              onClick={onParseAndValidate}
              disabled={!file || isBusy}
              type="button"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--re-brand)] px-5 py-2.5 text-sm font-semibold text-white hover:-translate-y-0.5 transition-all disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 min-h-[48px] active:scale-[0.98] w-full sm:w-auto"
              style={{ boxShadow: '0 4px 16px var(--re-brand-muted)' }}
            >
              {isBusy && !commitResult ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              {isBusy && !commitResult ? 'Working...' : 'Parse + Validate'}
            </button>

            <button
              onClick={onCommit}
              disabled={!canCommit || isBusy || !isAuthenticated}
              type="button"
              className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--re-brand)] px-5 py-2.5 text-sm font-semibold text-white hover:-translate-y-0.5 transition-all disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 min-h-[48px] active:scale-[0.98] w-full sm:w-auto"
              style={{ boxShadow: '0 4px 16px var(--re-brand-muted)' }}
            >
              <CheckCircle2 className="w-4 h-4" />
              Commit Import
            </button>

            <button
              onClick={onRefreshStatus}
              disabled={!parseResult?.session_id || isBusy || !isAuthenticated}
              type="button"
              className="inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-5 py-2.5 text-sm font-medium text-[var(--re-text-secondary)] hover:border-[var(--re-brand)]/30 transition-all disabled:cursor-not-allowed disabled:opacity-50 min-h-[48px] active:scale-[0.98] w-full sm:w-auto"
            >
              Refresh Status
            </button>
          </div>

          {/* Client-side CSV preview (no auth required) */}
          {csvPreview && !parseResult && (
            <div className="mt-5 rounded-xl border border-[var(--re-brand)]/20 bg-[var(--re-brand)]/5 p-4 sm:p-5"
              style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
            >
              <div className="flex items-center gap-2 mb-3">
                <CheckCircle2 className="w-4 h-4 text-[var(--re-brand)]" />
                <p className="font-semibold text-sm text-[var(--re-text-primary)]">
                  Preview: {csvPreview.totalRows} records detected
                </p>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 mb-4">
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5 text-center">
                  <p className="text-lg font-bold text-[var(--re-brand)]">{csvPreview.totalRows}</p>
                  <p className="text-[11px] text-[var(--re-text-muted)]">Total Records</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5 text-center">
                  <p className="text-lg font-bold text-[var(--re-brand)]">{csvPreview.columns.length}</p>
                  <p className="text-[11px] text-[var(--re-text-muted)]">Columns</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5 text-center">
                  <p className="text-lg font-bold text-[var(--re-brand)]">{csvPreview.productNames.length}</p>
                  <p className="text-[11px] text-[var(--re-text-muted)]">Products</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5 text-center">
                  <p className="text-lg font-bold text-[var(--re-brand)]">{csvPreview.lotNumbers.length}</p>
                  <p className="text-[11px] text-[var(--re-text-muted)]">Lot Numbers</p>
                </div>
              </div>

              {/* CTE event type breakdown */}
              {Object.keys(csvPreview.eventTypeCounts).length > 0 && (
                <div className="mb-4">
                  <p className="text-[11px] sm:text-xs font-bold uppercase tracking-widest text-[var(--re-text-disabled)] mb-2">
                    CTE Event Types Detected
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(csvPreview.eventTypeCounts).map(([type, count]) => (
                      <span key={type} className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] text-[var(--re-text-secondary)]">
                        {type}
                        <span className="font-bold text-[var(--re-brand)]">{count}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Sample data table */}
              {csvPreview.sampleRows.length > 0 && (
                <div className="mb-4">
                  <p className="text-[11px] sm:text-xs font-bold uppercase tracking-widest text-[var(--re-text-disabled)] mb-2">
                    Sample Data (first {csvPreview.sampleRows.length} rows)
                  </p>
                  <div className="overflow-x-auto rounded-lg border border-[var(--re-surface-border)]">
                    <table className="w-full text-[11px] sm:text-xs">
                      <thead>
                        <tr className="bg-[var(--re-surface-elevated)]">
                          {csvPreview.columns.slice(0, 6).map(col => (
                            <th key={col} className="px-2 py-1.5 text-left font-semibold text-[var(--re-text-muted)] whitespace-nowrap">{col}</th>
                          ))}
                          {csvPreview.columns.length > 6 && (
                            <th className="px-2 py-1.5 text-left font-semibold text-[var(--re-text-disabled)]">+{csvPreview.columns.length - 6} more</th>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {csvPreview.sampleRows.map((row, i) => (
                          <tr key={i} className="border-t border-[var(--re-surface-border)]">
                            {row.slice(0, 6).map((cell, j) => (
                              <td key={j} className="px-2 py-1.5 text-[var(--re-text-secondary)] whitespace-nowrap truncate max-w-[120px]">{cell}</td>
                            ))}
                            {csvPreview.columns.length > 6 && (
                              <td className="px-2 py-1.5 text-[var(--re-text-disabled)]">…</td>
                            )}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Auth gate CTA */}
              {!isAuthenticated && (
                <div className="rounded-lg border border-[var(--re-brand)]/20 bg-[var(--re-surface-card)] p-4 text-center">
                  <p className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">
                    Your data looks ready for FSMA 204 validation
                  </p>
                  <p className="text-xs text-[var(--re-text-muted)] mb-3 max-w-sm mx-auto">
                    Sign in to run server-side validation, map fields to FSMA CTEs, and commit with cryptographic integrity verification.
                  </p>
                  <div className="flex flex-col sm:flex-row gap-2 justify-center">
                    <Link
                      href="/login?next=/onboarding/bulk-upload"
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--re-brand)] px-5 py-2.5 text-sm font-semibold text-white hover:-translate-y-0.5 transition-all no-underline min-h-[44px] active:scale-[0.98]"
                      style={{ boxShadow: '0 4px 16px var(--re-brand-muted)' }}
                    >
                      Sign In to Validate
                      <ArrowRight className="w-4 h-4" />
                    </Link>
                    <Link
                      href="/login?next=/onboarding/bulk-upload"
                      className="inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--re-surface-border)] px-5 py-2.5 text-sm font-semibold text-[var(--re-text-secondary)] hover:border-[var(--re-brand)]/30 transition-all no-underline min-h-[44px] active:scale-[0.98]"
                    >
                      Create an Account
                    </Link>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Client-side validation results (no auth required) */}
          {clientValidation && !parseResult && (
            <div className="mt-5 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4 sm:p-5"
              style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
            >
              {/* Header with completeness score */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4">
                <div className="flex items-center gap-2">
                  <ClipboardCheck className="w-5 h-5 text-[var(--re-brand)]" />
                  <p className="font-semibold text-sm text-[var(--re-text-primary)]">
                    FSMA 204 Validation Report
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <div className="h-2 w-24 rounded-full bg-[var(--re-surface-border)] overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        clientValidation.completenessScore >= 80 ? 'bg-re-brand' :
                        clientValidation.completenessScore >= 50 ? 'bg-re-warning-muted0' : 'bg-re-danger-muted0'
                      }`}
                      style={{ width: `${clientValidation.completenessScore}%` }}
                    />
                  </div>
                  <span className={`text-sm font-bold ${
                    clientValidation.completenessScore >= 80 ? 'text-re-brand' :
                    clientValidation.completenessScore >= 50 ? 'text-re-warning' : 'text-re-danger'
                  }`}>
                    {clientValidation.completenessScore}%
                  </span>
                  <span className="text-[11px] text-[var(--re-text-muted)]">compliance score</span>
                </div>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 mb-4">
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5 text-center">
                  <p className="text-lg font-bold text-[var(--re-brand)]">{clientValidation.totalRows}</p>
                  <p className="text-[11px] text-[var(--re-text-muted)]">Records</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5 text-center">
                  <p className="text-lg font-bold text-[var(--re-brand)]">{clientValidation.productNames.length}</p>
                  <p className="text-[11px] text-[var(--re-text-muted)]">Products</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5 text-center">
                  <p className="text-lg font-bold text-[var(--re-brand)]">{clientValidation.lotNumbers.length}</p>
                  <p className="text-[11px] text-[var(--re-text-muted)]">Lot Numbers</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5 text-center">
                  <p className="text-lg font-bold text-[var(--re-brand)]">{clientValidation.facilityNames.length}</p>
                  <p className="text-[11px] text-[var(--re-text-muted)]">Facilities</p>
                </div>
              </div>

              {/* CTE event type breakdown */}
              {Object.keys(clientValidation.eventTypeCounts).length > 0 && (
                <div className="mb-4">
                  <p className="text-[11px] sm:text-xs font-bold uppercase tracking-widest text-[var(--re-text-disabled)] mb-2">
                    CTE Event Types
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {Object.entries(clientValidation.eventTypeCounts).map(([type, count]) => (
                      <span key={type} className="inline-flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] text-[var(--re-text-secondary)]">
                        {type}
                        <span className="font-bold text-[var(--re-brand)]">{count}</span>
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Date range */}
              {clientValidation.dateRange.earliest && (
                <div className="mb-4">
                  <p className="text-[11px] sm:text-xs font-bold uppercase tracking-widest text-[var(--re-text-disabled)] mb-1">
                    Date Range
                  </p>
                  <p className="text-xs text-[var(--re-text-secondary)]">
                    {clientValidation.dateRange.earliest} → {clientValidation.dateRange.latest}
                  </p>
                </div>
              )}

              {/* Column mapping status */}
              <div className="mb-4">
                <p className="text-[11px] sm:text-xs font-bold uppercase tracking-widest text-[var(--re-text-disabled)] mb-2">
                  FSMA 204 Column Mapping
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {/* Required columns */}
                  {clientValidation.requiredColumnsPresent.map(col => (
                    <div key={col} className="flex items-center gap-2 text-xs">
                      <CheckCircle2 className="w-3.5 h-3.5 text-re-brand shrink-0" />
                      <span className="text-[var(--re-text-secondary)]">{col}</span>
                      <span className="text-[10px] text-re-brand font-medium">required</span>
                    </div>
                  ))}
                  {clientValidation.requiredColumnsMissing.map(col => (
                    <div key={col} className="flex items-center gap-2 text-xs">
                      <span className="w-3.5 h-3.5 rounded-full bg-re-danger-muted0/10 text-re-danger text-[10px] font-bold flex items-center justify-center shrink-0">!</span>
                      <span className="text-re-danger">{col}</span>
                      <span className="text-[10px] text-re-danger font-medium">missing</span>
                    </div>
                  ))}
                  {clientValidation.recommendedColumnsPresent.map(col => (
                    <div key={col} className="flex items-center gap-2 text-xs">
                      <CheckCircle2 className="w-3.5 h-3.5 text-[var(--re-brand)] shrink-0" />
                      <span className="text-[var(--re-text-secondary)]">{col}</span>
                    </div>
                  ))}
                  {clientValidation.recommendedColumnsMissing.map(col => (
                    <div key={col} className="flex items-center gap-2 text-xs">
                      <span className="w-3.5 h-3.5 rounded-full bg-re-warning-muted0/10 text-re-warning text-[10px] font-bold flex items-center justify-center shrink-0">~</span>
                      <span className="text-re-warning">{col}</span>
                      <span className="text-[10px] text-re-warning font-medium">recommended</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Validation issues */}
              {clientValidation.issues.length > 0 && (
                <div className="mb-4">
                  <p className="text-[11px] sm:text-xs font-bold uppercase tracking-widest text-[var(--re-text-disabled)] mb-2">
                    Issues ({clientValidation.issues.filter(i => i.severity === 'error').length} errors, {clientValidation.issues.filter(i => i.severity === 'warning').length} warnings)
                  </p>
                  <div className="max-h-48 overflow-y-auto space-y-1 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-2">
                    {clientValidation.issues.slice(0, 25).map((issue, idx) => (
                      <div key={idx} className={`flex items-start gap-2 text-[11px] sm:text-xs px-2 py-1 rounded ${
                        issue.severity === 'error' ? 'text-re-danger' : 'text-re-warning'
                      }`}>
                        <span className="shrink-0 mt-0.5">{issue.severity === 'error' ? '✗' : '⚠'}</span>
                        <span>
                          {issue.row && <span className="font-mono opacity-60">Row {issue.row} </span>}
                          {issue.column && <span className="font-mono opacity-60">[{issue.column}] </span>}
                          {issue.message}
                        </span>
                      </div>
                    ))}
                    {clientValidation.issues.length > 25 && (
                      <p className="text-[11px] text-[var(--re-text-disabled)] px-2 py-1">
                        +{clientValidation.issues.length - 25} more issues not shown
                      </p>
                    )}
                  </div>
                </div>
              )}

              {/* Overall status */}
              <div className={`rounded-lg p-3 text-sm font-semibold flex items-center gap-2 ${
                clientValidation.canProceed
                  ? 'bg-re-brand-muted text-re-brand border border-re-brand/20'
                  : 'bg-re-danger-muted0/10 text-re-danger border border-re-danger/20'
              }`}>
                {clientValidation.canProceed ? <CheckCircle2 className="w-4 h-4" /> : <span>!</span>}
                {clientValidation.canProceed
                  ? 'Data passes FSMA 204 structure checks. Ready for server-side commit.'
                  : 'Fix the errors above before proceeding to commit.'}
              </div>

              {/* CTA to sign in for full commit */}
              {!isAuthenticated && (
                <div className="mt-4 rounded-lg border border-[var(--re-brand)]/20 bg-[var(--re-surface-card)] p-4 text-center">
                  <p className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">
                    {clientValidation.canProceed
                      ? 'Your data passed validation — sign in to commit with cryptographic proof'
                      : 'Fix the issues above, then sign in to commit'}
                  </p>
                  <p className="text-xs text-[var(--re-text-muted)] mb-3 max-w-sm mx-auto">
                    Server-side commit adds SHA-256 hashing, Merkle tree integrity, and generates audit-ready records for FDA inspection.
                  </p>
                  <div className="flex flex-col sm:flex-row gap-2 justify-center">
                    <Link
                      href="/login?next=/onboarding/bulk-upload"
                      className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--re-brand)] px-5 py-2.5 text-sm font-semibold text-white hover:-translate-y-0.5 transition-all no-underline min-h-[44px] active:scale-[0.98]"
                      style={{ boxShadow: '0 4px 16px var(--re-brand-muted)' }}
                    >
                      Sign In to Commit
                      <ArrowRight className="w-4 h-4" />
                    </Link>
                    <Link
                      href="/login?next=/onboarding/bulk-upload"
                      className="inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--re-surface-border)] px-5 py-2.5 text-sm font-semibold text-[var(--re-text-secondary)] hover:border-[var(--re-brand)]/30 transition-all no-underline min-h-[44px] active:scale-[0.98]"
                    >
                      Create an Account
                    </Link>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mt-4 rounded-lg border border-re-danger/20 bg-re-danger-muted0/5 p-3 text-sm text-re-danger flex items-start gap-2">
              <span className="text-re-danger mt-0.5">!</span>
              <span>{error}</span>
            </div>
          )}

          {/* Parse result */}
          {parseResult && (
            <div className="mt-4 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4"
              style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
            >
              <p className="font-semibold text-sm text-[var(--re-text-primary)] mb-2">Parsed ({parseResult.detected_format})</p>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                {[
                  { label: 'Facilities', value: parseResult.facilities },
                  { label: 'FTL Scopes', value: parseResult.ftl_scopes },
                  { label: 'TLCs', value: parseResult.tlcs },
                  { label: 'Events', value: parseResult.events },
                ].map((item) => (
                  <div key={item.label} className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-3 text-center">
                    <p className="text-lg font-bold text-[var(--re-brand)]">{item.value}</p>
                    <p className="text-[11px] text-[var(--re-text-muted)]">{item.label}</p>
                  </div>
                ))}
              </div>
              {parseResult.warnings?.length > 0 && (
                <ul className="mt-3 list-disc pl-5 text-xs text-re-warning">
                  {parseResult.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Validation preview */}
          {validateResult && (
            <div className="mt-4 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4"
              style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
            >
              <p className="font-semibold text-sm text-[var(--re-text-primary)] mb-2">Validation Preview</p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm text-[var(--re-text-secondary)]">
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-3">
                  <p className="text-xs text-[var(--re-text-muted)] mb-0.5">Facilities</p>
                  <p className="font-semibold">{validateResult.preview.facilities_to_create} create / {validateResult.preview.facilities_to_update} update</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-3">
                  <p className="text-xs text-[var(--re-text-muted)] mb-0.5">TLCs</p>
                  <p className="font-semibold">{validateResult.preview.tlcs_to_create} create / {validateResult.preview.tlcs_to_update} update</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-3">
                  <p className="text-xs text-[var(--re-text-muted)] mb-0.5">FTL / Events</p>
                  <p className="font-semibold">{validateResult.preview.ftl_scopes_to_upsert} upserts / {validateResult.preview.events_to_chain} chain</p>
                </div>
              </div>
              <div className={`mt-3 rounded-lg p-3 text-sm font-semibold flex items-center gap-2 ${
                validateResult.preview.can_commit
                  ? 'bg-re-brand-muted text-re-brand border border-re-brand/20'
                  : 'bg-re-danger-muted0/10 text-re-danger border border-re-danger/20'
              }`}>
                {validateResult.preview.can_commit ? <CheckCircle2 className="w-4 h-4" /> : <span>!</span>}
                {validateResult.preview.can_commit ? 'Ready to commit.' : 'Resolve validation errors before commit.'}
              </div>
              {validateResult.preview.errors?.length > 0 && (
                <ul className="mt-3 list-disc pl-5 text-xs text-re-danger">
                  {validateResult.preview.errors.map((item, index) => (
                    <li key={`${item.section}-${item.row}-${index}`}>
                      {item.section} row {item.row}: {item.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {/* Commit result */}
          {commitResult && (
            <div className="mt-4 rounded-xl border border-re-brand/20 bg-re-brand/5 p-4"
              style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
            >
              <p className="font-semibold text-sm text-[var(--re-text-primary)] mb-2 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-re-brand" />
                Commit Complete
              </p>
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs text-[var(--re-text-secondary)]">
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5">
                  <p className="text-[var(--re-text-muted)] mb-0.5">Facilities</p>
                  <p className="font-semibold text-sm">{commitResult.summary.facilities_created} created / {commitResult.summary.facilities_updated} updated</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5">
                  <p className="text-[var(--re-text-muted)] mb-0.5">TLCs</p>
                  <p className="font-semibold text-sm">{commitResult.summary.tlcs_created} created / {commitResult.summary.tlcs_updated} updated</p>
                </div>
                <div className="rounded-lg bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-2.5">
                  <p className="text-[var(--re-text-muted)] mb-0.5">Events Chained</p>
                  <p className="font-semibold text-sm">{commitResult.summary.events_chained}</p>
                </div>
              </div>
              {commitResult.summary.sync_warning_count > 0 && (
                <div className="mt-3 rounded-lg border border-re-warning/20 bg-re-warning-muted0/5 p-3 text-xs text-re-warning">
                  <p className="font-semibold mb-1">Graph sync warnings ({commitResult.summary.sync_warning_count})</p>
                  <ul className="list-disc pl-5">
                    {commitResult.summary.sync_warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
              <details className="mt-3">
                <summary className="text-xs text-[var(--re-text-muted)] cursor-pointer hover:text-[var(--re-text-secondary)]">Raw summary JSON</summary>
                <pre className="mt-2 overflow-x-auto text-xs text-[var(--re-text-muted)] bg-[var(--re-surface-elevated)] rounded-lg p-3 border border-[var(--re-surface-border)]">
                  {JSON.stringify(commitResult.summary, null, 2)}
                </pre>
              </details>
            </div>
          )}

          {/* Status result */}
          {statusResult && (
            <div className="mt-4 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4"
              style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
            >
              <p className="font-semibold text-sm text-[var(--re-text-primary)]">Latest Status: {statusResult.status}</p>
              {statusResult.error && <p className="mt-1 text-sm text-re-danger">{statusResult.error}</p>}
              {statusResult.summary && statusResult.summary.sync_warning_count > 0 && (
                <p className="mt-1 text-xs text-re-warning">
                  Graph sync warnings: {statusResult.summary.sync_warning_count}. See commit summary details above.
                </p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
