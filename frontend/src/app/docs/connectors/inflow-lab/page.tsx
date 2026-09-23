import type { Metadata } from "next";
import Link from "next/link";
import { ArrowLeft, ArrowRight, Check } from "lucide-react";
import { API_BASE } from "@/lib/api-base";
import { PageHeader } from "@/components/layout/page-header";
import { Card } from "@/components/ui/card";
import { CodeBlock } from "@/components/ui/code-block";

export const metadata: Metadata = {
  title: "Inflow Lab Connector | RegEngine",
  description:
    "Use Inflow Lab to distinguish sandbox diagnosis, mock feed validation, authenticated ingest, and production evidence boundaries.",
  openGraph: {
    title: 'Inflow Lab Connector',
    description: 'Use Inflow Lab to distinguish sandbox diagnosis, mock feed validation, authenticated ingest, and production evidence boundaries.',
    url: 'https://regengine.co/docs/connectors/inflow-lab',
    type: 'website',
  },
};

const ingestExample = `curl -X POST ${API_BASE}/webhooks/ingest \\
  -H "Content-Type: application/json" \\
  -H "X-RegEngine-API-Key: rge_live_..." \\
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000000" \\
  -H "Idempotency-Key: inflow-lab-test-001" \\
  -d '{
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "source": "inflow-lab",
    "events": [{
      "cte_type": "shipping",
      "traceability_lot_code": "ROM-2026-0427-A",
      "product_description": "Romaine Lettuce",
      "quantity": 48,
      "unit_of_measure": "cases",
      "location_name": "Inflow Lab Test DC",
      "timestamp": "2026-04-27T18:30:00Z",
      "kdes": {
        "ship_from_location": "Test Grower",
        "ship_to_location": "Test Retailer",
        "carrier": "Inflow Lab Carrier"
      }
    }]
  }'`;

const localRun = `git clone https://github.com/regengine/inflow-lab.git
cd inflow-lab
cp .env.example .env
# Set RE_API_BASE_URL, RE_API_KEY, and RE_TENANT_ID
python -m pytest`;

const statusFacts = [
  ["Public slug", "inflow-lab"],
  ["Backend id", "inflow_lab"],
  ["Repository", "regengine/inflow-lab"],
  ["CI contract", "Authenticated ingest"],
];

const livePath = [
  ["Sandbox/mock", "Diagnoses source shape without creating production evidence"],
  ["Authenticated ingest", "POST /api/v1/webhooks/ingest"],
  ["Alias resolution", "inflow-lab resolves to inflow_lab"],
  ["Persisted records", "Tenant-scoped records become eligible for evidence export"],
];

const connectionSteps = [
  "Inflow Lab can diagnose CSV shape and generate RegEngine-shaped FSMA 204 CTE payloads.",
  "Mock and sandbox runs stay separate from production ingestion and are not evidence.",
  "Only authenticated webhook ingest creates persisted tenant records that can be used for production evidence export.",
];

/** Inline identifier — SPEC §2.3. */
const CODE =
  "rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary";

