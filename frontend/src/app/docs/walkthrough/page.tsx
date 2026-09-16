import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft, ArrowRight } from 'lucide-react';
import { filterExperimentalToolLinks } from '@/lib/experimental-features';
import { PageHeader } from '@/components/layout/page-header';
import { Callout } from '@/components/ui/callout';
import { CodeBlock } from '@/components/ui/code-block';

export const metadata: Metadata = {
  title: 'End-to-End Walkthrough | RegEngine',
  description:
    'A 15-minute hands-on walkthrough — post a complete FSMA 204 supplier-to-shipping flow, see it on your dashboard, and produce a review-ready export.',
  openGraph: {
    title: 'End-to-End Walkthrough',
    description: 'A 15-minute hands-on walkthrough — post a complete FSMA 204 supplier-to-shipping flow, see it on your dashboard, and produce a review-ready export.',
    url: 'https://regengine.co/docs/walkthrough',
    type: 'website',
  },
};

/** Inline identifier — SPEC §2.3. */
const CODE =
  'rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary';

const PROSE_LINK =
  'text-re-brand underline decoration-re-border-strong underline-offset-[3px] hover:decoration-re-brand';

export default function WalkthroughPage() {
  return (
    <>
      <PageHeader
        breadcrumbs={
          <Link
            href="/docs"
            className="inline-flex items-center gap-2 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
          >
            <ArrowLeft aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
            Back to Docs
          </Link>
        }
        eyebrow="15 min hands-on"
        title="End-to-End Walkthrough"
        description={
          <>
            Post a complete supplier-to-shipping flow, see it on your dashboard, and produce a review-ready export.
            Builds on{' '}
            <Link href="/docs/quickstart" className={PROSE_LINK}>
              the 5-minute Quickstart
            </Link>
            .
          </>
        }
      />

      <div className="space-y-8">
        {/* Prereqs */}
        <Section title="Before you start">
          <p className="mb-3 text-body text-re-text-secondary">You should have completed the Quickstart and have:</p>
          <ul className="list-disc space-y-1 pl-5 text-ui text-re-text-secondary marker:text-re-text-muted">
            <li><code className={CODE}>$REGENGINE_API_KEY</code> in your shell</li>
            <li><code className={CODE}>$REGENGINE_TENANT_ID</code> in your shell</li>
            <li>A working <code className={CODE}>curl</code> and ~15 minutes</li>
          </ul>
          <p className="mt-3 text-ui text-re-text-tertiary">
            The scenario: you&apos;re a fresh-cut produce processor. One supplier sent you a romaine
            lot; you transform it; you ship it to a distributor. Three events in one supplier-to-shipping
            chain. We&apos;ll post them, list them, and export them.
          </p>
        </Section>

        {/* Step 1 */}
        <Step n={1} title="Post the Receiving event">
          <p className="mb-3 text-body text-re-text-secondary">
            You receive lot <code className={CODE}>LOT-2026-001</code> from
            Supplier A. This is a Receiving CTE — the starting anchor for the chain.
          </p>
          <CodeBlock
            language="bash"
            code={`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -H "Content-Type: application/json" \\
  -d '{
    "source": "manual-walkthrough",
    "events": [{
      "cte_type": "receiving",
      "traceability_lot_code": "00012345678901-LOT-2026-001",
      "product_description": "Romaine Lettuce, whole heads",
      "quantity": 500,
      "unit_of_measure": "cases",
      "location_gln": "0012345600007",
      "location_name": "DC-4 Receiving Dock",
      "timestamp": "2026-05-13T08:00:00Z",
      "kdes": {
        "receive_date": "2026-05-13",
        "supplier_name": "Supplier A",
        "supplier_gln": "0012345600001"
      }
    }]
  }'`}
          />
          <ExpectedResponse>
            <CodeBlock
              language="json"
              code={`{ "accepted": 1, "rejected": 0, "total": 1, "events": [
  { "traceability_lot_code": "00012345678901-LOT-2026-001",
    "cte_type": "receiving", "status": "accepted",
    "event_id": "...", "sha256_hash": "...", "chain_hash": "..." }
] }`}
            />
          </ExpectedResponse>
          <Troubleshoot>
            <li>
              <strong className="font-medium text-re-text-primary">503 with &quot;Document storage is not configured&quot;</strong> — this endpoint doesn&apos;t
              need object storage; you shouldn&apos;t hit this. If you do, the 503 is from a different
              path; ping support.
            </li>
            <li>
              <strong className="font-medium text-re-text-primary">401/403</strong> — recheck <code className={CODE}>$REGENGINE_API_KEY</code>. The header is{' '}
              <code className={CODE}>X-RegEngine-API-Key</code> (not <code className={CODE}>Authorization</code>).
            </li>
            <li>
              <strong className="font-medium text-re-text-primary">422 validation error</strong> — the response body lists which KDE failed; fix and resubmit. Lot codes follow GS1 GTIN-14 + lot suffix.
            </li>
          </Troubleshoot>
        </Step>

        {/* Step 2 */}
        <Step n={2} title="Post the Transformation event">
          <p className="mb-3 text-body text-re-text-secondary">
            You wash and bag the lot — that&apos;s a Transformation CTE. The input lot is the
            Receiving lot from Step 1; the output lot is new.
          </p>
          <CodeBlock
            language="bash"
            code={`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -H "Content-Type: application/json" \\
  -d '{
    "source": "manual-walkthrough",
    "events": [{
      "cte_type": "transformation",
      "traceability_lot_code": "00012345678901-LOT-2026-001-BAGGED",
      "product_description": "Romaine, washed + bagged, 10oz consumer pack",
      "quantity": 4800,
      "unit_of_measure": "units",
      "location_gln": "0012345600007",
      "location_name": "DC-4 Processing Line 2",
      "timestamp": "2026-05-13T14:00:00Z",
      "kdes": {
        "input_lot_codes": ["00012345678901-LOT-2026-001"],
        "transformation_type": "wash_and_bag",
        "process_start": "2026-05-13T09:30:00Z",
        "process_end": "2026-05-13T13:45:00Z"
      }
    }]
  }'`}
          />
          <ExpectedResponse>
            <p className="text-ui text-re-text-secondary">
              Same shape as Step 1. The new event chains to the receiving event via{' '}
              <code className={CODE}>kdes.input_lot_codes</code>.
            </p>
          </ExpectedResponse>
        </Step>

        {/* Step 3 */}
        <Step n={3} title="Post the Shipping event">
          <p className="mb-3 text-body text-re-text-secondary">
            The bagged lot ships to a distributor. This closes the chain for this lot.
          </p>
          <CodeBlock
            language="bash"
            code={`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID" \\
  -H "Idempotency-Key: $(uuidgen)" \\
  -H "Content-Type: application/json" \\
  -d '{
    "source": "manual-walkthrough",
    "events": [{
      "cte_type": "shipping",
      "traceability_lot_code": "00012345678901-LOT-2026-001-BAGGED",
      "product_description": "Romaine, washed + bagged, 10oz consumer pack",
      "quantity": 4800,
      "unit_of_measure": "units",
      "location_gln": "0012345600007",
      "location_name": "DC-4 Outbound",
      "timestamp": "2026-05-13T18:00:00Z",
      "kdes": {
        "ship_date": "2026-05-13",
        "receiver_name": "Distributor B",
        "receiver_gln": "0012345600002"
      }
    }]
  }'`}
          />
        </Step>

        {/* Step 4 */}
        <Step n={4} title="Check your dashboard">
          <p className="mb-3 text-body text-re-text-secondary">
            Open <Link href="/dashboard/compliance" className={PROSE_LINK}>
            /dashboard/compliance</Link>. You should see:
          </p>
          <ul className="list-disc space-y-1 pl-5 text-ui text-re-text-secondary marker:text-re-text-muted">
            <li>3 events for tenant <code className={CODE}>$REGENGINE_TENANT_ID</code></li>
            <li>The traceability lot code visible in the events list</li>
            <li>A compliance score (early-stage; will improve as more lots flow through)</li>
          </ul>
          <p className="mt-3 text-ui text-re-text-tertiary">
            Empty dashboard? Confirm the tenant ID in the URL matches the one you posted with.
            Different tenant = different scope.
          </p>
        </Step>

        {/* Step 5 */}
        <Step n={5} title="Produce an FDA-oriented export">
          <p className="mb-3 text-body text-re-text-secondary">
            For the lot you just shipped, generate an FDA-oriented sortable spreadsheet for operator review:
          </p>
          <CodeBlock
            language="bash"
            code={`curl -X POST https://regengine.co/api/v1/fda/export \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID" \\
  -H "Content-Type: application/json" \\
  -d '{
    "traceability_lot_codes": ["00012345678901-LOT-2026-001-BAGGED"],
    "format": "fda_sortable_csv"
  }' \\
  -o lot-export.csv

# Inspect:
head -20 lot-export.csv`}
          />
          <p className="mt-3 text-ui text-re-text-tertiary">
            You should see header rows mapping to FDA&apos;s 1.1455(c) requirements, with one row per
            CTE event for the lot. Production records, not legal advice — your operation remains
            responsible for compliance.
          </p>
        </Step>

        {/* Success */}
        <Callout tone="success">
          <h3 className="text-subheading text-re-text-primary">
            What you just proved
          </h3>
          <ul className="mt-2 list-disc space-y-1.5 pl-5 text-ui text-re-text-secondary marker:text-re-text-muted">
            <li>Three CTE events with chained SHA-256 hashes are now in your tenant scope.</li>
            <li>The compliance dashboard reflects them within seconds.</li>
            <li>An FDA-oriented export can be produced for any subset by lot code.</li>
          </ul>
        </Callout>

        {/* Next */}
        <section className="border-t border-re-border-subtle pt-6">
          <h2 className="text-heading text-re-text-primary">Where to go from here</h2>
          <ul className="mt-3 list-none border-t border-re-border-subtle p-0">
            {filterExperimentalToolLinks([
              { title: 'Try a Recall Drill', desc: 'Simulate an FDA recall request against the data you just posted', href: '/dashboard/recall-drills' },
              { title: 'CSV Bulk Ingest', desc: 'Upload a real supplier CSV through Inflow Workbench preflight', href: '/tools/inflow-lab' },
              { title: 'Set up EPCIS or EDI', desc: 'Replace manual curl with your existing system-of-record', href: '/docs/connectors/inflow-lab' },
            ]).map(({ title, desc, href }) => (
              <li key={href}>
                <Link
                  href={href}
                  className="group flex items-center gap-4 border-b border-re-border-subtle px-1 py-4 no-underline transition-colors duration-120 hover:bg-re-surface-inset motion-reduce:transition-none"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block text-ui font-medium text-re-text-primary">{title}</span>
                    <span className="block text-small text-re-text-tertiary">{desc}</span>
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
        </section>
      </div>
    </>
  );
}

/* ── helpers ─────────────────────────────────────────────────────── */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-re-border-subtle pt-6">
      <h2 className="mb-3 text-heading text-re-text-primary">{title}</h2>
      {children}
    </section>
  );
}

/** The ordinal is a mono numeral, not a brand-filled disc (SPEC §1.6). */
function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section className="border-t border-re-border-subtle pt-6">
      <div className="flex items-baseline gap-3">
        <span aria-hidden="true" className="font-mono text-label text-re-text-muted">
          {n}
        </span>
        <h2 className="text-heading text-re-text-primary">{title}</h2>
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function ExpectedResponse({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-3">
      <div className="mb-1.5 font-mono text-label uppercase text-re-text-muted">
        Expected response
      </div>
      {children}
    </div>
  );
}

function Troubleshoot({ children }: { children: React.ReactNode }) {
  return (
    <Callout tone="warning" title="If it didn't work" className="mt-4">
      <ul className="list-disc space-y-1.5 pl-5 text-ui text-re-text-secondary marker:text-re-text-muted">{children}</ul>
    </Callout>
  );
}
