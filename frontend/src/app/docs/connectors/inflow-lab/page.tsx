import type { Metadata } from "next";
import Link from "next/link";
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Code2,
  FlaskConical,
  GitBranch,
  ShieldCheck,
  Terminal,
  Webhook,
} from "lucide-react";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Inflow Lab Connector | RegEngine",
  description:
    "Use Inflow Lab to generate FSMA 204 webhook payloads for RegEngine demos, contract tests, and developer validation.",
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

const statusFacts = [
  ["Public slug", "inflow-lab"],
  ["Backend id", "inflow_lab"],
  ["Repository", "regengine/inflow-lab"],
  ["CI contract", "Live ingest"],
];

const livePath = [
  ["Simulator", "Builds RegEngine-shaped FSMA 204 CTE batches"],
  ["Webhook ingest", "POST /api/v1/webhooks/ingest"],
  ["Alias resolution", "inflow-lab resolves to inflow_lab"],
  ["RegEngine", "Validates, stores, and source-tags events"],
];

const connectionSteps = [
  "Inflow Lab generates RegEngine-shaped FSMA 204 CTE payloads.",
  "The simulator posts batches to /api/v1/webhooks/ingest with source set to inflow-lab.",
  "RegEngine stores the events, preserves source attribution, and runs the same validation path used by production webhook traffic.",
];

export default function InflowLabDocsPage() {
  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <div>
            <Link href="/integrations" className={styles.backLink}>
              <ArrowLeft aria-hidden="true" size={16} />
              Back to integrations
            </Link>

            <p className={styles.kicker}>Pilot connector</p>
            <h1>Inflow Lab</h1>
            <p>
              Inflow Lab is RegEngine&apos;s FSMA 204 simulator for webhook contract tests, sales demos, and developer validation. It sends traceability events into the same ingest API used by customer integrations.
            </p>
            <dl className={styles.statusGrid}>
              {statusFacts.map(([label, value]) => (
                <div key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          </div>

          <aside className={styles.pathPanel}>
            <div className={styles.panelHeader}>
              <span>
                <FlaskConical aria-hidden="true" size={19} />
              </span>
              <div>
                <p className={styles.eyebrow}>Live path</p>
                <h2>Simulator to ingest</h2>
              </div>
            </div>
            {livePath.map(([label, detail], index) => (
              <div key={label} className={styles.pathStep}>
                <span>{index + 1}</span>
                <div>
                  <strong>{label}</strong>
                  <p>{detail}</p>
                </div>
              </div>
            ))}
          </aside>
        </div>
      </section>

      <div className={styles.content}>
        <div className={styles.mainColumn}>
          <section className={styles.card}>
            <h2>
              <Webhook aria-hidden="true" size={21} />
              How it connects
            </h2>
            <div className={styles.checkList}>
              {connectionSteps.map((item) => (
                <div key={item}>
                  <CheckCircle2 aria-hidden="true" size={20} />
                  <p>{item}</p>
                </div>
              ))}
            </div>
          </section>

          <section className={styles.card}>
            <h2>
              <Code2 aria-hidden="true" size={21} />
              Signed webhook payload
            </h2>
            <p>
              Use <code>source: &quot;inflow-lab&quot;</code> so dashboard and audit surfaces can distinguish simulator traffic from generic webhook submissions. Backend routes resolve that public slug to canonical connector id <code>inflow_lab</code>.
            </p>
            <div className={styles.codeBlock}>
              <div>POST /api/v1/webhooks/ingest</div>
              <pre>
                <code>{ingestExample}</code>
              </pre>
            </div>
          </section>

          <section className={styles.card}>
            <h2>
              <GitBranch aria-hidden="true" size={21} />
              Local and CI usage
            </h2>
            <p>
              The simulator lives in the RegEngine GitHub organization. Run it locally for partner demos; the RegEngine workflow pins the repo and runs live ingest contract validation in CI.
            </p>
            <div className={styles.codeBlock}>
              <div>Local setup</div>
              <pre>
                <code>{localRun}</code>
              </pre>
            </div>
          </section>
        </div>

        <aside className={styles.sideColumn}>
          <section className={styles.card}>
            <h2>
              <ShieldCheck aria-hidden="true" size={21} />
              Operational notes
            </h2>
            <div className={styles.notes}>
              <p>Inflow Lab is a simulator and developer tool, not a production vendor data source.</p>
              <p>Hosted access is intentionally separate from this connector tile until a design partner asks for it or it becomes part of the weekly sales motion.</p>
              <p>Cross-repo contract CI should pin the simulator commit that RegEngine expects, then run a live ingest assertion against the local service.</p>
            </div>
          </section>

          <section className={styles.card}>
            <h2>
              <Activity aria-hidden="true" size={21} />
              Decision posture
            </h2>
            <div className={styles.notes}>
              <p>Keep Inflow Lab as a local/demo simulator until a design partner asks for hosted access.</p>
              <p>Promote the connector tile and docs as proof of developer workflow, not as a customer production integration.</p>
            </div>
          </section>

          <Link href="/docs/api" className={styles.apiLink}>
            Open API docs
            <ArrowRight aria-hidden="true" size={16} />
          </Link>
        </aside>
      </div>
    </main>
  );
}
