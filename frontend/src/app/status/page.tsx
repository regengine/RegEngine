import type { Metadata } from 'next';
import Link from 'next/link';
import { StatusBoard } from './StatusBoard';

export const metadata: Metadata = {
  title: 'System Status | RegEngine',
  description:
    'Live RegEngine system status — backend service health, last checked timestamp, and pilot support channel.',
  openGraph: {
    title: 'System Status | RegEngine',
    description: 'Live RegEngine system status and pilot support contact.',
    url: 'https://regengine.co/status',
    type: 'website',
  },
};

export const dynamic = 'force-dynamic';

export default function StatusPage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      {/* Hero */}
      <section className="max-w-[860px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-6">
        <h1 className="font-display text-4xl font-bold text-[var(--re-text-primary)] mb-3 leading-tight tracking-tight">
          System Status
        </h1>
        <p className="text-sm text-[var(--re-text-muted)] leading-relaxed max-w-[640px]">
          Live health of the RegEngine backend services. This page polls{' '}
          <code className="font-mono text-xs px-1 py-0.5 rounded bg-[var(--re-surface-elevated)]">/api/health</code>{' '}
          every 30 seconds.
        </p>
      </section>

      {/* Status board */}
      <section className="max-w-[860px] mx-auto px-4 sm:px-6 pb-10">
        <StatusBoard />
      </section>

      {/* Support */}
      <section className="max-w-[860px] mx-auto px-4 sm:px-6 pb-16">
        <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 shadow-sm">
          <h2 className="font-display text-2xl font-bold text-[var(--re-text-primary)] mb-3">
            Pilot support
          </h2>
          <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mb-4">
            Production issues, integration questions, or anything blocking your evaluation:
            email{' '}
            <a
              href="mailto:support@regengine.co"
              className="text-[var(--re-brand)] underline hover:opacity-90"
            >
              support@regengine.co
            </a>
            . First response within 24 hours during pilot programs. For urgent
            ingestion or auth issues, include your workspace slug and the timestamp
            of the request so we can correlate with logs.
          </p>
          <div className="grid gap-3 sm:grid-cols-3 mt-4">
            <Link
              href="/docs"
              className="rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3 text-sm font-medium text-[var(--re-text-primary)] hover:border-[var(--re-brand)]/40 transition-colors"
            >
              Documentation →
            </Link>
            <Link
              href="/docs/changelog"
              className="rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3 text-sm font-medium text-[var(--re-text-primary)] hover:border-[var(--re-brand)]/40 transition-colors"
            >
              Changelog →
            </Link>
            <Link
              href="/trust"
              className="rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-3 text-sm font-medium text-[var(--re-text-primary)] hover:border-[var(--re-brand)]/40 transition-colors"
            >
              Trust Center →
            </Link>
          </div>
        </div>
      </section>

      {/* Disclaimer */}
      <section className="max-w-[860px] mx-auto px-4 sm:px-6 pb-20">
        <p className="text-xs text-[var(--re-text-disabled)] leading-relaxed">
          Status reflects backend service liveness as observed from the Vercel
          edge. It does not promise end-to-end ingestion success for every
          tenant; specific service commitments are set in your agreement.
        </p>
      </section>
    </div>
  );
}
