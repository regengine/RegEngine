'use client';

import { useMemo, useState, type ChangeEvent } from 'react';
import Link from 'next/link';

import { apiClient } from '@/lib/api-client';
import type {
  SupplierBulkUploadCommitResponse,
  SupplierBulkUploadParseResponse,
  SupplierBulkUploadStatusResponse,
  SupplierBulkUploadValidateResponse,
} from '@/types/api';

const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;

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

export default function BulkUploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [parseResult, setParseResult] = useState<SupplierBulkUploadParseResponse | null>(null);
  const [validateResult, setValidateResult] = useState<SupplierBulkUploadValidateResponse | null>(null);
  const [commitResult, setCommitResult] = useState<SupplierBulkUploadCommitResponse | null>(null);
  const [statusResult, setStatusResult] = useState<SupplierBulkUploadStatusResponse | null>(null);

  const canCommit = useMemo(() => Boolean(validateResult?.preview?.can_commit), [validateResult]);

  const onFileSelected = (event: ChangeEvent<HTMLInputElement>) => {
    setFile(event.target.files?.[0] || null);
    setParseResult(null);
    setValidateResult(null);
    setCommitResult(null);
    setStatusResult(null);
    setError(null);
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
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-primary)] py-10">
      <div className="mx-auto max-w-4xl px-4">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-[var(--re-text-primary)]">Supplier Bulk Upload</h1>
            <p className="mt-1 text-sm text-[var(--re-text-muted)]">
              Upload facilities, FTL scope, TLCs, and CTE events in one pass. Bulk writes use the same tenant-wide hash/Merkle path as manual entries.
            </p>
          </div>
          <Link href="/onboarding" className="text-sm font-medium text-[var(--re-brand)] hover:opacity-80">
            Back to Onboarding
          </Link>
        </div>

        <div className="rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5 shadow-sm">
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              onClick={() => onDownloadTemplate('csv')}
              className="rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-3 py-2 text-sm font-medium text-[var(--re-text-secondary)] hover:opacity-90"
              disabled={isBusy}
              type="button"
            >
              Download CSV Template
            </button>
            <button
              onClick={() => onDownloadTemplate('xlsx')}
              className="rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-3 py-2 text-sm font-medium text-[var(--re-text-secondary)] hover:opacity-90"
              disabled={isBusy}
              type="button"
            >
              Download XLSX Template
            </button>
          </div>

          <input
            type="file"
            accept=".csv,.xlsx,.json,.pdf"
            onChange={onFileSelected}
            className="block w-full rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-2 text-sm text-[var(--re-text-secondary)]"
          />

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={onParseAndValidate}
              disabled={!file || isBusy}
              type="button"
              className="rounded-md bg-[var(--re-brand)] px-4 py-2 text-sm font-semibold text-[var(--re-surface-base)] hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isBusy ? 'Working...' : 'Parse + Validate'}
            </button>

            <button
              onClick={onCommit}
              disabled={!canCommit || isBusy}
              type="button"
              className="rounded-md bg-[var(--re-info)] px-4 py-2 text-sm font-semibold text-[var(--re-surface-base)] hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Commit Import
            </button>

            <button
              onClick={onRefreshStatus}
              disabled={!parseResult?.session_id || isBusy}
              type="button"
              className="rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-4 py-2 text-sm font-medium text-[var(--re-text-secondary)] hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Refresh Status
            </button>
          </div>

          {error && <p className="mt-3 rounded-md border border-[var(--re-danger)] bg-[var(--re-danger-muted)] p-2 text-sm text-[var(--re-danger)]">{error}</p>}

          {parseResult && (
            <div className="mt-4 rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3 text-sm text-[var(--re-text-secondary)]">
              <p className="font-semibold text-[var(--re-text-primary)]">Parsed ({parseResult.detected_format})</p>
              <p>
                Facilities: {parseResult.facilities} | FTL scopes: {parseResult.ftl_scopes} | TLCs: {parseResult.tlcs} | Events: {parseResult.events}
              </p>
              {parseResult.warnings?.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-[var(--re-warning)]">
                  {parseResult.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {validateResult && (
            <div className="mt-4 rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3 text-sm text-[var(--re-text-secondary)]">
              <p className="font-semibold text-[var(--re-text-primary)]">Validation Preview</p>
              <p>
                Facilities create/update: {validateResult.preview.facilities_to_create}/{validateResult.preview.facilities_to_update}
              </p>
              <p>
                TLC create/update: {validateResult.preview.tlcs_to_create}/{validateResult.preview.tlcs_to_update}
              </p>
              <p>
                FTL upserts: {validateResult.preview.ftl_scopes_to_upsert} | Events to chain: {validateResult.preview.events_to_chain}
              </p>
              <p className={validateResult.preview.can_commit ? 'text-[var(--re-success)]' : 'text-[var(--re-danger)]'}>
                {validateResult.preview.can_commit ? 'Ready to commit.' : 'Resolve validation errors before commit.'}
              </p>
              {validateResult.preview.errors?.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-[var(--re-danger)]">
                  {validateResult.preview.errors.map((item, index) => (
                    <li key={`${item.section}-${item.row}-${index}`}>
                      {item.section} row {item.row}: {item.message}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {commitResult && (
            <div className="mt-4 rounded-md border border-[var(--re-success)] bg-[var(--re-success-muted)] p-3 text-sm text-[var(--re-text-primary)]">
              <p className="font-semibold">Commit Complete</p>
              <p className="mt-1 text-xs">
                Facilities create/update: {commitResult.summary.facilities_created}/{commitResult.summary.facilities_updated} | TLC create/update:{' '}
                {commitResult.summary.tlcs_created}/{commitResult.summary.tlcs_updated} | Events chained: {commitResult.summary.events_chained}
              </p>
              {commitResult.summary.sync_warning_count > 0 && (
                <div className="mt-2 rounded-md border border-[var(--re-warning)] bg-[var(--re-warning-muted)] p-2 text-xs text-[var(--re-warning)]">
                  <p className="font-semibold">Graph sync warnings ({commitResult.summary.sync_warning_count})</p>
                  <ul className="mt-1 list-disc pl-5">
                    {commitResult.summary.sync_warnings.map((warning) => (
                      <li key={warning}>{warning}</li>
                    ))}
                  </ul>
                </div>
              )}
              <pre className="mt-2 overflow-x-auto text-xs">{JSON.stringify(commitResult.summary, null, 2)}</pre>
            </div>
          )}

          {statusResult && (
            <div className="mt-4 rounded-md border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3 text-sm text-[var(--re-text-secondary)]">
              <p className="font-semibold text-[var(--re-text-primary)]">Latest Status: {statusResult.status}</p>
              {statusResult.error && <p className="mt-1 text-[var(--re-danger)]">{statusResult.error}</p>}
              {statusResult.summary && statusResult.summary.sync_warning_count > 0 && (
                <p className="mt-1 text-xs text-[var(--re-warning)]">
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
