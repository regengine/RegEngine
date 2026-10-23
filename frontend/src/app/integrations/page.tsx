import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Activity,
  Code,
  DatabaseZap,
  ExternalLink,
  FileSpreadsheet,
  FlaskConical,
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
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Container } from "@/components/layout/container";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "Integrations: Supplier Data Intake | RegEngine",
  description:
    "RegEngine accepts supplier data via CSV upload and the JSON events API, with custom-scoped connectors for ERP, food-safety, and retailer systems. EPCIS 2.0 is in Preview.",
  openGraph: {
    title: 'Integrations: Supplier Data Intake | RegEngine',
    description: 'CSV upload and JSON events API intake, plus custom-scoped connectors for ERP, food-safety, and retailer systems. EPCIS 2.0 is in Preview.',
    url: 'https://regengine.co/integrations',
    type: 'website',
  },
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
  developer_api: { title: "Developer APIs", eyebrow: "REST, JSON events, EPCIS export", icon: Code },
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

const proofStats = [
  ["Connector slug", "inflow-lab"],
  ["Backend id", "inflow_lab"],
  ["CI coverage", "Contract test"],
];

const inflowPath = [
  ["Simulator", "Generates FSMA 204 CTE batches"],
  ["JSON events API", "POST /api/v1/webhooks/ingest"],
  ["Registry alias", "inflow-lab -> inflow_lab"],
  ["RegEngine", "Validates, stores, and tags events"],
];

/**
 * Nine customer-visible statuses collapse onto the five system tones. The label
 * text is always rendered beside the tone, so colour never carries the status
 * on its own (SPEC §1.6).
 */
const STATUS_TONE: Record<CustomerVisibleStatus, BadgeTone> = {
  implemented: "success",
  supported: "success",
  pilot: "info",
  design_partner: "info",
  export_supported: "neutral",
  file_import_supported: "neutral",
  custom_scoped: "warning",
  preparation: "warning",
  contract_only: "neutral",
};

/** dt/dd fact pair used by both the hero proof row and the featured panel. */
const factTermClass = "font-mono text-label uppercase text-re-text-muted";
const factValueClass = "mt-1 text-ui text-re-text-primary";

