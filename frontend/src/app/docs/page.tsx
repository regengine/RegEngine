import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRight,
  Key,
  BookOpen,
  Zap,
  Code2,
  Terminal,
  Webhook,
  AlertTriangle,
  Clock,
  Package,
  FileText,
} from 'lucide-react';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { CodeBlock } from '@/components/ui/code-block';
import { API_BASE } from '@/lib/api-base';
import {
  INGEST_CURL_SAMPLE,
  INGEST_JS_SAMPLE,
  INGEST_PYTHON_SAMPLE,
  INGEST_RESPONSE_SAMPLE,
} from '@/lib/api-samples/ingest-samples';

export const metadata: Metadata = {
  title: 'API Documentation | RegEngine',
  description:
    'RegEngine API documentation for FSMA 204 food traceability. Ingest CTE/KDE records, run advisory rule evaluation, and export FDA-oriented sortable records where configured data supports the request.',
  openGraph: {
    title: 'API Documentation | RegEngine',
    description:
      'RegEngine API documentation for FSMA 204 food traceability. Ingest CTE/KDE records, run advisory rule evaluation, and export FDA-oriented sortable records where configured data supports the request.',
    type: 'website',
    url: 'https://regengine.co/docs',
    siteName: 'RegEngine',
  },
};

/* ─── Data ─────────────────────────────────────────────────── */

const endpoints = [
  {
    method: 'POST' as const,
    path: '/webhooks/ingest',
    title: 'Ingest Records',
    description: 'Ingest traceability records with CTE/KDE data. Needs a signed body and an Idempotency-Key. Each record is hash-chained so you can detect tampering between ingest and export.',
  },
  {
    method: 'GET' as const,
    path: '/records',
    title: 'Query Records',
    description: 'Query canonical records, filtered by lot code, event type, source system, status, and date range. Pages with limit and offset.',
  },
  {
    method: 'GET' as const,
    path: '/records/{event_id}',
    title: 'Record Detail',
    description: 'One record with its provenance, rule evaluations, exception cases, and amendment chain.',
  },
  {
    method: 'GET' as const,
    path: '/fda/export',
    title: 'FDA Export',
    description: 'Export FDA-oriented sortable records for a lot code as a package, CSV, or PDF. Needs tenant_id, the fda.export scope, and an active subscription.',
  },
  {
    method: 'GET' as const,
    path: '/fda/trace/{tlc}',
    title: 'Lot Trace',
    description: 'Trace the transformation graph around a traceability lot code: upstream sources and downstream products. Needs tenant_id and the fda.read scope.',
  },
];

const subPages = [
  { title: 'Quickstart', href: '/docs/quickstart', icon: Zap, description: 'Your first API call in about 5 minutes' },
  { title: 'Authentication', href: '/docs/authentication', icon: Key, description: 'The key header, scopes, and what a key can reach' },
  { title: 'API Reference', href: '/docs/api', icon: Code2, description: 'Full endpoint reference with schemas' },
  { title: 'Outbound webhooks (planned)', href: '/docs/webhooks', icon: Webhook, description: 'Notifications from RegEngine. To send events in, use the JSON events API (POST /webhooks/ingest).' },
  { title: 'Inflow Lab', href: '/docs/connectors/inflow-lab', icon: Terminal, description: 'Preflight, readiness scoring, fix queue, and commit gates' },
  { title: 'Error Codes', href: '/docs/errors', icon: AlertTriangle, description: 'Error responses and troubleshooting' },
  { title: 'Rate Limits', href: '/docs/rate-limits', icon: Clock, description: 'What to do when you get a 429' },
  { title: 'SDKs', href: '/docs/sdks', icon: Package, description: 'Client libraries are planned. Use REST and the OpenAPI spec today.' },
  { title: 'FSMA 204 Guide', href: '/docs/fsma-204', icon: FileText, description: 'FSMA 204 regulation reference and implementation' },
];

const quickStartSteps = [
  { step: '1', label: 'Read the docs', href: '/docs/quickstart', icon: BookOpen },
  { step: '2', label: 'Request developer access', href: '/developers', icon: Key },
  { step: '3', label: 'Make your first call', href: '/docs/quickstart', icon: Terminal },
];

const SECTION_LABEL = 'mb-5 font-mono text-label uppercase text-re-text-muted';

/* ─── Code Samples ─────────────────────────────────────────── */
/* Rendered from one payload: src/lib/api-samples/ingest-receiving.json. */

