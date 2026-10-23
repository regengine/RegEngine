import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Button } from '@/components/ui/button';
import { SandboxClient } from './SandboxClient';
import { isSandboxEnabled } from '@/lib/sandbox-cta';

// #2757 - restores the front door the compare-page CTAs have promised since
// #2730 removed the dead homepage sandbox hash anchors. The evaluation
// itself is served by
// POST /api/v1/sandbox/evaluate through the existing unauthenticated BFF proxy
// allowlist in app/api/ingestion/[...path]/route.ts.

export const metadata: Metadata = {
  title: 'FSMA 204 Sandbox: Check your CSV | RegEngine',
  description:
    'Upload a CSV of traceability events and see which FSMA 204 key data elements are missing. No signup, no data stored.',
  openGraph: {
    title: 'FSMA 204 Sandbox: Check your CSV',
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
      // No <main> here: the root layout already renders main#main-content, and
      // a nested one gave the page two main landmarks.
      <Container width="prose" className="py-16 sm:py-20">
        <PageHeader title="The CSV sandbox is not enabled on this deployment" />
        <p className="text-body text-re-text-secondary">
          RegEngine&apos;s stateless CSV evaluation endpoint is part of the experimental router
          surface and is turned off here. Nothing is broken on your end; the feature simply is
          not switched on for this environment.
        </p>
        <p className="mt-4 text-body text-re-text-secondary">
          The walkthrough shows the ingest-to-export path end to end.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Button size="lg" asChild>
            <Link href="/walkthrough">
              See the walkthrough
              <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
            </Link>
          </Button>
        </div>
      </Container>
    );
  }

  return <SandboxClient />;
}