export default function IntegrationsPage() {
  const grouped = CATEGORY_ORDER.map((category) => ({
    category,
    ...CATEGORY_META[category],
    items: CAPABILITY_REGISTRY.filter((item) => item.category === category),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="bg-re-surface-base">
      <Container as="section" width="marketing" className="grid items-start gap-10 py-12 sm:py-16 lg:grid-cols-[minmax(0,1fr)_minmax(0,430px)]">
        <div>
          <p className={cn(factTermClass, "mb-4")}>Supplier data intake</p>
          <h1 className="max-w-[20ch] font-display text-display text-re-text-primary">
            Know which sources are ready, guided, or custom scoped.
          </h1>
          <p className="mt-5 max-w-[68ch] text-body text-re-text-secondary">
            A compact view of available intake modes, guided workflows, and custom-scoped implementation paths. Named vendor and retailer workflows require scope confirmation and evidence review before being treated as production connectors. Send records by CSV upload or the JSON events API. EPCIS 2.0 is in Preview. Inflow Lab is the simulator path for JSON events API demos and contract CI.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild size="lg">
              <Link href="/docs/connectors/inflow-lab" className="no-underline">
                Open Inflow docs
                <ArrowRight aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/docs/api" className="no-underline">
                <Code aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} />
                API docs
              </Link>
            </Button>
          </div>
          <dl className="mt-10 grid gap-x-8 gap-y-4 border-t border-re-border-subtle pt-6 sm:grid-cols-3">
            {proofStats.map(([label, value]) => (
              <div key={label}>
                <dt className={factTermClass}>{label}</dt>
                <dd className={factValueClass}>{value}</dd>
              </div>
            ))}
          </dl>
        </div>

        {inflow && (
          <aside>
            <Card padding="spacious">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className={cn(factTermClass, "inline-flex items-center gap-1.5")}>
                    <FlaskConical aria-hidden="true" className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
                    Featured path
                  </p>
                  <h2 className="mt-1 text-heading text-re-text-primary">{inflow.name}</h2>
                </div>
                <Badge tone={STATUS_TONE[inflow.status]} size="sm">{STATUS_LABELS[inflow.status]}</Badge>
              </div>
              <p className="mt-3 text-ui leading-relaxed text-re-text-secondary">{inflow.customer_copy}</p>

              <div className="mt-6 divide-y divide-re-border-subtle rounded-md border border-re-border-subtle bg-re-surface-inset">
                {inflowPath.map(([label, detail], index) => (
                  <div key={label} className="flex gap-3 px-4 py-3">
                    <span className="font-mono text-label text-re-text-muted">{index + 1}</span>
                    <div className="min-w-0">
                      <strong className="block text-ui font-medium text-re-text-primary">{label}</strong>
                      <p className="mt-0.5 break-words text-small text-re-text-tertiary">{detail}</p>
                    </div>
                  </div>
                ))}
              </div>

              <dl className="mt-6 divide-y divide-re-border-subtle border-t border-re-border-subtle">
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
                  <dt className={factTermClass}>Delivery</dt>
                  <dd className="text-ui text-re-text-primary">{DELIVERY_MODE_LABELS[inflow.delivery_mode]}</dd>
                </div>
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
                  <dt className={factTermClass}>Repo</dt>
                  <dd className="font-mono text-[0.8125rem] text-re-text-primary">regengine/inflow-lab</dd>
                </div>
                <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 py-2.5">
                  <dt className={factTermClass}>Endpoint</dt>
                  <dd className="font-mono text-[0.8125rem] text-re-text-primary">/webhooks/ingest</dd>
                </div>
              </dl>
            </Card>
          </aside>
        )}
      </Container>

      <section className="border-t border-re-border-subtle">
        <Container width="marketing" className="py-16 sm:py-20">
          <div className="mb-10 max-w-[68ch] space-y-3">
            <div>
              <h2 className="font-display text-heading-lg text-re-text-primary">Current integration posture</h2>
            </div>
            <p className="text-ui text-re-text-secondary sm:text-body">
              Status labels stay conservative. Implemented and Supported mean usable in supported workspaces; Pilot means validated but guided; Preparation and Contract-only items require explicit diligence; Custom Scoped means implementation work should be explicitly estimated.
            </p>
          </div>

          <div className="space-y-8">
            {grouped.map((group) => {
              const CategoryIcon = group.icon;

              return (
                <section key={group.category}>
                  <Card>
                    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-re-border-subtle px-5 py-4">
                      <div className="min-w-0">
                        <h3 className="text-subheading text-re-text-primary">{group.title}</h3>
                        <p className="mt-0.5 inline-flex items-center gap-1.5 text-small text-re-text-tertiary">
                          <CategoryIcon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
                          {group.eyebrow}
                        </p>
                      </div>
                      <span className="shrink-0 font-mono text-label uppercase text-re-text-muted">
                        {group.items.length} {group.items.length === 1 ? "entry" : "entries"}
                      </span>
                    </header>

                    <div className="divide-y divide-re-border-subtle">
                      {group.items.map((integration) => {
                        const IntegrationIcon = ICONS_BY_ID[integration.id] ?? group.icon;

                        return (
                          <article
                            key={integration.id}
                            className={cn(
                              "grid gap-x-6 gap-y-3 px-5 py-4 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_auto] lg:items-start",
                              integration.id === "inflow-lab" && "bg-re-surface-inset",
                            )}
                          >
                            <div className="min-w-0">
                              <h4 className="text-ui font-medium text-re-text-primary">{integration.name}</h4>
                              <p className="mt-0.5 inline-flex items-center gap-1.5 text-small text-re-text-tertiary">
                                <IntegrationIcon aria-hidden="true" className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} />
                                {INTEGRATION_TYPE_LABELS[integration.integration_type]}
                              </p>
                            </div>

                            <p className="min-w-0 text-ui leading-relaxed text-re-text-secondary">{integration.customer_copy}</p>

                            <div className="flex flex-wrap items-center gap-2 lg:justify-end">
                              <Badge tone={STATUS_TONE[integration.status]} size="sm">
                                {STATUS_LABELS[integration.status]}
                              </Badge>
                              <Badge tone="neutral" size="sm">
                                {DELIVERY_MODE_LABELS[integration.delivery_mode]}
                              </Badge>
                              {integration.evidence_url && (
                                <Button asChild variant="ghost" size="sm">
                                  <Link href={integration.evidence_url} className="no-underline">
                                    Details
                                    <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" strokeWidth={1.75} />
                                  </Link>
                                </Button>
                              )}
                            </div>
                          </article>
                        );
                      })}
                    </div>
                  </Card>
                </section>
              );
            })}
          </div>
        </Container>
      </section>

      <section className="border-t border-re-border-subtle bg-re-surface-inset">
        <Container width="marketing" className="flex flex-col items-start gap-6 py-16 sm:py-20 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-[68ch]">
            <h2 className="font-display text-heading-lg text-re-text-primary">Need another source scoped?</h2>
            <p className="mt-3 text-body text-re-text-secondary">
              Bring the ERP export, supplier file, or API shape into onboarding and RegEngine will map it against the FSMA 204 event model before promising a production connector.
            </p>
          </div>
          <div className="flex flex-wrap gap-3 lg:shrink-0">
            <Button asChild size="lg">
              <Link href="/contact" className="no-underline">
                Scope integration
                <ArrowRight aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} />
              </Link>
            </Button>
            <Button asChild variant="secondary" size="lg">
              <Link href="/trust" className="no-underline">
                <Activity aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} />
                Trust Center
              </Link>
            </Button>
          </div>
        </Container>
      </section>
    </div>
  );
}
