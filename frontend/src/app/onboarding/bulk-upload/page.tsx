'use client';

import { useMemo, useState, type ChangeEvent } from 'react';
import Link from 'next/link';
import {
  ArrowRight, CheckCircle2, Download, FileSpreadsheet, Hash,
  Loader2, UploadCloud, ClipboardCheck, Search, ShieldCheck,
} from 'lucide-react';

import { apiClient } from '@/lib/api-client';
import { useAuth } from '@/lib/auth-context';
import type {
  SupplierBulkUploadCommitResponse,
  SupplierBulkUploadParseResponse,
  SupplierBulkUploadStatusResponse,
  SupplierBulkUploadValidateResponse,
} from '@/types/api';

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

const STEPS = [
  { label: 'Download Template', Icon: Download },
  { label: 'Upload File', Icon: UploadCloud },
  { label: 'Parse + Validate', Icon: Search },
  { label: 'Commit', Icon: CheckCircle2 },
];

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
  parseResult: SupplierBulkUploadParseResponse | null,
  commitResult: SupplierBulkUploadCommitResponse | null,
): number {
  if (commitResult) return 3;
  if (parseResult) return 2;
  if (file) return 1;
  return 0;
}

export default function BulkUploadPage() {
  const { isAuthenticated } = useAuth();
  const [file, setFile] = useState<File | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [parseResult, setParseResult] = useState<SupplierBulkUploadParseResponse | null>(null);
  const [validateResult, setValidateResult] = useState<SupplierBulkUploadValidateResponse | null>(null);
  const [commitResult, setCommitResult] = useState<SupplierBulkUploadCommitResponse | null>(null);
  const [statusResult, setStatusResult] = useState<SupplierBulkUploadStatusResponse | null>(null);

  const canCommit = useMemo(() => Boolean(validateResult?.preview?.can_commit), [validateResult]);
  const activeStep = getActiveStep(file, parseResult, commitResult);

  const onFileSelected = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] || null);
    setParseResult(null);
    setValidateResult(null);
    setCommitResult(null);
    setStatusResult(null);
    setError(null);
  };

  const onParseAndValidate = async () => {
    if (!isAuthenticated) {
      setError('Not authenticated. Sign in and try again.');
      return;
    }
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
    setParseResult(null);
    setValidateResult(null);
    setCommitResult(null);
    setStatusResult(null);

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

        {/* Signed-out teaser */}
        {!isAuthenticated && (
          <div
            className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 mb-6 text-center"
            style={{
              borderTop: '3px solid var(--re-brand)',
              boxShadow: '0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)',
            }}
          >
            <div className="w-12 h-12 rounded-xl bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 flex items-center justify-center mx-auto mb-4">
              <ShieldCheck className="w-6 h-6 text-[var(--re-brand)]" />
            </div>
            <h3 className="text-lg font-semibold text-[var(--re-text-primary)] mb-2">Sign in to start uploading</h3>
            <p className="text-sm text-[var(--re-text-muted)] max-w-md mx-auto mb-4">
              Founding Design Partners get instant validation, custom field mapping, and cryptographic integrity verification on every bulk import.
            </p>
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              <Link
                href="/login?next=/onboarding/bulk-upload"
                className="inline-flex items-center justify-center gap-2 rounded-lg bg-[var(--re-brand)] px-5 py-2.5 text-sm font-semibold text-white hover:-translate-y-0.5 transition-all no-underline min-h-[48px] active:scale-[0.98]"
                style={{ boxShadow: '0 4px 16px var(--re-brand-muted)' }}
              >
                Sign In
                <ArrowRight className="w-4 h-4" />
              </Link>
              <Link
                href="/alpha"
                className="inline-flex items-center justify-center gap-2 rounded-lg border border-[var(--re-surface-border)] px-5 py-2.5 text-sm font-semibold text-[var(--re-text-secondary)] hover:border-[var(--re-brand)]/30 transition-all no-underline min-h-[48px] active:scale-[0.98]"
              >
                Become a Founding Design Partner
              </Link>
            </div>
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
              disabled={!file || isBusy || !isAuthenticated}
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

          {/* Error */}
          {error && (
            <div className="mt-4 rounded-lg border border-red-500/20 bg-red-500/5 p-3 text-sm text-red-500 flex items-start gap-2">
              <span className="text-red-400 mt-0.5">!</span>
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
                <ul className="mt-3 list-disc pl-5 text-xs text-amber-500">
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
                  ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/20'
                  : 'bg-red-500/10 text-red-500 border border-red-500/20'
              }`}>
                {validateResult.preview.can_commit ? <CheckCircle2 className="w-4 h-4" /> : <span>!</span>}
                {validateResult.preview.can_commit ? 'Ready to commit.' : 'Resolve validation errors before commit.'}
              </div>
              {validateResult.preview.errors?.length > 0 && (
                <ul className="mt-3 list-disc pl-5 text-xs text-red-500">
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
            <div className="mt-4 rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4"
              style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
            >
              <p className="font-semibold text-sm text-[var(--re-text-primary)] mb-2 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500" />
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
                <div className="mt-3 rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-500">
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
              {statusResult.error && <p className="mt-1 text-sm text-red-500">{statusResult.error}</p>}
              {statusResult.summary && statusResult.summary.sync_warning_count > 0 && (
                <p className="mt-1 text-xs text-amber-500">
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
