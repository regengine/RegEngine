import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { SandboxClient } from './SandboxClient';
import { isSandboxEnabled } from '@/lib/sandbox-cta';

// #2757 — restores the front door the compare-page CTAs have promised since
// #2730 removed the dead homepage sandbox hash anchors. The evaluation
// itself is served by
// POST /api/v1/sandbox/evaluate through the existing unauthenticated BFF proxy
// allowlist in app/api/ingestion/[...path]/route.ts.

export const metadata: Metadata = {
  title: 'FSMA 204 Sandbox — Check your CSV | RegEngine',
  description:
    'Upload a CSV of traceability events and see which FSMA 204 key data elements are missing. No signup, no data stored.',
  openGraph: {
    title: 'FSMA 204 Sandbox — Check your CSV',
    description: 'Upload a CSV of traceability events and see which FSMA 204 key data elements are missing. No signup, no data stored.',
    url: 'https://regengine.co/sandbox',
    type: 'website',
  },
};

export default function SandboxPage() {
  // The sandbox router is experimental (server/main.py _EXPERIMENTAL_ROUTERS)
  // and auto-disabled in production. Rather than 404 or show an upload box
  // that can only fail, say so plainly and point at what does work.
  if (!isSandboxEnabled()) {
    return (
      <main className="min-h-screen bg-[var(--re-surface-base)]">
        <div className="max-w-2xl mx-auto px-4 py-20">
          <h1 className="text-2xl font-semibold text-[var(--re-text-primary)]">
            The CSV sandbox is not enabled on this deployment
          </h1>
          <p className="mt-4 text-[0.9rem] leading-7 text-[var(--re-text-muted)]">
            RegEngine&apos;s stateless CSV evaluation endpoint is part of the experimental router
            surface and is turned off here. Nothing is broken on your end — the feature simply is
            not switched on for this environment.
          </p>
          <p className="mt-4 text-[0.9rem] leading-7 text-[var(--re-text-muted)]">
            The interactive demo covers the same rule evaluation against a synthetic dataset, and
            the walkthrough shows the ingest-to-export path end to end.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              href="/demo"
              className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-5 py-2.5 rounded-lg text-sm font-semibold transition-colors hover:bg-[var(--re-brand-dark)]"
            >
              Explore the interactive demo <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/walkthrough"
              className="inline-flex items-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-5 py-2.5 rounded-lg text-sm font-medium transition-colors hover:bg-[var(--re-surface-elevated)]"
            >
              See the walkthrough
            </Link>
          </div>
        </div>
      </main>
    );
  }

  return <SandboxClient />;
}