export default function InflowLabDocsPage() {
  return (
    <>
      <PageHeader
        breadcrumbs={
          <Link
            href="/integrations"
            className="inline-flex items-center gap-2 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
          >
            <ArrowLeft aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
            Back to integrations
          </Link>
        }
        eyebrow="Pilot connector"
        title="Inflow Lab"
        description="Inflow Lab is RegEngine's FSMA 204 boundary workspace for sandbox diagnosis, mock feed validation, and authenticated ingest checks. Mock data never becomes production evidence; evidence export starts from authenticated, persisted tenant records."
      />

      <div className="space-y-10">
        {/* Connector facts */}
        <Card className="overflow-hidden">
          <dl className="grid grid-cols-1 sm:grid-cols-2">
            {statusFacts.map(([label, value], i) => (
              <div
                key={label}
                className={`border-re-border-subtle px-4 py-3 ${i > 0 ? "border-t" : ""} ${i % 2 === 1 ? "sm:border-l" : ""} ${i === 1 ? "sm:border-t-0" : ""}`}
              >
                <dt className="font-mono text-label uppercase text-re-text-muted">{label}</dt>
                <dd className="m-0 mt-1 break-words font-mono text-[0.8125rem] text-re-text-primary">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </Card>

        {/* Boundary path */}
        <section>
          <p className="mb-1 font-mono text-label uppercase text-re-text-muted">Boundary path</p>
          <h2 className="mb-4 text-heading text-re-text-primary">Sandbox to authenticated records</h2>

          <Card className="overflow-hidden">
            <ol className="list-none">
              {livePath.map(([label, detail], index) => (
                <li
                  key={label}
                  className="flex items-start gap-3 border-b border-re-border-subtle px-4 py-3 last:border-0"
                >
                  <span aria-hidden="true" className="mt-0.5 w-5 shrink-0 font-mono text-label text-re-text-muted">
                    {index + 1}
                  </span>
                  <div className="min-w-0">
                    <strong className="block text-ui font-medium text-re-text-primary">{label}</strong>
                    <p className="mt-0.5 break-words font-mono text-small text-re-text-tertiary">{detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>
        </section>

        {/* How it connects */}
        <section>
          <h2 className="mb-4 text-heading text-re-text-primary">How it connects</h2>
          <Card className="overflow-hidden">
            <ul className="list-none">
              {connectionSteps.map((item) => (
                <li
                  key={item}
                  className="flex items-start gap-3 border-b border-re-border-subtle px-4 py-3 last:border-0"
                >
                  <Check aria-hidden="true" strokeWidth={1.75} className="mt-0.5 h-4 w-4 shrink-0 text-re-text-muted" />
                  <p className="min-w-0 text-ui text-re-text-secondary">{item}</p>
                </li>
              ))}
            </ul>
          </Card>
        </section>

        {/* Signed webhook payload */}
        <section>
          <h2 className="mb-3 text-heading text-re-text-primary">Signed webhook payload</h2>
          <p className="mb-4 text-body text-re-text-secondary">
            Use <code className={CODE}>source: &quot;inflow-lab&quot;</code> so dashboard and audit surfaces can distinguish test traffic from generic webhook submissions. Backend routes resolve that public slug to canonical connector id <code className={CODE}>inflow_lab</code>. Production evidence still requires authenticated persisted records.
          </p>
          <div className="space-y-2">
            <p className="font-mono text-label text-re-text-muted">POST /api/v1/webhooks/ingest</p>
            <CodeBlock code={ingestExample} />
          </div>
        </section>

        {/* Local and CI usage */}
        <section>
          <h2 className="mb-3 text-heading text-re-text-primary">Local and CI usage</h2>
          <p className="mb-4 text-body text-re-text-secondary">
            The simulator lives in the RegEngine GitHub organization. Run it locally for contract validation; the RegEngine workflow pins the repo and runs authenticated ingest validation in CI.
          </p>
          <div className="space-y-2">
            <p className="font-mono text-label text-re-text-muted">Local setup</p>
            <CodeBlock code={localRun} />
          </div>
        </section>

        {/* Operational notes */}
        <section>
          <h2 className="mb-4 text-heading text-re-text-primary">Operational notes</h2>
          <div className="space-y-3 text-ui text-re-text-secondary">
            <p>Inflow Lab is a simulator and developer tool, not a production vendor data source.</p>
            <p>Sandbox and mock records are for diagnosis, mapping, and feed monitoring setup. They are not production evidence.</p>
            <p>Cross-repo contract CI should pin the simulator commit that RegEngine expects, then run an authenticated ingest assertion against the local service.</p>
          </div>
        </section>

        <Link
          href="/docs/api"
          className="flex items-center justify-between gap-3 rounded-lg border border-re-border bg-re-surface-card px-4 py-4 text-ui font-medium text-re-text-primary no-underline transition-colors duration-120 hover:border-re-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none"
        >
          Open API docs
          <ArrowRight aria-hidden="true" strokeWidth={1.75} className="h-4 w-4 shrink-0 text-re-text-muted" />
        </Link>
      </div>
    </>
  );
}