const codeTabs = [
  { label: 'cURL', lang: 'bash', code: INGEST_CURL_SAMPLE },
  { label: 'Python', lang: 'python', code: INGEST_PYTHON_SAMPLE },
  { label: 'JavaScript', lang: 'javascript', code: INGEST_JS_SAMPLE },
];

/* ─── Page ─────────────────────────────────────────────────── */

export default function DocsHomePage() {
  return (
    <div className="re-page min-h-screen">
      <Container width="docs" className="py-10 sm:py-14">
        <PageHeader
          eyebrow="Developer Docs"
          title="RegEngine API Documentation"
          description="Wire FSMA 204 traceability into any supply-chain system. Preflight supplier data, surface gaps, fix missing KDEs, and commit records to an FDA-oriented sortable export workflow. Your operation remains responsible for compliance."
          meta={<Badge tone="neutral" size="sm" mono>v1</Badge>}
        />

        {/* Quick start steps */}
        <ul className="mb-8 grid list-none gap-2 sm:grid-cols-3">
          {quickStartSteps.map((item) => (
            <li key={item.step}>
              <Link
                href={item.href}
                className="group flex h-full items-center gap-3 rounded-lg border border-re-border bg-re-surface-card px-4 py-3 no-underline transition-colors duration-120 hover:border-re-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none"
              >
                <span aria-hidden="true" className="font-mono text-label text-re-text-muted">
                  {item.step}
                </span>
                <item.icon aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 shrink-0 text-re-text-muted" />
                <span className="min-w-0 flex-1 text-ui font-medium text-re-text-primary">
                  {item.label}
                </span>
                <ArrowRight
                  aria-hidden="true"
                  strokeWidth={1.75}
                  className="h-4 w-4 shrink-0 text-re-text-muted transition-colors duration-120 group-hover:text-re-text-primary motion-reduce:transition-none"
                />
              </Link>
            </li>
          ))}
        </ul>

        {/* Base URL + Auth */}
        <dl className="mb-14 grid gap-4 sm:grid-cols-2">
          <div>
            <dt className="mb-1.5 font-mono text-label uppercase text-re-text-muted">Base URL</dt>
            <dd className="m-0">
              <code className="block overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset px-4 py-2 font-mono text-[0.8125rem] text-re-text-primary">
                {API_BASE}
              </code>
            </dd>
          </div>
          <div>
            <dt className="mb-1.5 font-mono text-label uppercase text-re-text-muted">Authentication</dt>
            <dd className="m-0">
              <code className="block overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset px-4 py-2 font-mono text-[0.8125rem] text-re-text-primary">
                X-RegEngine-API-Key: <span className="text-re-text-tertiary">rge_live_...</span>
              </code>
            </dd>
          </div>
        </dl>

        {/* ── Core Endpoints ────────────────────────────────── */}
        <section className="mb-14">
          <h2 className={SECTION_LABEL}>Core Endpoints</h2>

          <Card className="overflow-hidden">
            <ul className="list-none">
              {endpoints.map((ep) => (
                <li
                  key={ep.path}
                  className="flex flex-col gap-3 border-b border-re-border-subtle px-5 py-4 last:border-0 sm:flex-row sm:items-start sm:justify-between"
                >
                  <div className="min-w-0 flex-1">
                    <div className="mb-1 flex flex-wrap items-center gap-2">
                      <Badge tone="neutral" size="sm" mono>
                        {ep.method}
                      </Badge>
                      <code className="font-mono text-[0.8125rem] text-re-text-primary">{ep.path}</code>
                    </div>
                    <p className="text-small text-re-text-tertiary">{ep.description}</p>
                  </div>
                  <Link
                    href="/docs/api"
                    className="shrink-0 self-start text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                  >
                    Reference
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        </section>

        {/* ── Code Samples ──────────────────────────────────── */}
        <section className="mb-14">
          <h2 className="mb-2 font-mono text-label uppercase text-re-text-muted">Ingest Your First Record</h2>
          <p className="mb-2 text-ui text-re-text-secondary">
            Send a traceability event to the{' '}
            <code className="rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary">
              POST /webhooks/ingest
            </code>{' '}
            endpoint. Set <code className="font-mono text-[0.8125rem] text-re-text-primary">REGENGINE_API_KEY</code> and{' '}
            <code className="font-mono text-[0.8125rem] text-re-text-primary">REGENGINE_SIGNING_SECRET</code> to the values
            RegEngine issues to you.
          </p>
          <p className="mb-5 text-ui text-re-text-secondary">
            This call writes a permanent record and can be billed. Use a test workspace and keep the{' '}
            <code className="font-mono text-[0.8125rem] text-re-text-primary">TEST-</code> lot prefix. To check your key first
            with a read, follow the{' '}
            <Link
              href="/docs/quickstart"
              className="text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand"
            >
              Quickstart
            </Link>
            .
          </p>

          {/* Tab bar (static, no JS needed -- all samples shown with labels) */}
          <div className="space-y-4">
            {codeTabs.map((tab) => (
              <div key={tab.label} className="space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-label text-re-text-muted">{tab.label}</span>
                  <span className="font-mono text-label text-re-text-muted">{tab.lang}</span>
                </div>
                <CodeBlock code={tab.code} />
              </div>
            ))}
          </div>

          {/* Response */}
          <div className="mt-6 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <Badge tone="success" size="sm" mono>200 OK</Badge>
              <span className="font-mono text-label uppercase text-re-text-muted">response</span>
            </div>
            <CodeBlock code={INGEST_RESPONSE_SAMPLE} />
          </div>
        </section>

        {/* ── Documentation Pages Grid ──────────────────────── */}
        <section className="mb-14">
          <h2 className={SECTION_LABEL}>Documentation</h2>

          <ul className="grid list-none gap-2 sm:grid-cols-2">
            {subPages.map((page) => (
              <li key={page.href}>
                <Link
                  href={page.href}
                  className="group flex h-full items-start gap-3 rounded-lg border border-re-border bg-re-surface-card px-5 py-4 no-underline transition-colors duration-120 hover:border-re-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none"
                >
                  <page.icon
                    aria-hidden="true"
                    strokeWidth={1.75}
                    className="mt-0.5 h-4 w-4 shrink-0 text-re-text-muted"
                  />
                  <span className="min-w-0 flex-1">
                    <span className="mb-0.5 flex items-center gap-2">
                      <span className="text-ui font-medium text-re-text-primary">{page.title}</span>
                      <ArrowRight
                        aria-hidden="true"
                        strokeWidth={1.75}
                        className="h-3.5 w-3.5 shrink-0 text-re-text-muted opacity-0 transition-opacity duration-120 group-hover:opacity-100 motion-reduce:transition-none"
                      />
                    </span>
                    <span className="block text-small text-re-text-tertiary">{page.description}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>

        {/* ── CTA Banner ────────────────────────────────────── */}
        <section className="mb-14 flex flex-col items-start justify-between gap-6 rounded-lg border border-re-border bg-re-surface-card px-6 py-6 sm:flex-row sm:items-center">
          <div>
            <h3 className="mb-1 text-subheading text-re-text-primary">
              Ready to get started?
            </h3>
            <p className="text-ui text-re-text-tertiary">
              Developer access is request-gated. Tell us about your integration and we&apos;ll provision your API key.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2">
            <Button asChild variant="secondary" size="lg">
              <Link href="/docs/quickstart" className="no-underline">
                Quickstart
                <ArrowRight aria-hidden="true" strokeWidth={1.75} />
              </Link>
            </Button>
            <Button asChild variant="primary" size="lg">
              <Link href="/developers" className="no-underline">
                <Key aria-hidden="true" strokeWidth={1.75} />
                Request developer access
              </Link>
            </Button>
          </div>
        </section>

        {/* ── Footer ────────────────────────────────────────── */}
        <footer className="flex flex-col items-start justify-between gap-4 border-t border-re-border-subtle pt-8 sm:flex-row sm:items-center">
          <div className="flex flex-wrap items-center gap-4">
            <code className="rounded-md border border-re-border-subtle bg-re-surface-inset px-4 py-2 font-mono text-[0.8125rem] text-re-text-secondary">
              python verify_chain.py audit-bundle.zip
            </code>
            <span className="text-ui text-re-text-tertiary">
              Don&apos;t trust, verify.
            </span>
          </div>
          <div className="flex flex-wrap gap-6">
            <Link href="/docs/quickstart" className="text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none">
              Quickstart
            </Link>
            <Link href="/docs/api" className="text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none">
              API Reference
            </Link>
            <Link href="/docs/fsma-204" className="text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none">
              FSMA 204
            </Link>
            <a href="mailto:support@regengine.co" className="text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none">
              Support
            </a>
          </div>
        </footer>
      </Container>
    </div>
  );
}
