import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, CheckCircle, AlertCircle, Terminal } from 'lucide-react';
import { CodeBlock } from '@/components/ui/code-block';

export const metadata: Metadata = {
  title: 'End-to-End Walkthrough | RegEngine',
  description:
    'A 15-minute hands-on walkthrough — post a complete FSMA 204 supplier-to-shipping flow, see it on your dashboard, and produce an audit-ready export.',
};

export default function WalkthroughPage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      {/* Header */}
      <div className="p-6 border-b border-[var(--re-surface-border)]">
        <div className="max-w-[800px] mx-auto">
          <Link
            href="/docs"
            className="inline-flex items-center gap-2 text-sm text-[var(--re-brand)] no-underline mb-4"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Docs
          </Link>
          <div className="flex items-center gap-3 mb-3">
            <Terminal className="w-7 h-7 text-[var(--re-brand)]" />
            <span className="bg-[rgba(16,185,129,0.2)] text-[var(--re-brand)] text-[11px] font-semibold px-2.5 py-1 rounded">
              15 min hands-on
            </span>
          </div>
          <h1 className="text-[1.75rem] sm:text-[2.5rem] font-bold text-[var(--re-text-primary)] mb-2">
            End-to-End Walkthrough
          </h1>
          <p className="text-[var(--re-text-muted)] text-base">
            Post a complete supplier-to-shipping flow, see it on your dashboard, and produce an audit-ready export.
            Builds on{' '}
            <Link href="/docs/quickstart" className="text-[var(--re-brand)] underline">
              the 5-minute Quickstart
            </Link>
            .
          </p>
        </div>
      </div>

      {/* Content */}
      <div className="max-w-[800px] mx-auto px-6 py-12 space-y-12">
        {/* Prereqs */}
        <Section title="Before you start">
          <p className="leading-[1.7] mb-3">You should have completed the Quickstart and have:</p>
          <ul className="list-disc pl-5 space-y-1 text-sm">
            <li><code className="bg-black/30 px-1.5 py-0.5 rounded">$REGENGINE_API_KEY</code> in your shell</li>
            <li><code className="bg-black/30 px-1.5 py-0.5 rounded">$REGENGINE_TENANT_ID</code> in your shell</li>
            <li>A working <code className="bg-black/30 px-1.5 py-0.5 rounded">curl</code> and ~15 minutes</li>
          </ul>
          <p className="text-sm text-[var(--re-text-muted)] mt-3">
            The scenario: you&apos;re a fresh-cut produce processor. One supplier sent you a romaine
            lot; you transform it; you ship it to a distributor. Three events in one supplier-to-shipping
            chain. We&apos;ll post them, list them, and export them.
          </p>
        </Section>

        {/* Step 1 */}
        <Step n={1} title="Post the Receiving event">
          <p className="leading-[1.7] mb-3">
            You receive lot <code className="bg-black/30 px-1.5 py-0.5 rounded">LOT-2026-001</code> from
            Supplier A. This is a Receiving CTE — the starting anchor for the chain.
          </p>
          <CodeBlock
            language="bash"
            code={`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID" \\
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
              <strong>503 with &quot;Document storage is not configured&quot;</strong> — this endpoint doesn&apos;t
              need object storage; you shouldn&apos;t hit this. If you do, the 503 is from a different
              path; ping support.
            </li>
            <li>
              <strong>401/403</strong> — recheck <code>$REGENGINE_API_KEY</code>. The header is{' '}
              <code>X-RegEngine-API-Key</code> (not <code>Authorization</code>).
            </li>
            <li>
              <strong>422 validation error</strong> — the response body lists which KDE failed; fix and resubmit. Lot codes follow GS1 GTIN-14 + lot suffix.
            </li>
          </Troubleshoot>
        </Step>

        {/* Step 2 */}
        <Step n={2} title="Post the Transformation event">
          <p className="leading-[1.7] mb-3">
            You wash and bag the lot — that&apos;s a Transformation CTE. The input lot is the
            Receiving lot from Step 1; the output lot is new.
          </p>
          <CodeBlock
            language="bash"
            code={`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID" \\
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
            <p className="text-sm">
              Same shape as Step 1. The new event chains to the receiving event via{' '}
              <code className="bg-black/30 px-1.5 py-0.5 rounded">kdes.input_lot_codes</code>.
            </p>
          </ExpectedResponse>
        </Step>

        {/* Step 3 */}
        <Step n={3} title="Post the Shipping event">
          <p className="leading-[1.7] mb-3">
            The bagged lot ships to a distributor. This closes the chain for this lot.
          </p>
          <CodeBlock
            language="bash"
            code={`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID" \\
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
          <p className="leading-[1.7] mb-3">
            Open <Link href="/dashboard/compliance" className="text-[var(--re-brand)] underline">
            /dashboard/compliance</Link>. You should see:
          </p>
          <ul className="list-disc pl-5 space-y-1 text-sm">
            <li>3 events for tenant <code className="bg-black/30 px-1.5 py-0.5 rounded">$REGENGINE_TENANT_ID</code></li>
            <li>The traceability lot code visible in the events list</li>
            <li>A compliance score (early-stage; will improve as more lots flow through)</li>
          </ul>
          <p className="text-sm text-[var(--re-text-muted)] mt-3">
            Empty dashboard? Confirm the tenant ID in the URL matches the one you posted with.
            Different tenant = different scope.
          </p>
        </Step>

        {/* Step 5 */}
        <Step n={5} title="Produce an FDA-ready export">
          <p className="leading-[1.7] mb-3">
            For the lot you just shipped, generate the sortable spreadsheet FDA inspectors expect:
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
          <p className="text-sm text-[var(--re-text-muted)] mt-3">
            You should see header rows mapping to FDA&apos;s 1.1455(c) requirements, with one row per
            CTE event for the lot. Production records, not legal advice — your operation remains
            responsible for compliance.
          </p>
        </Step>

        {/* Success */}
        <div className="rounded-lg p-6 bg-[rgba(16,185,129,0.1)] border border-[rgba(16,185,129,0.3)]">
          <div className="flex items-start gap-4">
            <CheckCircle className="w-6 h-6 text-[var(--re-brand)] shrink-0" />
            <div>
              <h3 className="text-[1.1rem] font-semibold text-[var(--re-text-primary)] mb-2">
                What you just proved
              </h3>
              <ul className="text-sm space-y-1.5 list-disc pl-5">
                <li>Three CTE events with chained SHA-256 hashes are now in your tenant scope.</li>
                <li>The compliance dashboard reflects them within seconds.</li>
                <li>An FDA-formatted export can be produced for any subset by lot code.</li>
                <li>Your tenant is now in the OKR count of pilots ingesting weekly.</li>
              </ul>
            </div>
          </div>
        </div>

        {/* Next */}
        <section>
          <h2 className="text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">Where to go from here</h2>
          <div className="grid gap-3">
            {[
              { title: 'Try a Recall Drill', desc: 'Simulate an FDA recall request against the data you just posted', href: '/dashboard/recall-drills' },
              { title: 'CSV Bulk Ingest', desc: 'Upload a real supplier CSV through Inflow Workbench preflight', href: '/tools/inflow-lab' },
              { title: 'Set up EPCIS or EDI', desc: 'Replace manual curl with your existing system-of-record', href: '/docs/connectors/inflow-lab' },
            ].map(({ title, desc, href }) => (
              <Link key={href} href={href} className="no-underline">
                <div className="px-5 py-4 rounded-lg flex items-center gap-4 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)]">
                  <div className="flex-1">
                    <div className="font-semibold text-[var(--re-text-primary)] mb-0.5">{title}</div>
                    <div className="text-[13px] text-[var(--re-text-muted)]">{desc}</div>
                  </div>
                  <ArrowRight className="w-4 h-4 text-[var(--re-text-muted)]" />
                </div>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}

/* ── helpers ─────────────────────────────────────────────────────── */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-[1.1rem] font-semibold text-[var(--re-text-primary)] mb-3">{title}</h2>
      {children}
    </section>
  );
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <section>
      <div className="flex items-start gap-4">
        <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm text-white shrink-0 bg-[var(--re-brand)]">
          {n}
        </div>
        <div className="flex-1 min-w-0">
          <h2 className="text-[1.1rem] font-semibold text-[var(--re-text-primary)] mb-3">{title}</h2>
          {children}
        </div>
      </div>
    </section>
  );
}

function ExpectedResponse({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-3">
      <div className="text-[12px] uppercase tracking-wider text-[var(--re-text-muted)] mb-1.5">
        Expected response
      </div>
      {children}
    </div>
  );
}

function Troubleshoot({ children }: { children: React.ReactNode }) {
  return (
    <div className="mt-4 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-4">
      <div className="flex items-center gap-2 mb-2">
        <AlertCircle className="w-4 h-4 text-[var(--re-warning)]" />
        <div className="text-sm font-semibold text-[var(--re-text-primary)]">If it didn&apos;t work</div>
      </div>
      <ul className="text-sm space-y-1.5 list-disc pl-5">{children}</ul>
    </div>
  );
}
