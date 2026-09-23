'use client';

// #2757 — the CSV upload front door. Posts through the BFF proxy
// (/api/ingestion/... → POST /api/v1/sandbox/evaluate), which is on the
// unauthenticated allowlist, so no auth and no CSRF token are involved.
// Limits mirror the backend exactly (services/ingestion/app/sandbox/router.py):
// 2 MB of CSV text, 500 events, 30 requests/minute per IP.

import { useCallback, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, FileUp, Loader2, RotateCcw, ShieldOff, TriangleAlert } from 'lucide-react';
import { usePostHog } from '@/lib/posthog-provider';
import { SandboxResultView, type SandboxResult } from '@/components/marketing/sandbox-grid/SandboxResultView';

const EVALUATE_URL = '/api/ingestion/api/v1/sandbox/evaluate';
const SAMPLE_URL = '/samples/sandbox_sample_ftl.csv';

/** Backend rejects >2 MB with a 413; fail locally so the user isn't waiting on a round trip. */
const MAX_CSV_BYTES = 2_000_000;

const TEXT_EXTENSIONS = ['.csv', '.tsv', '.txt'];
const SPREADSHEET_EXTENSIONS = ['.xlsx', '.xls', '.xlsm', '.numbers', '.ods'];

function extensionOf(name: string): string {
  const dot = name.lastIndexOf('.');
  return dot === -1 ? '' : name.slice(dot).toLowerCase();
}

/**
 * Returns an error string when the file cannot be sent, or null when it can.
 * Spreadsheets get their own message: the frontend has no xlsx parser, and
 * silently failing on a .xlsx is the kind of dead end #2757 exists to remove.
 */
export function validateSandboxFile(file: { name: string; size: number }): string | null {
  const ext = extensionOf(file.name);
  if (SPREADSHEET_EXTENSIONS.includes(ext)) {
    return `RegEngine's sandbox reads CSV, not ${ext} directly. In Excel or Numbers choose File → Save As (or Export) → CSV, then upload that file.`;
  }
  if (ext && !TEXT_EXTENSIONS.includes(ext)) {
    return `Unsupported file type ${ext}. Upload a .csv export of your traceability events.`;
  }
  if (file.size > MAX_CSV_BYTES) {
    return `That file is ${(file.size / 1_000_000).toFixed(1)} MB. The sandbox evaluates up to 2 MB — contact us for unlimited evaluation.`;
  }
  return null;
}

/** Maps a failed evaluate response to copy that says what actually happened. */
export function describeSandboxFailure(status: number, detail?: string): string {
  if (status === 404) {
    return 'The sandbox evaluation service is not enabled on this deployment, so your file was not evaluated. Nothing was uploaded or stored.';
  }
  if (status === 429) {
    return 'Rate limit reached (30 evaluations per minute). Wait a minute and try again.';
  }
  if (detail) return detail;
  if (status === 503) {
    return 'The sandbox evaluation service is temporarily unavailable. Nothing was stored — please try again shortly.';
  }
  return `The sandbox could not evaluate that file (HTTP ${status}).`;
}

