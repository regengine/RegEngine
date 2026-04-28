import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  Code,
  DatabaseZap,
  ExternalLink,
  FileSpreadsheet,
  FlaskConical,
  GitBranch,
  PackageCheck,
  Shield,
  ShoppingCart,
  Thermometer,
  Webhook,
} from "lucide-react";
import {
  CAPABILITY_REGISTRY,
  DELIVERY_MODE_LABELS,
  INTEGRATION_TYPE_LABELS,
  STATUS_LABELS,
  type CapabilityCategory,
  type CustomerVisibleStatus,
} from "@/lib/customer-readiness";
import styles from "./page.module.css";

export const metadata: Metadata = {
  title: "Integrations - Connect Your Supply Chain to RegEngine",
  description:
    "RegEngine integrates with ERPs, food safety platforms, retailers, IoT sensors, and custom systems. CSV, API, webhook, and SFTP ingestion.",
};

const CATEGORY_ORDER: CapabilityCategory[] = [
  "developer_api",
  "erp_warehouse",
  "food_safety_iot",
  "retailer_network",
  "commercial",
];

const CATEGORY_META: Record<
  CapabilityCategory,
  { title: string; eyebrow: string; icon: typeof Shield }
> = {
  developer_api: { title: "Developer APIs", eyebrow: "Webhook, REST, EPCIS", icon: Code },
  erp_warehouse: { title: "ERP & warehouse", eyebrow: "Files, extracts, mapping", icon: FileSpreadsheet },
  food_safety_iot: { title: "Food safety & IoT", eyebrow: "Audits, sensors, cold chain", icon: Thermometer },
  retailer_network: { title: "Retailer exports", eyebrow: "Outbound packages", icon: ShoppingCart },
  commercial: { title: "Commercial programs", eyebrow: "Scoped partner work", icon: Shield },
};

const ICONS_BY_ID: Record<string, typeof Shield> = {
  "inflow-lab": FlaskConical,
  "rest-api": DatabaseZap,
  webhooks: Webhook,
  epcis: PackageCheck,
  "csv-sftp": FileSpreadsheet,
};

const inflow = CAPABILITY_REGISTRY.find((item) => item.id === "inflow-lab");

function statusClass(status: CustomerVisibleStatus) {
  return `${styles.pill} ${styles[`status_${status}`]}`;
}

