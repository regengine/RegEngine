import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight, CheckCircle, Clock, Code, Shield, ShoppingCart,
  Thermometer, FileSpreadsheet, Truck, Server, Webhook, Anchor,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Integrations — Connect Your Supply Chain to RegEngine",
  description:
    "RegEngine integrates with ERPs, food safety platforms, retailers, IoT sensors, and custom systems. CSV, API, webhook, and SFTP ingestion.",
};

interface Integration {
  name: string;
  category: string;
  description: string;
  status: "connected" | "available" | "coming_soon";
  icon: typeof Shield;
}

const INTEGRATIONS: Integration[] = [
  // Food Safety
  { name: "SafetyCulture (iAuditor)", category: "Food Safety", description: "Sync audit results and inspection data automatically", status: "available", icon: Shield },
  { name: "FoodReady", category: "Food Safety", description: "Import food safety plans and HACCP documentation", status: "available", icon: Shield },
  { name: "FoodDocs", category: "Food Safety", description: "Connect food safety management system data", status: "available", icon: Shield },
  { name: "Tive", category: "IoT / Cold Chain", description: "Real-time temperature and location tracking for shipments", status: "available", icon: Thermometer },

  // Retailers
  { name: "Walmart GDSN", category: "Retailer", description: "Sync traceability data with Walmart's GDSN requirements", status: "available", icon: ShoppingCart },
  { name: "Kroger", category: "Retailer", description: "Meet Kroger's supplier traceability mandates", status: "available", icon: ShoppingCart },
  { name: "Whole Foods", category: "Retailer", description: "Whole Foods supplier compliance integration", status: "available", icon: ShoppingCart },
  { name: "Costco", category: "Retailer", description: "Costco food safety and traceability compliance", status: "available", icon: ShoppingCart },

  // ERP
  { name: "Produce Pro", category: "ERP", description: "Map Produce Pro transaction data to FSMA 204 CTEs", status: "coming_soon", icon: FileSpreadsheet },
  { name: "SAP Business One", category: "ERP", description: "Import batch and inventory data from SAP B1 Service Layer", status: "coming_soon", icon: Server },
  { name: "Aptean (Freshlynx)", category: "ERP", description: "Connect Aptean food & beverage ERP data", status: "coming_soon", icon: FileSpreadsheet },
  { name: "Blue Yonder", category: "ERP", description: "Supply chain planning and execution data", status: "coming_soon", icon: Truck },

  // Developer
  { name: "CSV / SFTP", category: "Developer", description: "Upload CSV files or sync via scheduled SFTP transfers", status: "available", icon: FileSpreadsheet },
  { name: "REST API", category: "Developer", description: "Full REST API with OpenAPI docs for custom integrations", status: "available", icon: Code },
  { name: "Webhooks", category: "Developer", description: "Push CTE events in real time via webhook endpoints", status: "available", icon: Webhook },
  { name: "EPCIS 2.0", category: "Developer", description: "GS1 EPCIS 2.0 event import and export", status: "available", icon: Anchor },
];

const CATEGORIES = ["Food Safety", "Retailer", "IoT / Cold Chain", "ERP", "Developer"];

const STATUS_BADGE = {
  connected: { label: "Connected", className: "bg-green-500/15 text-green-400" },
  available: { label: "Available", className: "bg-blue-500/15 text-blue-400" },
  coming_soon: { label: "Coming Soon", className: "bg-amber-500/15 text-amber-400" },
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
        {CATEGORIES.map((cat) => {
          const items = INTEGRATIONS.filter((i) => i.category === cat);
          if (items.length === 0) return null;
          return (
            <div key={cat} className="mb-10">
              <h2 className="text-lg font-semibold mb-4 text-[var(--re-text-primary)]">{cat}</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {items.map((integration) => {
                  const badge = STATUS_BADGE[integration.status];
                  return (
                    <div
                      key={integration.name}
                      className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5 flex items-start gap-4"
                    >
                      <div className="p-2.5 rounded-lg bg-[var(--re-surface-elevated)] flex-shrink-0">
                        <integration.icon className="w-5 h-5 text-[var(--re-brand)]" />
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2 mb-1">
                          <h3 className="text-sm font-semibold">{integration.name}</h3>
                          <span className={`text-[0.6rem] px-1.5 py-0.5 rounded-full font-medium ${badge.className}`}>
                            {badge.label}
                          </span>
                        </div>
                        <p className="text-[0.75rem] text-[var(--re-text-muted)]">{integration.description}</p>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
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