export function SandboxClient() {
  const posthog = usePostHog();
  const inputRef = useRef<HTMLInputElement>(null);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<SandboxResult | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);

  const evaluate = useCallback(
    async (csv: string, label: string) => {
      setBusy(true);
      setError(null);
      setResult(null);
      setFileName(label);

      try {
        const res = await fetch(EVALUATE_URL, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ csv }),
        });

        if (!res.ok) {
          let detail: string | undefined;
          try {
            const body = await res.json();
            detail = typeof body?.detail === 'string' ? body.detail : undefined;
          } catch {
            // Non-JSON error body (proxy/CDN page); the status alone drives the copy.
          }
          setError(describeSandboxFailure(res.status, detail));
          posthog.capture('SANDBOX_EVALUATE_FAILED', { status: res.status });
          return;
        }

        const data: SandboxResult = await res.json();
        setResult(data);
        posthog.capture('SANDBOX_EVALUATE_SUCCEEDED', {
          total_events: data.total_events,
          non_compliant_events: data.non_compliant_events,
        });
      } catch {
        setError('Could not reach the sandbox. Check your connection and try again — nothing was stored.');
        posthog.capture('SANDBOX_EVALUATE_FAILED', { status: 0 });
      } finally {
        setBusy(false);
      }
    },
    [posthog],
  );

  const onFile = useCallback(
    async (file: File) => {
      const problem = validateSandboxFile(file);
      if (problem) {
        setResult(null);
        setFileName(file.name);
        setError(problem);
        return;
      }
      await evaluate(await file.text(), file.name);
    },
    [evaluate],
  );

  const onSample = useCallback(async () => {
    setBusy(true);
    try {
      const res = await fetch(SAMPLE_URL);
      const csv = await res.text();
      await evaluate(csv, 'sandbox_sample_ftl.csv');
    } catch {
      setBusy(false);
      setError('Could not load the sample file. Try uploading your own CSV.');
    }
  }, [evaluate]);

  function reset() {
    setResult(null);
    setError(null);
    setFileName(null);
    if (inputRef.current) inputRef.current.value = '';
  }

  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      <div className="max-w-4xl mx-auto px-4 py-12">
        <h1 className="text-3xl font-semibold text-[var(--re-text-primary)]">
          FSMA 204 Sandbox
        </h1>
        <p className="mt-4 max-w-2xl text-[0.95rem] leading-7 text-[var(--re-text-muted)]">
          Upload a CSV of traceability events and see which §1.1455 key data elements are missing,
          which rules fail, and what to fix first. No signup. Nothing is stored — the evaluation is
          stateless and the file never leaves the request.
        </p>
        <p className="mt-2 text-[0.75rem] text-[var(--re-text-disabled)]">
          Up to 500 events and 2 MB per file. Column headers are matched flexibly, so
          &ldquo;Lot #&rdquo;, &ldquo;Event Type&rdquo;, and &ldquo;UOM&rdquo; are understood as
          written.
        </p>

        {/* Upload */}
        <div className="mt-8 rounded-xl border border-dashed border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-8 text-center">
          <FileUp className="mx-auto h-8 w-8 text-[var(--re-text-disabled)]" aria-hidden="true" />
          <label
            htmlFor="sandbox-file"
            className="mt-4 block text-[0.9rem] font-medium text-[var(--re-text-primary)]"
          >
            Choose a CSV of traceability events
          </label>
          <input
            ref={inputRef}
            id="sandbox-file"
            type="file"
            accept=".csv,.tsv,.txt,text/csv,text/plain"
            disabled={busy}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void onFile(file);
            }}
            className="mt-4 mx-auto block text-[0.8rem] text-[var(--re-text-muted)] file:mr-3 file:rounded-lg file:border-0 file:bg-[var(--re-brand)] file:px-4 file:py-2 file:text-[0.8rem] file:font-semibold file:text-[var(--re-brand-foreground)] hover:file:bg-[var(--re-brand-dark)] disabled:opacity-50"
          />
          <div className="mt-5 text-[0.75rem] text-[var(--re-text-muted)]">
            No file handy?{' '}
            <button
              type="button"
              onClick={() => void onSample()}
              disabled={busy}
              className="font-semibold text-[var(--re-brand)] underline underline-offset-2 disabled:opacity-50"
            >
              Run a sample FTL chain
            </button>
          </div>
        </div>

        {busy && (
          <div
            role="status"
            className="mt-6 flex items-center gap-2 text-[0.8rem] text-[var(--re-text-muted)]"
          >
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            Evaluating {fileName ?? 'your file'}…
          </div>
        )}

        {error && !busy && (
          <div
            role="alert"
            className="mt-6 flex items-start gap-3 rounded-lg border border-re-danger/30 bg-re-danger/10 p-4"
          >
            {error.startsWith('The sandbox evaluation service is not enabled') ? (
              <ShieldOff className="mt-0.5 h-4 w-4 flex-shrink-0 text-re-danger" aria-hidden="true" />
            ) : (
              <TriangleAlert className="mt-0.5 h-4 w-4 flex-shrink-0 text-re-danger" aria-hidden="true" />
            )}
            <div>
              <p className="text-[0.8rem] text-re-danger">{error}</p>
              <Link
                href="/demo"
                className="mt-2 inline-flex items-center gap-1.5 text-[0.75rem] font-semibold text-[var(--re-brand)] hover:underline"
              >
                Explore the interactive demo instead <ArrowRight className="h-3 w-3" />
              </Link>
            </div>
          </div>
        )}

        {result && !busy && (
          <div className="mt-8">
            <div className="mb-3 flex items-center justify-between">
              <span className="font-mono text-[0.75rem] text-[var(--re-text-muted)]">{fileName}</span>
              <button
                type="button"
                onClick={reset}
                className="inline-flex items-center gap-1.5 text-[0.75rem] font-medium text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]"
              >
                <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
                Evaluate another file
              </button>
            </div>

            <SandboxResultView
              result={result}
              footer={
                <div className="rounded-lg border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/5 p-4 text-center">
                  <p className="mb-2 text-[0.8rem] font-semibold text-[var(--re-brand)]">
                    Want this running against your real feeds?
                  </p>
                  <Link
                    href="/pricing"
                    className="inline-flex items-center gap-2 rounded-lg bg-[var(--re-brand)] px-5 py-2 text-[0.8rem] font-semibold text-[var(--re-brand-foreground)] transition-all hover:bg-[var(--re-brand-dark)]"
                  >
                    See pricing and apply <ArrowRight className="h-4 w-4" />
                  </Link>
                </div>
              }
            />
          </div>
        )}
      </div>
    </div>
  );
}