export default function IntegrationsPage() {
  const grouped = CATEGORY_ORDER.map((category) => ({
    category,
    ...CATEGORY_META[category],
    items: CAPABILITY_REGISTRY.filter((item) => item.category === category),
  })).filter((group) => group.items.length > 0);

  return (
    <main className={styles.page}>
      <section className={styles.hero}>
        <div className={styles.heroInner}>
          <div className={styles.heroCopy}>
            <div className={styles.kicker}>
              <CheckCircle2 aria-hidden="true" size={16} />
              RegEngine readiness registry
            </div>
            <h1>Integrations that prove FSMA 204 data can move</h1>
            <p>
              Connect simulator events, source-system files, customer APIs, and retailer export packages without overstating what is live. Every entry below is tied to the readiness registry used for diligence and product planning.
            </p>
            <div className={styles.actions}>
              <Link href="/docs/connectors/inflow-lab" className={styles.primaryButton}>
                View Inflow Lab
                <ArrowRight aria-hidden="true" size={16} />
              </Link>
              <Link href="/docs/api" className={styles.secondaryButton}>
                <Code aria-hidden="true" size={16} />
                API docs
              </Link>
            </div>
          </div>

          {inflow && (
            <aside className={styles.featurePanel}>
              <div className={styles.featureTop}>
                <div>
                  <div className={styles.featureIcon}>
                    <FlaskConical aria-hidden="true" size={22} />
                  </div>
                  <p className={styles.eyebrow}>Featured connector</p>
                  <h2>{inflow.name}</h2>
                </div>
                <span className={statusClass(inflow.status)}>{STATUS_LABELS[inflow.status]}</span>
              </div>
              <p className={styles.featureCopy}>{inflow.customer_copy}</p>

              <div className={styles.flowBox}>
                {[
                  ["Inflow Lab", "source: inflow-lab"],
                  ["Signed webhook", "POST /api/v1/webhooks/ingest"],
                  ["RegEngine ingest", "validation + source attribution"],
                  ["Audit surface", "demo-ready FSMA 204 events"],
                ].map(([label, detail], index) => (
                  <div key={label} className={styles.flowStep}>
                    <span>{index + 1}</span>
                    <div>
                      <strong>{label}</strong>
                      <p>{detail}</p>
                    </div>
                  </div>
                ))}
              </div>

              <dl className={styles.featureFacts}>
                <div>
                  <dt>Delivery</dt>
                  <dd>{DELIVERY_MODE_LABELS[inflow.delivery_mode]}</dd>
                </div>
                <div>
                  <dt>Repo</dt>
                  <dd>regengine/inflow-lab</dd>
                </div>
                <div>
                  <dt>Use</dt>
                  <dd>Demos + contract CI</dd>
                </div>
              </dl>
            </aside>
          )}
        </div>
      </section>

      <section className={styles.registry}>
        <div className={styles.registryHeader}>
          <div>
            <p className={styles.eyebrow}>Registry</p>
            <h2>Current integration posture</h2>
          </div>
          <p>
            Status labels are deliberately conservative: GA means generally available; Pilot and Custom Scoped mean guided implementation, validation, or design-partner work.
          </p>
        </div>

        <div className={styles.categoryStack}>
          {grouped.map((group) => {
            const CategoryIcon = group.icon;

            return (
              <section key={group.category} className={styles.category}>
                <header className={styles.categoryHeader}>
                  <div className={styles.categoryTitle}>
                    <span>
                      <CategoryIcon aria-hidden="true" size={20} />
                    </span>
                    <div>
                      <h3>{group.title}</h3>
                      <p>{group.eyebrow}</p>
                    </div>
                  </div>
                  <span className={styles.count}>
                    {group.items.length} {group.items.length === 1 ? "entry" : "entries"}
                  </span>
                </header>

                <div className={styles.rows}>
                  {group.items.map((integration) => {
                    const IntegrationIcon = ICONS_BY_ID[integration.id] ?? group.icon;

                    return (
                      <article key={integration.id} className={styles.integrationRow}>
                        <div className={styles.integrationName}>
                          <span>
                            <IntegrationIcon aria-hidden="true" size={20} />
                          </span>
                          <div>
                            <h4>{integration.name}</h4>
                            <p>{INTEGRATION_TYPE_LABELS[integration.integration_type]}</p>
                          </div>
                        </div>

                        <p className={styles.integrationCopy}>{integration.customer_copy}</p>

                        <div className={styles.rowBadges}>
                          <span className={statusClass(integration.status)}>
                            {STATUS_LABELS[integration.status]}
                          </span>
                          <span className={styles.pill}>
                            {DELIVERY_MODE_LABELS[integration.delivery_mode]}
                          </span>
                          {integration.evidence_url && (
                            <Link href={integration.evidence_url} className={styles.detailPill}>
                              Details
                              <ExternalLink aria-hidden="true" size={13} />
                            </Link>
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            );
          })}
        </div>
      </section>

      <section className={styles.cta}>
        <div>
          <h2>Need a source system scoped?</h2>
          <p>
            Bring the ERP export, supplier file, or API shape into onboarding and RegEngine will map it against the FSMA 204 event model before promising a production connector.
          </p>
        </div>
        <div className={styles.actions}>
          <Link href="/contact" className={styles.primaryButton}>
            Request an integration
            <ArrowRight aria-hidden="true" size={16} />
          </Link>
          <Link href="/trust" className={styles.secondaryButton}>
            <GitBranch aria-hidden="true" size={16} />
            View evidence
          </Link>
        </div>
      </section>
    </main>
  );
}
