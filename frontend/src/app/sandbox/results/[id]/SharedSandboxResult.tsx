'use client';

import { Link2 } from 'lucide-react';
import Link from 'next/link';
import { useEffect } from 'react';
import { usePostHog } from '@/lib/posthog-provider';
// #2757 — the diagnosis markup used to live here and was duplicated by every
// other surface that wanted it. It is now one component shared with /sandbox.
import { SandboxResultView, type SandboxResult } from '@/components/marketing/sandbox-grid/SandboxResultView';

export function SharedSandboxResult({ result }: { result: SandboxResult; shareId: string }) {
  const posthog = usePostHog();

  // Track share link views
  useEffect(() => {
    posthog.capture('SANDBOX_SHARE_VIEWED', {
      total_events: result.total_events,
      compliant_events: result.compliant_events,
      non_compliant_events: result.non_compliant_events,
    });
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

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
          <Link
            href="/sandbox"
            className="text-[0.75rem] text-[var(--re-brand)] hover:underline"
          >
            Try your own data &rarr;
          </Link>
        </div>

        <SandboxResultView
          result={result}
          footer={
            <div className="rounded-lg border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/5 p-4 text-center">
              <p className="text-[0.8rem] font-semibold text-[var(--re-brand)] mb-2">
                Ready to turn this diagnosis into an operational test run?
              </p>
              <Link
                href="/sandbox"
                className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-[var(--re-brand-foreground)] px-5 py-2 rounded-lg text-[0.8rem] font-semibold transition-all hover:bg-[var(--re-brand-dark)]"
              >
                Try Your Own Data
              </Link>
            </div>
          }
        />
      </div>
    </div>
  );
}
