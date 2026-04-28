import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Code,
  ExternalLink,
  FileSpreadsheet,
  FlaskConical,
  Shield,
  ShoppingCart,
  Thermometer,
  Webhook,
} from "lucide-react";
import {
  CAPABILITY_REGISTRY,
  DELIVERY_MODE_LABELS,
  STATUS_LABELS,
  type CapabilityCategory,
  type CustomerVisibleStatus,
} from "@/lib/customer-readiness";

export const metadata: Metadata = {
  title: "Integrations — Connect Your Supply Chain to RegEngine",
  description:
    "RegEngine integrates with ERPs, food safety platforms, retailers, IoT sensors, and custom systems. CSV, API, webhook, and SFTP ingestion.",
};

const CATEGORIES: Array<{ id: CapabilityCategory; title: string; icon: typeof Shield }> = [
  { id: "food_safety_iot", title: "Food safety & IoT", icon: Thermometer },
  { id: "erp_warehouse", title: "ERP & warehouse", icon: FileSpreadsheet },
  { id: "retailer_network", title: "Retailer exports", icon: ShoppingCart },
  { id: "developer_api", title: "Developer APIs", icon: Code },
  { id: "commercial", title: "Commercial programs", icon: Shield },
];

const STATUS_BADGE: Record<CustomerVisibleStatus, string> = {
  ga: "bg-emerald-500/15 text-emerald-300 border-emerald-500/25",
  pilot: "bg-sky-500/15 text-sky-300 border-sky-500/25",
  design_partner: "bg-fuchsia-500/15 text-fuchsia-300 border-fuchsia-500/25",
  export_supported: "bg-cyan-500/15 text-cyan-300 border-cyan-500/25",
  file_import_supported: "bg-indigo-500/15 text-indigo-300 border-indigo-500/25",
  custom_scoped: "bg-amber-500/15 text-amber-300 border-amber-500/25",
};

const ICONS_BY_ID: Record<string, typeof Shield> = {
  "inflow-lab": FlaskConical,
  "webhooks": Webhook,
  "csv-sftp": FileSpreadsheet,
};

export default function IntegrationsPage() {
  return (
    <div className="min-h-screen bg-[#0f1117] text-white">
      <div className="max-w-5xl mx-auto px-4 py-16">
        {/* Hero */}
        <div className="text-center mb-12">
          <h1 className="text-3xl md:text-4xl font-bold mb-4">Integrations</h1>
          <p className="text-[var(--re-text-muted)] text-lg max-w-2xl mx-auto">
            Connect your ERP, food safety platform, retailer mandates, and IoT sensors.
            RegEngine ingests data from anywhere and validates it against FSMA 204 rules.
          </p>
        </div>

        {/* Integration grid by category */}
        {CATEGORIES.map((category) => {
          const items = CAPABILITY_REGISTRY.filter((item) => item.category === category.id);
          if (items.length === 0) return null;
          const CategoryIcon = category.icon;

          return (
            <section key={category.id} className="mb-10">
              <h2 className="text-lg font-semibold mb-4 text-[var(--re-text-primary)] flex items-center gap-2">
                <CategoryIcon className="h-5 w-5 text-[var(--re-brand)]" />
                {category.title}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {items.map((integration) => {
                  const IntegrationIcon = ICONS_BY_ID[integration.id] ?? category.icon;

                  return (
                    <div
                      key={integration.id}
                      className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5 flex items-start gap-4"
                    >
                      <div className="p-2.5 rounded-lg bg-[var(--re-surface-elevated)] flex-shrink-0">
                        <IntegrationIcon className="w-5 h-5 text-[var(--re-brand)]" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex flex-wrap items-center gap-2 mb-1">
                          <h3 className="text-sm font-semibold">{integration.name}</h3>
                          <span className={`text-[0.6rem] px-1.5 py-0.5 rounded-full border font-medium ${STATUS_BADGE[integration.status]}`}>
                            {STATUS_LABELS[integration.status]}
                          </span>
                          <span className="text-[0.6rem] px-1.5 py-0.5 rounded-full border border-white/10 bg-white/5 text-[var(--re-text-muted)] font-medium">
                            {DELIVERY_MODE_LABELS[integration.delivery_mode]}
                          </span>
                        </div>
                        <p className="text-[0.75rem] text-[var(--re-text-muted)]">{integration.customer_copy}</p>
                        {integration.evidence_url && (
                          <Link
                            href={integration.evidence_url}
                            className="mt-3 inline-flex items-center gap-1 text-[0.72rem] font-medium text-[var(--re-brand)] hover:text-[var(--re-brand-light)]"
                          >
                            View details <ExternalLink className="h-3 w-3" />
                          </Link>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>
          );
        })}

        {/* Request integration CTA */}
        <div className="bg-gradient-to-r from-[var(--re-brand)]/10 to-purple-500/10 border border-[var(--re-brand)]/20 rounded-xl p-8 text-center mt-8">
          <h2 className="text-xl font-bold mb-2">Don&apos;t see your system?</h2>
          <p className="text-[var(--re-text-muted)] text-sm mb-6">
            We build custom integrations for mid-market food companies.
            Tell us what you use and we&apos;ll scope it in your onboarding call.
          </p>
          <div className="flex items-center justify-center gap-4">
            <Link
              href="/contact"
              className="inline-flex items-center gap-2 bg-[var(--re-brand)] text-white px-6 py-2.5 rounded-lg text-sm font-semibold hover:bg-[var(--re-brand-dark)] transition-colors"
            >
              Request an Integration <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/docs/api"
              className="inline-flex items-center gap-2 bg-white/10 text-white px-6 py-2.5 rounded-lg text-sm font-medium hover:bg-white/20 transition-colors"
            >
              <Code className="w-4 h-4" />
              API Docs
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
