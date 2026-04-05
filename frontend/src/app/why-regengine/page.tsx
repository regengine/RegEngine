import type { Metadata } from "next";
import Link from "next/link";
import {
  ArrowRight,
  Code2,
  Clock,
  Shield,
  Zap,
  Database,
  FileSpreadsheet,
  Users,
  CheckCircle,
  X,
} from "lucide-react";

export const metadata: Metadata = {
  title: "Why RegEngine — API-First FSMA 204 Compliance | RegEngine",
  description:
    "The only FSMA 204 platform built API-first. Compare RegEngine to FoodLogiQ, ReposiTrak, TraceGains, and SafetyChain — see why technical teams choose us.",
  openGraph: {
    title: "Why RegEngine — API-First FSMA 204 Compliance",
    description:
      "Compare RegEngine to legacy compliance vendors. API-first architecture, self-serve signup, transparent pricing.",
    type: "website",
  },
};

const DIFFERENTIATORS = [
  {
    icon: Code2,
    title: "API-First Architecture",
    description:
      "Every feature is accessible via REST API with OpenAPI documentation. Integrate traceability into your existing ERP, WMS, or IoT stack — no manual re-entry.",
    competitors: "Legacy vendors require manual portal uploads or expensive custom integrations.",
  },
  {
    icon: Clock,
    title: "Minutes to First CTE",
    description:
      "Sign up, get an API key, and submit your first Critical Tracking Event in under 15 minutes. No implementation consultants, no 6-week onboarding.",
    competitors: "Competitors require weeks of implementation with dedicated project managers.",
  },
  {
    icon: Zap,
    title: "Self-Serve Everything",
    description:
      "Create your account, configure your supply chain, upload data, and export FDA-ready records — all without talking to sales.",
    competitors: "Every competitor requires a demo call before you can even see pricing.",
  },
  {
    icon: Database,
    title: "Developer Sandbox",
    description:
      "A free sandbox environment with sample data, Postman collections, and SDKs. Test your integration before going live.",
    competitors: "No competitor offers a developer sandbox or public API documentation.",
  },
  {
    icon: Shield,
    title: "Transparent Pricing",
    description:
      "Published, per-facility pricing on the website. No hidden fees, no per-record charges, no surprise invoices after you exceed an undisclosed limit.",
    competitors: "Most vendors hide pricing behind sales calls. Some charge per-record fees that scale unpredictably.",
  },
  {
    icon: FileSpreadsheet,
    title: "Multi-Format Ingestion",
    description:
      "Upload via API, CSV, webhook, or our guided UI. We normalize everything into FSMA 204-compliant records automatically.",
    competitors: "Competitors typically support only their proprietary portal or a single CSV format.",
  },
];

type FeatureRow = {
  feature: string;
  regengine: string | boolean;
  foodlogiq: string | boolean;
  repositrak: string | boolean;
  tracegains: string | boolean;
};

const COMPARISON: FeatureRow[] = [
  { feature: "Public REST API", regengine: true, foodlogiq: false, repositrak: false, tracegains: false },
  { feature: "OpenAPI Documentation", regengine: true, foodlogiq: false, repositrak: false, tracegains: false },
  { feature: "Self-Serve Signup", regengine: true, foodlogiq: false, repositrak: false, tracegains: false },
  { feature: "Developer Sandbox", regengine: true, foodlogiq: false, repositrak: false, tracegains: false },
  { feature: "Published Pricing", regengine: true, foodlogiq: false, repositrak: true, tracegains: false },
  { feature: "Free Compliance Tools", regengine: "12 tools", foodlogiq: false, repositrak: false, tracegains: false },
  { feature: "CSV + API + Webhook Ingestion", regengine: true, foodlogiq: "Portal only", repositrak: "Portal + CSV", tracegains: "Portal only" },
  { feature: "Time to First FDA-Ready Export", regengine: "< 15 min", foodlogiq: "Weeks", repositrak: "Hours–days", tracegains: "Weeks" },
  { feature: "FDA Export (sortable spreadsheet)", regengine: true, foodlogiq: true, repositrak: true, tracegains: true },
  { feature: "24-Hour Recall Readiness", regengine: true, foodlogiq: true, repositrak: true, tracegains: true },
];

