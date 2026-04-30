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
    "Use Inflow Lab to distinguish sandbox diagnosis, mock feed validation, authenticated ingest, and production evidence boundaries.",
};

const ingestExample = `curl -X POST https://api.regengine.co/api/v1/webhooks/ingest \\
  -H "Content-Type: application/json" \\
  -H "X-RegEngine-API-Key: re_live_..." \\
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
              Inflow Lab is RegEngine&apos;s FSMA 204 boundary workspace for sandbox diagnosis, mock feed validation, and authenticated ingest checks. Mock data never becomes production evidence; evidence export starts from authenticated, persisted tenant records.
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
                <p className={styles.eyebrow}>Boundary path</p>
                <h2>Sandbox to authenticated records</h2>
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
              Use <code>source: &quot;inflow-lab&quot;</code> so dashboard and audit surfaces can distinguish test traffic from generic webhook submissions. Backend routes resolve that public slug to canonical connector id <code>inflow_lab</code>. Production evidence still requires authenticated persisted records.
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
              The simulator lives in the RegEngine GitHub organization. Run it locally for contract validation; the RegEngine workflow pins the repo and runs authenticated ingest validation in CI.
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
              <p>Sandbox and mock records are for diagnosis, mapping, and feed monitoring setup. They are not production evidence.</p>
              <p>Cross-repo contract CI should pin the simulator commit that RegEngine expects, then run an authenticated ingest assertion against the local service.</p>
            </div>
          </section>

          <section className={styles.card}>
            <h2>
              <Activity aria-hidden="true" size={21} />
              Decision posture
            </h2>
            <div className={styles.notes}>
              <p>Keep Inflow Lab as a sandbox/mock simulator until a design partner asks for hosted access.</p>
              <p>Promote the connector tile and docs as proof of operational boundaries, not as a customer production integration.</p>
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
