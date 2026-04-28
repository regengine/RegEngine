import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft, CheckCircle2, Code2, GitBranch, Terminal, Webhook } from 'lucide-react';
import { T as _T } from '@/lib/design-tokens';

const T = {
  ..._T,
  heading: 'var(--re-text-primary)',
  text: 'var(--re-text-secondary)',
  textMuted: 'var(--re-text-muted)',
  surface: 'var(--re-surface-card)',
  border: 'var(--re-surface-border)',
};

export const metadata: Metadata = {
  title: 'Inflow Lab Connector | RegEngine',
  description:
    'Use Inflow Lab to generate FSMA 204 webhook payloads for RegEngine demos, contract tests, and developer validation.',
};

const ingestExample = `curl -X POST https://api.regengine.co/api/v1/webhooks/ingest \\
  -H "Content-Type: application/json" \\
  -H "X-RegEngine-API-Key: re_live_..." \\
  -H "X-Tenant-ID: 00000000-0000-0000-0000-000000000000" \\
  -H "Idempotency-Key: inflow-lab-demo-001" \\
  -d '{
    "tenant_id": "00000000-0000-0000-0000-000000000000",
    "source": "inflow-lab",
    "events": [{
      "cte_type": "shipping",
      "traceability_lot_code": "ROM-2026-0427-A",
      "product_description": "Romaine Lettuce",
      "quantity": 48,
      "unit_of_measure": "cases",
      "location_name": "Inflow Lab Demo DC",
      "timestamp": "2026-04-27T18:30:00Z",
      "kdes": {
        "ship_from_location": "Demo Grower",
        "ship_to_location": "Demo Retailer",
        "carrier": "Inflow Lab Carrier"
      }
    }]
  }'`;

const localRun = `git clone https://github.com/regengine/inflow-lab.git
cd inflow-lab
cp .env.example .env
# Set RE_API_BASE_URL, RE_API_KEY, and RE_TENANT_ID
python -m pytest`;

export default function InflowLabDocsPage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      <div style={{ borderBottom: `1px solid ${T.border}`, padding: '24px' }}>
        <div className="max-w-[780px] mx-auto">
          <Link
            href="/docs"
            className="inline-flex items-center gap-2 text-sm mb-4"
            style={{ color: T.accent, textDecoration: 'none' }}
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Docs
          </Link>

          <div className="flex items-center gap-3 mb-3">
            <Terminal className="w-7 h-7 text-re-brand" />
            <span className="text-[11px] font-semibold px-2.5 py-1 rounded" style={{ background: 'rgba(16,185,129,0.16)', color: T.accent }}>
              Pilot
            </span>
          </div>

          <h1 className="text-[1.75rem] sm:text-[2.5rem] font-bold text-[var(--re-text-primary)] mb-2">
            Inflow Lab Connector
          </h1>
          <p className="text-re-text-muted text-base max-w-[680px]">
            Inflow Lab is RegEngine's FSMA 204 simulator for webhook contract tests, sales demos, and developer validation. It sends traceability events into the same ingest API used by customer integrations.
          </p>
        </div>
      </div>

      <main className="max-w-[780px] mx-auto py-12 px-6">
        <section className="mb-10">
          <h2 className="text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">
            <Webhook className="w-5 h-5 inline align-middle mr-2" />
            How It Connects
          </h2>
          <div className="grid gap-3">
            {[
              'Inflow Lab generates RegEngine-shaped FSMA 204 CTE payloads.',
              'The simulator posts batches to /api/v1/webhooks/ingest with source set to inflow-lab.',
              'RegEngine stores the events, preserves source attribution, and runs the same validation path used by production webhook traffic.',
            ].map((item) => (
              <div key={item} className="flex gap-3 p-4 rounded-lg" style={{ background: T.surface, border: `1px solid ${T.border}` }}>
                <CheckCircle2 className="w-5 h-5 shrink-0 mt-0.5 text-re-brand" />
                <p className="text-sm text-re-text-muted">{item}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">
            <Code2 className="w-5 h-5 inline align-middle mr-2" />
            Webhook Payload
          </h2>
          <p className="text-sm text-re-text-muted mb-4">
            Use <code className="px-1.5 py-0.5 rounded bg-black/30">source: "inflow-lab"</code> so dashboard and audit surfaces can distinguish simulator traffic from generic webhook submissions.
          </p>
          <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${T.border}` }}>
            <div className="px-4 py-2 text-xs text-re-text-muted" style={{ background: 'rgba(255,255,255,0.05)', borderBottom: `1px solid ${T.border}` }}>
              POST /api/v1/webhooks/ingest
            </div>
            <pre className="m-0 p-4 text-[12px] leading-5 overflow-x-auto bg-black/60 text-re-text-muted">
              <code>{ingestExample}</code>
            </pre>
          </div>
        </section>

        <section className="mb-10">
          <h2 className="text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">
            <GitBranch className="w-5 h-5 inline align-middle mr-2" />
            Local Simulator
          </h2>
          <p className="text-sm text-re-text-muted mb-4">
            The simulator lives in the RegEngine GitHub organization at <code className="px-1.5 py-0.5 rounded bg-black/30">regengine/inflow-lab</code>. Use it locally for partner demos and CI contract validation.
          </p>
          <div className="rounded-lg overflow-hidden" style={{ border: `1px solid ${T.border}` }}>
            <div className="px-4 py-2 text-xs text-re-text-muted" style={{ background: 'rgba(255,255,255,0.05)', borderBottom: `1px solid ${T.border}` }}>
              Local setup
            </div>
            <pre className="m-0 p-4 text-[12px] leading-5 overflow-x-auto bg-black/60 text-re-text-muted">
              <code>{localRun}</code>
            </pre>
          </div>
        </section>

        <section>
          <h2 className="text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">Operational Notes</h2>
          <div className="grid gap-3 text-sm text-re-text-muted">
            <p>Inflow Lab is a simulator and developer tool, not a production vendor data source.</p>
            <p>Hosted access is intentionally separate from this connector tile. Keep the local simulator path until a design partner explicitly asks for hosted access or it becomes part of weekly sales motion.</p>
            <p>Cross-repo contract CI should pin the simulator commit that RegEngine expects, then run a live ingest assertion against the local service.</p>
          </div>
        </section>
      </main>
    </div>
  );
}