function CellValue({ value }: { value: string | boolean }) {
  if (value === true) return <CheckCircle className="w-5 h-5 mx-auto" style={{ color: "var(--re-brand)" }} />;
  if (value === false) return <X className="w-5 h-5 mx-auto" style={{ color: "var(--re-text-muted)" }} />;
  return <span className="text-sm">{value}</span>;
}

const PERSONAS = [
  {
    icon: Code2,
    title: "For Engineering Teams",
    points: [
      "REST API with typed SDKs (Python, TypeScript)",
      "Webhook events for real-time pipeline integration",
      "OpenAPI spec you can import into Postman or generate clients from",
      "Sandbox environment with realistic sample data",
    ],
  },
  {
    icon: Users,
    title: "For Compliance Teams",
    points: [
      "Guided onboarding walks you through FSMA 204 requirements",
      "12 free compliance tools (FTL checker, CTE mapper, readiness assessment)",
      "One-click FDA export with sortable, audit-ready records",
      "Gap analysis shows exactly what's missing before an inspection",
    ],
  },
  {
    icon: Shield,
    title: "For Operations Leaders",
    points: [
      "Transparent pricing — no per-record fees or surprise invoices",
      "SOC 2 Type II security with encrypted data at rest and in transit",
      "3-year data retention exceeds FSMA's 2-year requirement",
      "Multi-tenant architecture with strict data isolation",
    ],
  },
];

