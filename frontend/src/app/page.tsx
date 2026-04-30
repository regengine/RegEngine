import Link from "next/link";
import type { Metadata } from "next";
import {
  Activity,
  ArrowRight,
  Boxes,
  BookOpen,
  Building2,
  Calculator,
  CheckCircle2,
  ClipboardCheck,
  Code2,
  Database,
  Factory,
  FileText,
  Leaf,
  Network,
  PackageCheck,
  RadioTower,
  Route,
  ScanLine,
  Shield,
  ShieldCheck,
  Store,
  Thermometer,
  Truck,
  AlertTriangle,
  Clock,
  Zap,
} from "lucide-react";
import { DataTransformDemo } from "@/components/marketing/DataTransformDemo";
import { SandboxUpload } from "@/components/marketing/SandboxUpload";

/* ------------------------------------------------------------------ */
/*  SEO METADATA                                                       */
/* ------------------------------------------------------------------ */
export const metadata: Metadata = {
  title: "RegEngine — Food Traceability That Protects Your Brand",
  description:
    "Supply chain traceability infrastructure for food companies. Respond to recall requests in minutes, satisfy Walmart and Kroger supplier requirements, and build the visibility your brand depends on.",
  keywords: [
    "food traceability software",
    "supply chain traceability",
    "FSMA 204 compliance software",
    "food traceability API",
    "retailer supplier traceability",
    "FDA traceability rule",
    "food safety compliance",
  ],
  openGraph: {
    title: "RegEngine — Food Traceability That Protects Your Brand",
    description:
      "FSMA 204 Food Traceability Compliance",
    url: "https://regengine.co",
    type: "website",
    images: [{ url: "/og-image.png", width: 1200, height: 630, alt: "RegEngine FSMA 204 traceability compliance" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "RegEngine — Food Traceability That Protects Your Brand",
    description:
      "Supply chain traceability infrastructure for food companies.",
    images: ["/og-image.png"],
  },
};

/* ------------------------------------------------------------------ */
/*  DATA                                                               */
/* ------------------------------------------------------------------ */

const TRUST_SIGNALS = [
  "First evidence package in 48 hours",
  "1hr 40min recall response",
  "API-first",
  "Built for FSMA 204",
];

const COMMAND_TIMELINE = [
  {
    stage: "Harvest CTE",
    facility: "Valley Fresh Farms",
    detail: "Romaine Lot R-2026-0312",
    time: "07:42",
    icon: Leaf,
    color: "var(--re-decomposition)",
    bg: "rgba(16,185,129,0.12)",
  },
  {
    stage: "Cooling",
    facility: "Central Valley Packhouse",
    detail: "Temperature log attached",
    time: "09:18",
    icon: Factory,
    color: "var(--re-discovery)",
    bg: "rgba(59,130,246,0.12)",
  },
  {
    stage: "Distribution",
    facility: "Northwest DC",
    detail: "Bill of lading matched",
    time: "13:06",
    icon: Truck,
    color: "var(--re-linkage)",
    bg: "rgba(168,85,247,0.12)",
  },
  {
    stage: "Retail handoff",
    facility: "Kroger + Walmart packets",
    detail: "Evidence package assembled",
    time: "15:24",
    icon: Store,
    color: "var(--re-evidence)",
    bg: "rgba(245,158,11,0.14)",
  },
];

const HERO_STATUS_CARDS = [
  { label: "CTEs found", value: "12/12", color: "var(--re-decomposition)" },
  { label: "Supplier names", value: "Normalized", color: "var(--re-discovery)" },
  { label: "Chain links", value: "Verified", color: "var(--re-linkage)" },
  { label: "Evidence pack", value: "Assembled", color: "var(--re-evidence)" },
];

const OPERATIONAL_STATS = [
  {
    value: "1hr 40min",
    label: "Average recall response time with RegEngine — vs. days with manual processes",
  },
  {
    value: "8+ hrs",
    label: "Traceability labor saved per facility on average",
  },
  {
    value: "Walmart · Costco · Kroger",
    label: "Major retailers actively requiring supplier traceability documentation",
    compact: true,
  },
];

const OPERATIONS_LANES = [
  {
    title: "FDA request",
    status: "24h clock started",
    desc: "Records package queued with lot history, CTE chain, and evidence attachments.",
    icon: RadioTower,
    color: "var(--re-discovery)",
  },
  {
    title: "Retailer readiness",
    status: "Walmart · Kroger · Costco",
    desc: "Supplier documentation and retailer-specific fields stay visible before an audit.",
    icon: ClipboardCheck,
    color: "var(--re-linkage)",
  },
  {
    title: "Brand exposure",
    status: "Gaps surfaced early",
    desc: "Missing KDEs, duplicate lots, and supplier mismatches are flagged before they become recall drag.",
    icon: ShieldCheck,
    color: "var(--re-evidence)",
  },
];

const BRAND_PROTECTION_CARDS = [
  {
    icon: Clock,
    title: "Recall response in minutes, not days",
    desc: "The FDA gives you 24 hours. Manual spreadsheet processes average 3–5 days. RegEngine gets you there in under 2.",
  },
  {
    icon: ShieldCheck,
    title: "Retailer requirements are here now",
    desc: "Walmart, Kroger, Costco, and Target require traceability from suppliers. One failed audit means shelf removal.",
  },
  {
    icon: AlertTriangle,
    title: "One contamination incident costs millions",
    desc: "Brand damage from a slow recall response dwarfs the cost of prevention. Traceability is brand insurance.",
  },
];

const TOOL_ACCENTS = [
  "var(--re-decomposition)",
  "var(--re-linkage)",
  "var(--re-discovery)",
  "var(--re-evidence)",
  "var(--re-decomposition)",
  "var(--re-discovery)",
];

const FREE_TOOLS = [
  {
    title: "FTL Coverage Checker",
    desc: "Enter a product. Find out if it's on the FDA Food Traceability List in seconds.",
    href: "/tools/ftl-checker",
    icon: Leaf,
    tag: null,
  },
  {
    title: "Retailer Readiness Assessment",
    desc: "Could you pass a Walmart supplier audit today? Auto-scored in 3 minutes.",
    href: "/retailer-readiness",
    icon: ShieldCheck,
    tag: "Most popular",
  },
  {
    title: "FDA Recall Drill Simulator",
    desc: "Simulate an FDA 24-hour records request. See how fast you can respond.",
    href: "/tools/drill-simulator",
    icon: Thermometer,
    tag: null,
  },
  {
    title: "ROI Calculator",
    desc: "Input your company size. See the cost of non-compliance vs. RegEngine pricing.",
    href: "/tools/roi-calculator",
    icon: Calculator,
    tag: null,
  },
  {
    title: "FSMA 204 Plain-English Guide",
    desc: "The FDA rule, translated into language your team can actually use. No jargon.",
    href: "/fsma-204",
    icon: BookOpen,
    tag: null,
  },
  {
    title: "Live Data Sandbox",
    desc: "Paste your CSV. RegEngine checks the CTEs present, shows missing KDEs and lineage gaps, and keeps results ephemeral.",
    href: "#sandbox",
    icon: Database,
    tag: "Try now",
  },
];

const HOW_IT_WORKS = [
  {
    step: "01",
    title: "Connect your data",
    desc: "Upload CSVs, connect your ERP, or send records via API. RegEngine accepts any format.",
    icon: Database,
  },
  {
    step: "02",
    title: "RegEngine validates & normalizes",
    desc: "Every record is checked against FSMA 204 rules, mapped to EPCIS 2.0, and cryptographically verified.",
    icon: Shield,
  },
  {
    step: "03",
    title: "Package verified records",
    desc: "Generate an evidence package from authenticated records in minutes, with sandbox findings kept separate from production exports.",
    icon: FileText,
  },
];

const PRICING_PREVIEW = [
  {
    name: "Base",
    price: "$425",
    period: "/mo",
    desc: "1 facility, getting started",
    features: ["Up to 500 CTEs/month", "FTL checker", "Email support"],
  },
  {
    name: "Standard",
    price: "$549",
    period: "/mo",
    desc: "Multi-facility, growing operations",
    features: ["Unlimited CTEs", "API access", "Priority support"],
    highlighted: true,
  },
  {
    name: "Premium",
    price: "$639",
    period: "/mo",
    desc: "Enterprise-grade compliance",
    features: ["Unlimited CTEs", "Dedicated account manager", "Custom integrations"],
  },
];

function TraceabilityCommandCenter() {
  return (
    <div className="relative">
      <div className="absolute inset-0 translate-x-3 translate-y-3 rounded-2xl border border-white/10 bg-white/[0.03]" aria-hidden="true" />
      <div className="relative overflow-hidden rounded-2xl border border-white/15 bg-[#071019] shadow-[0_28px_90px_rgba(0,0,0,0.5)]">
        <div className="absolute inset-0 opacity-45 [background-image:linear-gradient(rgba(148,163,184,0.09)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.09)_1px,transparent_1px)] [background-size:44px_44px]" aria-hidden="true" />
        <div className="absolute inset-x-0 top-0 h-24 bg-[linear-gradient(90deg,rgba(16,185,129,0.22),rgba(59,130,246,0.14),rgba(168,85,247,0.18))]" aria-hidden="true" />

        <div className="relative">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-4 py-3 sm:px-5">
            <div className="flex items-center gap-3">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-emerald-300/25 bg-emerald-400/10">
                <Activity className="h-[18px] w-[18px] text-emerald-300" />
              </div>
              <div>
                <p className="font-mono text-[0.62rem] font-semibold uppercase tracking-[0.16em] text-emerald-300">
                  Live recall workspace
                </p>
                <p className="text-sm font-semibold text-white">Romaine Lot R-2026-0312</p>
              </div>
            </div>
            <div className="flex items-center gap-2 rounded-full border border-amber-300/30 bg-amber-300/10 px-3 py-1.5">
              <Clock className="h-3.5 w-3.5 text-amber-200" />
              <span className="font-mono text-[0.65rem] font-semibold uppercase tracking-[0.1em] text-amber-100">
                1h 40m response
              </span>
            </div>
          </div>

          <div className="grid gap-0 lg:grid-cols-[1.08fr_0.92fr]">
            <div className="border-b border-white/10 p-4 sm:p-5 lg:border-b-0 lg:border-r">
              <div className="mb-4 flex items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-medium text-slate-400">Chain of custody</p>
                  <p className="text-lg font-semibold text-white">4 critical events linked</p>
                </div>
                <div className="flex items-center gap-2 rounded-md border border-emerald-300/25 bg-emerald-300/10 px-2.5 py-1.5 text-emerald-200">
                  <Network className="h-3.5 w-3.5" />
                  <span className="font-mono text-[0.62rem] font-semibold uppercase tracking-[0.1em]">Verified</span>
                </div>
              </div>

              <div className="space-y-3">
                {COMMAND_TIMELINE.map((event, index) => {
                  const Icon = event.icon;

                  return (
                    <div key={event.stage} className="relative grid grid-cols-[2.25rem_1fr_auto] items-start gap-3 rounded-lg border border-white/10 bg-black/20 p-3">
                      {index < COMMAND_TIMELINE.length - 1 && (
                        <span className="absolute left-[1.7rem] top-10 h-7 w-px bg-white/15" aria-hidden="true" />
                      )}
                      <span
                        className="flex h-9 w-9 items-center justify-center rounded-lg border"
                        style={{
                          background: event.bg,
                          borderColor: `color-mix(in srgb, ${event.color} 35%, transparent)`,
                          color: event.color,
                        }}
                      >
                        <Icon className="h-[18px] w-[18px]" />
                      </span>
                      <span>
                        <span className="block text-sm font-semibold text-white">{event.stage}</span>
                        <span className="block text-xs text-slate-300">{event.facility}</span>
                        <span className="mt-1 block font-mono text-[0.62rem] uppercase tracking-[0.1em] text-slate-500">{event.detail}</span>
                      </span>
                      <span className="font-mono text-xs font-medium text-slate-400">{event.time}</span>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="p-4 sm:p-5">
              <div className="mb-4 rounded-lg border border-white/10 bg-white/[0.04] p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-medium text-slate-400">Retailer readiness</p>
                    <p className="text-2xl font-bold text-white">94%</p>
                  </div>
                  <ShieldCheck className="h-6 w-6 text-emerald-300" />
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-slate-800">
                  <div className="h-full w-[94%] rounded-full bg-[linear-gradient(90deg,var(--re-decomposition),var(--re-discovery),var(--re-linkage))]" />
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-center">
                  {["Walmart", "Kroger", "Costco"].map((retailer) => (
                    <span key={retailer} className="rounded-md border border-white/10 bg-black/20 px-2 py-1.5 text-[0.65rem] font-semibold text-slate-200">
                      {retailer}
                    </span>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2">
                {HERO_STATUS_CARDS.map((card) => (
                  <div key={card.label} className="rounded-lg border border-white/10 bg-black/25 p-3">
                    <p className="mb-1 text-[0.68rem] font-medium text-slate-400">{card.label}</p>
                    <p className="text-sm font-semibold text-white">{card.value}</p>
                    <span className="mt-2 block h-1 rounded-full" style={{ backgroundColor: card.color }} />
                  </div>
                ))}
              </div>

              <div className="mt-4 rounded-lg border border-emerald-300/25 bg-emerald-300/10 p-4">
                <div className="mb-2 flex items-center gap-2 text-emerald-100">
                  <PackageCheck className="h-4 w-4" />
                  <p className="text-sm font-semibold">Evidence package assembled</p>
                </div>
                <p className="text-xs leading-relaxed text-emerald-50/80">
                  EPCIS 2.0 export, PDF summary, chain integrity hash, and retailer audit packet are assembled from verified records.
                </p>
              </div>
            </div>
          </div>

          <div className="grid grid-cols-3 border-t border-white/10 bg-black/20">
            {["Ingest", "Normalize", "Export"].map((step, index) => (
              <div key={step} className="flex items-center justify-center gap-2 px-3 py-3 text-xs font-semibold text-slate-300">
                <span className={`h-2 w-2 rounded-full ${index === 0 ? "bg-blue-300" : index === 1 ? "bg-emerald-300" : "bg-amber-300"}`} />
                {step}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function OperationsBoard() {
  return (
    <div className="grid gap-6 lg:grid-cols-[0.85fr_1.15fr]">
      <div className="rounded-2xl border border-white/10 bg-[#071019] p-5 shadow-[0_18px_60px_rgba(0,0,0,0.28)]">
        <div className="mb-5 flex items-center justify-between gap-3">
          <div>
            <p className="font-mono text-[0.65rem] font-semibold uppercase tracking-[0.16em] text-[var(--re-brand)]">
              Operations board
            </p>
            <h3 className="mt-1 font-display text-2xl font-bold tracking-tight text-white">
              Recall drill, ready before the request lands.
            </h3>
          </div>
          <Route className="h-7 w-7 text-[var(--re-brand-light)]" />
        </div>

        <div className="space-y-3">
          {OPERATIONAL_STATS.map((stat, index) => (
            <div key={stat.label} className="rounded-lg border border-white/10 bg-white/[0.04] p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className={`font-display font-bold text-white ${stat.compact ? "text-xl" : "text-3xl"}`}>
                    {stat.value}
                  </p>
                  <p className="mt-1 text-xs leading-relaxed text-slate-400">{stat.label}</p>
                </div>
                <span
                  className="mt-1 h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: TOOL_ACCENTS[index] }}
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="grid gap-4">
        {OPERATIONS_LANES.map((lane) => {
          const Icon = lane.icon;

          return (
            <div key={lane.title} className="grid gap-4 rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] p-5 sm:grid-cols-[3rem_1fr_auto] sm:items-center">
              <div
                className="flex h-12 w-12 items-center justify-center rounded-lg border"
                style={{
                  borderColor: `color-mix(in srgb, ${lane.color} 28%, transparent)`,
                  backgroundColor: `color-mix(in srgb, ${lane.color} 10%, transparent)`,
                  color: lane.color,
                }}
              >
                <Icon className="h-5 w-5" />
              </div>
              <div>
                <p className="font-display text-lg font-semibold text-[var(--re-text-primary)]">{lane.title}</p>
                <p className="mt-1 text-sm leading-relaxed text-[var(--re-text-tertiary)]">{lane.desc}</p>
              </div>
              <p className="rounded-full border border-[var(--re-surface-border)] px-3 py-1.5 font-mono text-[0.62rem] font-semibold uppercase tracking-[0.12em] text-[var(--re-text-muted)] sm:text-right">
                {lane.status}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default function RegEngineLanding() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">

      {/* ── HERO ── */}
      <section className="relative isolate overflow-hidden border-b border-white/10 bg-[linear-gradient(135deg,#06100e_0%,#08111f_48%,#17131d_100%)]">
        <div className="absolute inset-0 opacity-35 [background-image:linear-gradient(rgba(148,163,184,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.08)_1px,transparent_1px)] [background-size:64px_64px]" aria-hidden="true" />
        <div className="absolute inset-y-0 right-0 w-full bg-[linear-gradient(115deg,transparent_0%,transparent_44%,rgba(16,185,129,0.18)_44%,rgba(59,130,246,0.12)_66%,rgba(168,85,247,0.16)_100%)]" aria-hidden="true" />

        <div className="relative max-w-[1280px] mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-10 sm:pb-14">
          <div className="grid grid-cols-1 lg:grid-cols-[0.9fr_1.1fr] gap-10 lg:gap-14 items-center">
          {/* Left — copy */}
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-emerald-300/25 bg-emerald-300/10 px-4 py-1.5 mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--re-brand)] animate-pulse" />
              <span className="font-mono text-xs font-medium text-emerald-200 tracking-wide">
                FSMA 204 Food Traceability Compliance
              </span>
            </div>

            <h1 className="font-display text-[clamp(2.4rem,5vw,4.25rem)] font-bold text-white leading-[1.02] tracking-tight mb-6">
              Supply chain traceability that protects your brand.
            </h1>

            <p className="text-lg text-slate-300 leading-relaxed mb-8 max-w-[560px]">
              Respond to recall requests in minutes, satisfy Walmart and Kroger supplier requirements,
              and build the visibility your brand depends on.
            </p>

            <div className="flex flex-col sm:flex-row sm:flex-wrap gap-3 mb-8">
              <Link
                href="/retailer-readiness"
                className="group relative inline-flex items-center justify-center gap-2 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-lg text-sm font-semibold transition-all duration-200 hover:bg-[var(--re-brand-dark)] hover:shadow-re-glow active:scale-[0.98] min-h-[48px]"
              >
                Start Your Workspace
                <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
              </Link>
              <Link
                href="/retailer-readiness"
                className="inline-flex items-center justify-center gap-2 border border-white/15 bg-white/[0.03] text-white px-7 py-3.5 rounded-lg text-sm font-medium transition-all duration-200 hover:border-[var(--re-brand)] hover:text-[var(--re-brand-light)] min-h-[48px]"
              >
                Check Your Readiness (Free)
              </Link>
              <Link
                href="/docs"
                className="inline-flex items-center justify-center gap-2 border border-white/15 bg-white/[0.03] text-white px-7 py-3.5 rounded-lg text-sm font-medium transition-all duration-200 hover:border-[var(--re-brand)] hover:text-[var(--re-brand-light)] min-h-[48px]"
              >
                <Code2 className="h-4 w-4" />
                View API Docs
              </Link>
            </div>

            <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap sm:items-center sm:gap-x-4 sm:gap-y-2">
              {TRUST_SIGNALS.map((signal) => (
                <span
                  key={signal}
                  className="inline-flex items-center gap-1.5 rounded-md border border-white/10 bg-black/20 px-2.5 py-2 text-xs text-slate-300 font-medium sm:border-0 sm:bg-transparent sm:px-0 sm:py-0"
                >
                  <CheckCircle2 className="h-3.5 w-3.5 text-[var(--re-brand)]" />
                  {signal}
                </span>
              ))}
            </div>
          </div>

          <TraceabilityCommandCenter />
          </div>

          <div className="mt-10 grid gap-3 border-t border-white/10 pt-5 sm:grid-cols-3">
            {[
              { icon: ScanLine, label: "Incoming request", value: "Supplier audit packet" },
              { icon: Boxes, label: "Lot graph", value: "12 CTEs connected" },
              { icon: Building2, label: "Retailer formats", value: "Walmart · Kroger · Costco" },
            ].map((item) => {
              const Icon = item.icon;

              return (
                <div key={item.label} className="flex items-center gap-3 rounded-lg border border-white/10 bg-black/20 p-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white/10 text-[var(--re-brand-light)]">
                    <Icon className="h-[18px] w-[18px]" />
                  </div>
                  <div>
                    <p className="font-mono text-[0.62rem] font-semibold uppercase tracking-[0.12em] text-slate-500">{item.label}</p>
                    <p className="text-sm font-semibold text-slate-100">{item.value}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── OPERATIONAL VALUE / BRAND PROTECTION ── */}
      <section className="border-y border-[var(--re-surface-border)] bg-[linear-gradient(180deg,var(--re-surface-card)_0%,var(--re-surface-elevated)_100%)]">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-14 sm:py-20">
          <div className="mb-10 max-w-[760px]">
            <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3">
              Operational value, not just compliance
            </p>
            <h2 className="font-display text-[clamp(1.75rem,4vw,2.75rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight">
              Traceability that pays for itself in the first recall drill.
            </h2>
            <p className="mt-4 max-w-[620px] text-[var(--re-text-secondary)] leading-relaxed">
              Keep the recall clock, lot movement, retailer readiness, and export evidence in one operating view
              before a buyer or regulator asks.
            </p>
          </div>

          <OperationsBoard />

          <div className="mt-6 grid grid-cols-1 md:grid-cols-3 gap-4">
            {BRAND_PROTECTION_CARDS.map((problem) => (
              <div key={problem.title} className="flex gap-3 rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-base)] p-4">
                <problem.icon className="h-5 w-5 text-[var(--re-brand)] shrink-0 mt-0.5" />
                <div>
                  <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">
                    {problem.title}
                  </h3>
                  <p className="text-xs text-[var(--re-text-tertiary)] leading-relaxed">
                    {problem.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── FREE TOOLS SHOWCASE ── */}
      <section className="max-w-[1200px] mx-auto px-4 sm:px-6 py-16 sm:py-24">
        <div className="grid gap-8 lg:grid-cols-[0.78fr_1.22fr] lg:items-start">
          <div>
            <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3">
              Free tools — no signup required
            </p>
            <h2 className="font-display text-[clamp(1.75rem,4vw,2.75rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-4">
              See your compliance gaps before you commit.
            </h2>
            <p className="text-[var(--re-text-secondary)] max-w-[500px] leading-relaxed">
              Use these tools now. No account needed. Understand your exposure, then decide.
            </p>

            <div className="mt-8 rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
              <div className="mb-4 flex items-center gap-3">
                <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-[var(--re-brand-muted)] text-[var(--re-brand)]">
                  <Zap className="h-5 w-5" />
                </div>
                <div>
                  <p className="font-display text-lg font-semibold text-[var(--re-text-primary)]">
                    Start with readiness
                  </p>
                  <p className="text-sm text-[var(--re-text-tertiary)]">
                    Auto-scored in 3 minutes.
                  </p>
                </div>
              </div>
              <Link
                href="/retailer-readiness"
                className="inline-flex w-full items-center justify-center gap-2 rounded-lg bg-[var(--re-brand)] px-5 py-3 text-sm font-semibold text-white transition-all duration-200 hover:bg-[var(--re-brand-dark)] hover:shadow-re-glow"
              >
                Run readiness assessment
                <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {FREE_TOOLS.map((tool, index) => {
              const Icon = tool.icon;
              const isFeatured = tool.title === "Retailer Readiness Assessment";
              const accent = TOOL_ACCENTS[index];

              return (
                <Link
                  key={tool.title}
                  href={tool.href}
                  className={`group relative flex min-h-[190px] flex-col overflow-hidden rounded-2xl border p-5 transition-all duration-200 hover:-translate-y-0.5 hover:shadow-re-glow ${
                    isFeatured
                      ? "sm:col-span-2 border-[var(--re-brand)]/45 bg-[linear-gradient(135deg,var(--re-brand-muted),var(--re-surface-card)_55%,rgba(59,130,246,0.08))]"
                      : "border-[var(--re-surface-border)] bg-[var(--re-surface-card)] hover:border-[var(--re-brand)]/50"
                  }`}
                >
                  <span className="absolute inset-x-0 top-0 h-1" style={{ backgroundColor: accent }} aria-hidden="true" />
                  <div className="flex items-start justify-between gap-3 mb-4">
                    <div
                      className="w-11 h-11 rounded-lg border flex items-center justify-center transition-colors duration-200"
                      style={{
                        borderColor: `color-mix(in srgb, ${accent} 22%, transparent)`,
                        backgroundColor: `color-mix(in srgb, ${accent} 9%, transparent)`,
                        color: accent,
                      }}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    {tool.tag && (
                      <span className="font-mono text-[0.6rem] font-semibold text-[var(--re-brand)] bg-[var(--re-brand-muted)] px-2 py-0.5 rounded">
                        {tool.tag}
                      </span>
                    )}
                  </div>
                  <h3 className="font-display text-[1.05rem] font-semibold text-[var(--re-text-primary)] mb-1.5">
                    {tool.title}
                  </h3>
                  <p className="text-sm text-[var(--re-text-tertiary)] leading-relaxed flex-1">
                    {tool.desc}
                  </p>
                  <span className="inline-flex items-center gap-1 text-xs font-semibold text-[var(--re-brand)] mt-4 group-hover:gap-2 transition-all duration-200">
                    Try it now <ArrowRight className="h-3 w-3" />
                  </span>
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ── */}
      <section className="border-y border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-16 sm:py-24">
          <div className="text-center mb-14">
            <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3">
              How it works
            </p>
            <h2 className="font-display text-[clamp(1.5rem,3.5vw,2.25rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight max-w-[600px] mx-auto">
              From messy data to verified evidence in three steps.
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            {HOW_IT_WORKS.map((step, i) => (
              <div key={step.step} className="relative">
                {/* Connector line */}
                {i < HOW_IT_WORKS.length - 1 && (
                  <div className="hidden md:block absolute top-8 left-[calc(100%)] w-full h-px border-t border-dashed border-[var(--re-border-default)]" aria-hidden="true" />
                )}
                <div className="flex flex-col items-center text-center">
                  <div className="w-16 h-16 rounded-2xl bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 flex items-center justify-center mb-5">
                    <step.icon className="h-7 w-7 text-[var(--re-brand)]" />
                  </div>
                  <span className="font-mono text-xs font-semibold text-[var(--re-brand)] mb-2">
                    Step {step.step}
                  </span>
                  <h3 className="font-display text-lg font-semibold text-[var(--re-text-primary)] mb-2">
                    {step.title}
                  </h3>
                  <p className="text-sm text-[var(--re-text-tertiary)] leading-relaxed max-w-[300px]">
                    {step.desc}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── DATA TRANSFORM DEMO ── */}
      <section className="max-w-[1200px] mx-auto px-4 sm:px-6 py-16 sm:py-24">
        <div className="mb-10">
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3">
            See what happens to bad data
          </p>
          <h2 className="font-display text-[clamp(1.5rem,3.5vw,2.25rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
            Messy CSV in. Defensible evidence package out.
          </h2>
          <p className="text-[var(--re-text-secondary)] max-w-[560px] leading-relaxed">
            Missing fields, duplicate lots, inconsistent supplier names — the kind of data you actually get. Watch RegEngine catch it all.
          </p>
        </div>
        <DataTransformDemo />
      </section>

      {/* ── LIVE SANDBOX ── */}
      <section id="sandbox" className="max-w-[1200px] mx-auto px-4 sm:px-6 pb-16 sm:pb-24">
        <div className="mb-10">
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3">
            Try it yourself — no signup required
          </p>
          <h2 className="font-display text-[clamp(1.5rem,3.5vw,2.25rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3 max-w-[640px]">
            Paste your data. See what breaks.
          </h2>
          <p className="text-[var(--re-text-secondary)] max-w-[560px] leading-relaxed">
            Drop your CSV and RegEngine checks the CTEs present, explains missing KDEs and lineage gaps, and shows the correction path in real time. Nothing is stored.
          </p>
        </div>
        <SandboxUpload />
      </section>

      {/* ── FOUNDER CREDIBILITY ── */}
      <section className="border-y border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-16 sm:py-20">
          <div className="max-w-[800px] mx-auto">
            <div className="flex items-start gap-5">
              <div className="w-14 h-14 rounded-full bg-[var(--re-brand-muted)] border-2 border-[var(--re-brand)]/30 flex items-center justify-center shrink-0">
                <span className="text-xl font-display font-bold text-[var(--re-brand)]">CS</span>
              </div>
              <div>
                <p className="text-lg text-[var(--re-text-primary)] leading-relaxed mb-4">
                  &ldquo;I built RegEngine because compliance shouldn&apos;t require a six-figure platform and a 12-month implementation.
                  I&apos;m Chris Sellers — AmeriCorps alum, former Senate staffer, and the founder.
                  I work directly with every company in our founding cohort. You&apos;ll get my cell phone number.&rdquo;
                </p>
                <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                  <span className="text-sm font-medium text-[var(--re-text-primary)]">
                    Christopher Sellers, Founder & CEO
                  </span>
                  <Link
                    href="/contact"
                    className="text-sm font-medium text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] transition-colors"
                  >
                    Book a free gap analysis →
                  </Link>
                </div>
              </div>
            </div>

            {/* Regulatory citations as trust signals */}
            <div className="mt-10 pt-8 border-t border-[var(--re-surface-border)]">
              <p className="font-mono text-[0.65rem] text-[var(--re-text-muted)] uppercase tracking-widest mb-4">
                Built on the regulation
              </p>
              <div className="flex flex-wrap gap-3">
                {[
                  "21 CFR § 1.1310",
                  "21 CFR § 1.1455",
                  "EPCIS 2.0",
                  "GS1 Standards",
                  "SHA-256 Verification",
                ].map((citation) => (
                  <span
                    key={citation}
                    className="font-mono text-xs text-[var(--re-text-tertiary)] border border-[var(--re-surface-border)] rounded-md px-3 py-1.5"
                  >
                    {citation}
                  </span>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ── PRICING PREVIEW ── */}
      <section className="max-w-[1200px] mx-auto px-4 sm:px-6 py-16 sm:py-24">
        <div className="text-center mb-12">
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3">
            Transparent pricing
          </p>
          <h2 className="font-display text-[clamp(1.5rem,3.5vw,2.25rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-3">
            Based on company size. No hidden fees.
          </h2>
          <p className="text-[var(--re-text-secondary)]">
            Founding partner rates, billed annually. Monthly billing available at checkout. Cancel anytime.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 max-w-[900px] mx-auto mb-8">
          {PRICING_PREVIEW.map((tier) => (
            <div
              key={tier.name}
              className={`rounded-xl p-6 border ${
                tier.highlighted
                  ? "border-[var(--re-brand)] bg-[var(--re-brand-muted)] shadow-re-glow"
                  : "border-[var(--re-surface-border)] bg-[var(--re-surface-card)]"
              }`}
            >
              {tier.highlighted && (
                <span className="inline-block font-mono text-[0.6rem] font-semibold text-[var(--re-brand)] bg-[var(--re-brand)]/10 border border-[var(--re-brand)]/20 px-2 py-0.5 rounded mb-3">
                  Most popular
                </span>
              )}
              <h3 className="font-display text-lg font-semibold text-[var(--re-text-primary)]">
                {tier.name}
              </h3>
              <p className="text-xs text-[var(--re-text-muted)] mb-3">{tier.desc}</p>
              <p className="mb-4">
                <span className="font-display text-3xl font-bold text-[var(--re-text-primary)]">
                  {tier.price}
                </span>
                <span className="text-sm text-[var(--re-text-muted)]">{tier.period}</span>
              </p>
              <ul className="space-y-2">
                {tier.features.map((feature) => (
                  <li key={feature} className="flex items-center gap-2 text-sm text-[var(--re-text-secondary)]">
                    <CheckCircle2 className="h-3.5 w-3.5 text-[var(--re-brand)] shrink-0" />
                    {feature}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>

        <div className="text-center">
          <Link
            href="/pricing"
            className="inline-flex items-center gap-2 text-sm font-medium text-[var(--re-brand)] hover:text-[var(--re-brand-dark)] transition-colors"
          >
            See full pricing details
            <ArrowRight className="h-4 w-4" />
          </Link>
        </div>
      </section>

      {/* ── FINAL CTA ── */}
      <section className="bg-[var(--re-surface-elevated)] border-t border-[var(--re-surface-border)]">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-16 sm:py-24 text-center">
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-4">
            FSMA 204 compliance deadline: July 20, 2028
          </p>
          <h2 className="font-display text-[clamp(1.75rem,4vw,2.75rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-4 max-w-[700px] mx-auto">
            Know exactly where every lot has been — before anyone asks.
          </h2>
          <p className="text-[var(--re-text-secondary)] max-w-[520px] mx-auto leading-relaxed mb-8">
            Protect your brand. Satisfy your retailers. Get your free readiness score in 3 minutes, including FSMA 204 compliance gaps.
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link
              href="/retailer-readiness"
              className="group relative inline-flex items-center justify-center gap-2 bg-[var(--re-brand)] text-white px-8 py-4 rounded-lg text-sm font-semibold transition-all duration-200 hover:bg-[var(--re-brand-dark)] hover:shadow-re-glow-strong active:scale-[0.98] min-h-[48px]"
            >
              Get My Free Readiness Score
              <ArrowRight className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-0.5" />
            </Link>
            <Link
              href="/pricing"
              className="inline-flex items-center justify-center gap-2 border border-[var(--re-border-default)] text-[var(--re-text-primary)] px-8 py-4 rounded-lg text-sm font-medium transition-all duration-200 hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] min-h-[48px]"
            >
              View Pricing
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
