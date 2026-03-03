'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';

import { apiClient } from '@/lib/api-client';
import type {
  SupplierBulkUploadCommitResponse,
  SupplierBulkUploadParseResponse,
  SupplierBulkUploadStatusResponse,
  SupplierBulkUploadValidateResponse,
} from '@/types/api';

export default function BulkUploadPage() {
  const [file, setFile] = useState<File | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [parseResult, setParseResult] = useState<SupplierBulkUploadParseResponse | null>(null);
  const [validateResult, setValidateResult] = useState<SupplierBulkUploadValidateResponse | null>(null);
  const [commitResult, setCommitResult] = useState<SupplierBulkUploadCommitResponse | null>(null);
  const [statusResult, setStatusResult] = useState<SupplierBulkUploadStatusResponse | null>(null);

  const canCommit = useMemo(() => Boolean(validateResult?.preview?.can_commit), [validateResult]);

  const onParseAndValidate = async () => {
    if (!file) {
      setError('Choose a file before uploading.');
      return;
    }
    setIsBusy(true);
    setError(null);
    setCommitResult(null);
    setStatusResult(null);

    try {
      const parsed = await apiClient.parseSupplierBulkUpload(file);
      setParseResult(parsed);

      const validated = await apiClient.validateSupplierBulkUpload(parsed.session_id);
      setValidateResult(validated);
    } catch (err: unknown) {
      const fallback = 'Upload failed. Verify file format and try again.';
      if (err && typeof err === 'object' && 'message' in err) {
        setError(String((err as { message: unknown }).message || fallback));
      } else {
        setError(fallback);
      }
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
      const fallback = 'Commit failed. Resolve validation issues and retry.';
      if (err && typeof err === 'object' && 'message' in err) {
        setError(String((err as { message: unknown }).message || fallback));
      } else {
        setError(fallback);
      }
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
      const fallback = 'Could not refresh status right now.';
      if (err && typeof err === 'object' && 'message' in err) {
        setError(String((err as { message: unknown }).message || fallback));
      } else {
        setError(fallback);
      }
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
      const fallback = 'Template download failed.';
      if (err && typeof err === 'object' && 'message' in err) {
        setError(String((err as { message: unknown }).message || fallback));
      } else {
        setError(fallback);
      }
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 py-10">
      <div className="mx-auto max-w-4xl px-4">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Supplier Bulk Upload</h1>
            <p className="mt-1 text-sm text-slate-600">
              Upload facilities, FTL scope, TLCs, and CTE events in one pass. Bulk writes use the same tenant-wide hash/Merkle path as manual entries.
            </p>
          </div>
          <Link href="/onboarding/supplier-flow" className="text-sm font-medium text-emerald-700 hover:text-emerald-600">
            Back to Supplier Flow
          </Link>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
          <div className="mb-3 flex flex-wrap gap-2">
            <button
              onClick={() => onDownloadTemplate('csv')}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              disabled={isBusy}
              type="button"
            >
              Download CSV Template
            </button>
            <button
              onClick={() => onDownloadTemplate('xlsx')}
              className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
              disabled={isBusy}
              type="button"
            >
              Download XLSX Template
            </button>
          </div>

          <input
            type="file"
            accept=".csv,.xlsx,.json,.pdf"
            onChange={(event) => setFile(event.target.files?.[0] || null)}
            className="block w-full rounded-md border border-slate-300 bg-white p-2 text-sm text-slate-700"
          />

          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={onParseAndValidate}
              disabled={!file || isBusy}
              type="button"
              className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isBusy ? 'Working...' : 'Parse + Validate'}
            </button>

            <button
              onClick={onCommit}
              disabled={!canCommit || isBusy}
              type="button"
              className="rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Commit Import
            </button>

            <button
              onClick={onRefreshStatus}
              disabled={!parseResult?.session_id || isBusy}
              type="button"
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
            >
              Refresh Status
            </button>
          </div>

          {error && <p className="mt-3 rounded-md border border-red-200 bg-red-50 p-2 text-sm text-red-700">{error}</p>}

          {parseResult && (
            <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
              <p className="font-semibold text-slate-900">Parsed ({parseResult.detected_format})</p>
              <p>
                Facilities: {parseResult.facilities} | FTL scopes: {parseResult.ftl_scopes} | TLCs: {parseResult.tlcs} | Events: {parseResult.events}
              </p>
              {parseResult.warnings?.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-amber-700">
                  {parseResult.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              )}
            </div>
          )}

          {validateResult && (
            <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
              <p className="font-semibold text-slate-900">Validation Preview</p>
              <p>
                Facilities create/update: {validateResult.preview.facilities_to_create}/{validateResult.preview.facilities_to_update}
              </p>
              <p>
                TLC create/update: {validateResult.preview.tlcs_to_create}/{validateResult.preview.tlcs_to_update}
              </p>
              <p>
                FTL upserts: {validateResult.preview.ftl_scopes_to_upsert} | Events to chain: {validateResult.preview.events_to_chain}
              </p>
              <p className={validateResult.preview.can_commit ? 'text-emerald-700' : 'text-red-700'}>
                {validateResult.preview.can_commit ? 'Ready to commit.' : 'Resolve validation errors before commit.'}
              </p>
              {validateResult.preview.errors?.length > 0 && (
                <ul className="mt-2 list-disc pl-5 text-xs text-red-700">
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
            <div className="mt-4 rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
              <p className="font-semibold">Commit Complete</p>
              <pre className="mt-2 overflow-x-auto text-xs">{JSON.stringify(commitResult.summary, null, 2)}</pre>
            </div>
          )}

          {statusResult && (
            <div className="mt-4 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm text-slate-700">
              <p className="font-semibold text-slate-900">Latest Status: {statusResult.status}</p>
              {statusResult.error && <p className="mt-1 text-red-700">{statusResult.error}</p>}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