export default function WhyRegenginePage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)]">
      {/* Hero */}
      <section className="max-w-[900px] mx-auto px-6 pt-16 pb-12 md:pt-24 md:pb-16">
        <h1
          className="text-3xl md:text-5xl font-bold mb-4"
          style={{ color: "var(--re-text-primary)" }}
        >
          The Only FSMA 204 Platform Built API-First
        </h1>
        <p
          className="text-lg md:text-xl mb-8"
          style={{ color: "var(--re-text-secondary)" }}
        >
          Legacy compliance vendors make you upload spreadsheets to a portal.
          RegEngine gives you a real API, transparent pricing, and self-serve
          signup — so your team can ship compliance instead of waiting for
          implementation consultants.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/signup"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-medium text-white"
            style={{ backgroundColor: "var(--re-brand)" }}
          >
            Start Free <ArrowRight className="w-4 h-4" />
          </Link>
          <Link
            href="/developers"
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-medium"
            style={{ border: "1px solid var(--re-surface-border)", color: "var(--re-text-primary)" }}
          >
            View API Docs
          </Link>
        </div>
      </section>

      {/* Differentiators */}
      <section className="max-w-[900px] mx-auto px-6 py-12 md:py-16">
        <h2
          className="text-2xl md:text-3xl font-bold mb-8"
          style={{ color: "var(--re-text-primary)" }}
        >
          What Makes RegEngine Different
        </h2>
        <div className="grid md:grid-cols-2 gap-6">
          {DIFFERENTIATORS.map((d) => (
            <div
              key={d.title}
              className="p-6 rounded-xl"
              style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
            >
              <d.icon className="w-6 h-6 mb-3" style={{ color: "var(--re-brand)" }} />
              <h3
                className="text-lg font-semibold mb-2"
                style={{ color: "var(--re-text-primary)" }}
              >
                {d.title}
              </h3>
              <p className="text-sm mb-3" style={{ color: "var(--re-text-secondary)" }}>
                {d.description}
              </p>
              <p className="text-xs" style={{ color: "var(--re-text-muted)" }}>
                <em>Competitors:</em> {d.competitors}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* Comparison Table */}
      <section className="max-w-[900px] mx-auto px-6 py-12 md:py-16">
        <h2
          className="text-2xl md:text-3xl font-bold mb-8"
          style={{ color: "var(--re-text-primary)" }}
        >
          Feature Comparison
        </h2>
        <div className="overflow-x-auto rounded-xl" style={{ border: "1px solid var(--re-surface-border)" }}>
          <table className="w-full text-sm">
            <thead>
              <tr style={{ backgroundColor: "var(--re-surface-card)" }}>
                <th className="text-left p-3 font-medium" style={{ color: "var(--re-text-muted)" }}>Feature</th>
                <th className="text-center p-3 font-semibold" style={{ color: "var(--re-brand)" }}>RegEngine</th>
                <th className="text-center p-3 font-medium" style={{ color: "var(--re-text-muted)" }}>FoodLogiQ</th>
                <th className="text-center p-3 font-medium" style={{ color: "var(--re-text-muted)" }}>ReposiTrak</th>
                <th className="text-center p-3 font-medium" style={{ color: "var(--re-text-muted)" }}>TraceGains</th>
              </tr>
            </thead>
            <tbody>
              {COMPARISON.map((row, i) => (
                <tr
                  key={row.feature}
                  style={{
                    backgroundColor: i % 2 === 0 ? "transparent" : "var(--re-surface-card)",
                    borderTop: "1px solid var(--re-surface-border)",
                  }}
                >
                  <td className="p-3 font-medium" style={{ color: "var(--re-text-primary)" }}>{row.feature}</td>
                  <td className="p-3 text-center"><CellValue value={row.regengine} /></td>
                  <td className="p-3 text-center" style={{ color: "var(--re-text-secondary)" }}><CellValue value={row.foodlogiq} /></td>
                  <td className="p-3 text-center" style={{ color: "var(--re-text-secondary)" }}><CellValue value={row.repositrak} /></td>
                  <td className="p-3 text-center" style={{ color: "var(--re-text-secondary)" }}><CellValue value={row.tracegains} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-xs mt-3" style={{ color: "var(--re-text-muted)" }}>
          Competitor data from public sources as of April 2026.
        </p>
      </section>

      {/* Personas */}
      <section className="max-w-[900px] mx-auto px-6 py-12 md:py-16">
        <h2
          className="text-2xl md:text-3xl font-bold mb-8"
          style={{ color: "var(--re-text-primary)" }}
        >
          Built for Every Stakeholder
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          {PERSONAS.map((p) => (
            <div
              key={p.title}
              className="p-6 rounded-xl"
              style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
            >
              <p.icon className="w-6 h-6 mb-3" style={{ color: "var(--re-brand)" }} />
              <h3
                className="text-lg font-semibold mb-3"
                style={{ color: "var(--re-text-primary)" }}
              >
                {p.title}
              </h3>
              <ul className="space-y-2">
                {p.points.map((point) => (
                  <li key={point} className="flex items-start gap-2 text-sm">
                    <CheckCircle className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: "var(--re-brand)" }} />
                    <span style={{ color: "var(--re-text-secondary)" }}>{point}</span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="max-w-[900px] mx-auto px-6 py-12 md:py-20">
        <div
          className="p-8 md:p-12 rounded-xl text-center"
          style={{ backgroundColor: "var(--re-surface-card)", border: "1px solid var(--re-surface-border)" }}
        >
          <h2
            className="text-2xl md:text-3xl font-bold mb-4"
            style={{ color: "var(--re-text-primary)" }}
          >
            Ready to See the Difference?
          </h2>
          <p className="mb-6 max-w-lg mx-auto" style={{ color: "var(--re-text-secondary)" }}>
            Start a 14-day free trial. Go from signup to your first FDA-ready
            export in under 15 minutes — no implementation required.
          </p>
          <div className="flex flex-wrap justify-center gap-3">
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-medium text-white"
              style={{ backgroundColor: "var(--re-brand)" }}
            >
              Start Free <ArrowRight className="w-4 h-4" />
            </Link>
            <Link
              href="/pricing"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-lg font-medium"
              style={{ border: "1px solid var(--re-surface-border)", color: "var(--re-text-primary)" }}
            >
              View Pricing
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
