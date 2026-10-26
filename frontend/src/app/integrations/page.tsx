import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Activity,
  Code,
  DatabaseZap,
  ExternalLink,
  FileSpreadsheet,
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
  developer_api: { title: "Developer APIs", eyebrow: "CSV upload, JSON events API, EPCIS (Preview)", icon: Code },
  erp_warehouse: { title: "ERP & warehouse", eyebrow: "Files, extracts, mapping", icon: FileSpreadsheet },
  food_safety_iot: { title: "Food safety & IoT", eyebrow: "Audits, sensors, cold chain", icon: Thermometer },
  retailer_network: { title: "Retailer exports", eyebrow: "Outbound packages", icon: ShoppingCart },
  commercial: { title: "Commercial programs", eyebrow: "Scoped partner work", icon: Shield },
};

const ICONS_BY_ID: Record<string, typeof Shield> = {
  "rest-api": DatabaseZap,
  webhooks: Webhook,
  epcis: PackageCheck,
  "csv-sftp": FileSpreadsheet,
};

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

/** dt/dd fact pair styling used by the hero eyebrow. */
const factTermClass = "font-mono text-label uppercase text-re-text-muted";

export default function IntegrationsPage() {
  const grouped = CATEGORY_ORDER.map((category) => ({
    category,
    ...CATEGORY_META[category],
    items: CAPABILITY_REGISTRY.filter((item) => item.category === category),
  })).filter((group) => group.items.length > 0);

  return (
    <div className="bg-re-surface-base">
      <Container as="section" width="marketing" className="grid items-start gap-10 py-12 sm:py-16">
        <div>
          <p className={cn(factTermClass, "mb-4")}>Supplier data intake</p>
          <h1 className="max-w-[20ch] font-display text-display text-re-text-primary">
            Know which sources are ready, guided, or custom scoped.
          </h1>
          <p className="mt-5 max-w-[68ch] text-body text-re-text-secondary">
            A compact view of available intake modes, guided workflows, and custom-scoped implementation paths. Named vendor and retailer workflows require scope confirmation and evidence review before being treated as production connectors. Send records by CSV upload or the JSON events API. EPCIS 2.0 is in Preview.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Button asChild variant="secondary" size="lg">
              <Link href="/docs/api" className="no-underline">
                <Code aria-hidden="true" className="h-4 w-4" strokeWidth={1.75} />
                API docs
              </Link>
            </Button>
          </div>
        </div>
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
                            className="grid gap-x-6 gap-y-3 px-5 py-4 lg:grid-cols-[minmax(0,15rem)_minmax(0,1fr)_auto] lg:items-start"
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
