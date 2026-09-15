import type { Metadata } from 'next';
import Link from 'next/link';
import { StatusBoard } from './StatusBoard';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Card } from '@/components/ui/card';

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
    <div className="min-h-screen bg-re-surface-base">
      {/* Hero */}
      <Container as="section" width="marketing" className="pb-6 pt-12 sm:pt-16">
        <PageHeader
          size="hero"
          title="System Status"
          description={
            <>
              Live health of the RegEngine backend services. This page polls{' '}
              <code className="rounded-sm bg-re-surface-inset px-1 py-0.5 font-mono text-[0.8125rem]">/api/health</code>{' '}
              every 30 seconds.
            </>
          }
          className="border-b-0 pb-0"
        />
      </Container>

      {/* Status board */}
      <Container as="section" width="marketing" className="pb-10">
        <StatusBoard />
      </Container>

      {/* Support */}
      <Container as="section" width="marketing" className="pb-16">
        <Card padding="spacious">
          <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">
            Pilot support
          </h2>
          <p className="mb-4 max-w-[68ch] text-ui text-re-text-secondary">
            Production issues, integration questions, or anything blocking your evaluation:
            email{' '}
            <a
              href="mailto:support@regengine.co"
              className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
            >
              support@regengine.co
            </a>
. We aim to respond within one business day during pilot programs. For urgent
            ingestion or auth issues, include your workspace slug and the timestamp
            of the request so we can correlate with logs.
          </p>
          <div className="mt-4 grid gap-3 sm:grid-cols-3">
            <Link
              href="/docs"
              className="rounded-md border border-re-border bg-re-surface-inset p-3 text-ui font-medium text-re-text-primary transition-colors duration-120 hover:border-re-border-strong motion-reduce:transition-none"
            >
              Documentation →
            </Link>
            <Link
              href="/docs/changelog"
              className="rounded-md border border-re-border bg-re-surface-inset p-3 text-ui font-medium text-re-text-primary transition-colors duration-120 hover:border-re-border-strong motion-reduce:transition-none"
            >
              Changelog →
            </Link>
            <Link
              href="/trust"
              className="rounded-md border border-re-border bg-re-surface-inset p-3 text-ui font-medium text-re-text-primary transition-colors duration-120 hover:border-re-border-strong motion-reduce:transition-none"
            >
              Trust Center →
            </Link>
          </div>
        </Card>
      </Container>

      {/* Disclaimer */}
      <Container as="section" width="marketing" className="pb-20">
        <p className="max-w-[68ch] text-small text-re-text-tertiary">
          Status reflects backend service liveness as observed from the Vercel
          edge. It does not promise end-to-end ingestion success for every
          tenant; specific service commitments are set in your agreement.
        </p>
      </Container>
    </div>
  );
}
