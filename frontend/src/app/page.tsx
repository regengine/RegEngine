import Link from "next/link";
import type { Metadata } from "next";
import {
  ArrowRight,
  Leaf,
  ShieldCheck,
  BookOpen,
  Thermometer,
  Calculator,
  CheckCircle2,
  AlertTriangle,
  Clock,
  FileText,
  Database,
  Shield,
  Zap,
  Code2,
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
  "First FDA-ready export in 48 hours",
  "1hr 40min recall response",
  "API-first",
  "Built for FSMA 204",
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
    desc: "Paste your CSV. RegEngine evaluates it against FSMA 204 traceability requirements across all 7 CTE types. Nothing stored.",
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
    title: "Export FDA-ready records",
    desc: "Generate a complete audit package in minutes — not weeks. Ready for FDA, Walmart, or any retailer.",
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

/* ------------------------------------------------------------------ */
/*  PAGE                                                               */
/* ------------------------------------------------------------------ */

export default function RegEngineLanding() {
  return (
    <div className="overflow-x-hidden bg-[var(--re-surface-base)]">

      {/* ── HERO ── */}
      <section className="relative max-w-[1200px] mx-auto px-4 sm:px-6 pt-16 sm:pt-24 pb-12 sm:pb-16">
        {/* Subtle gradient background */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[600px] bg-[var(--re-brand)] opacity-[0.03] rounded-full blur-[120px]" />
        </div>

        <div className="relative grid grid-cols-1 lg:grid-cols-2 gap-10 lg:gap-16 items-center">
          {/* Left — copy */}
          <div>
            <div className="inline-flex items-center gap-2 bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 rounded-full px-4 py-1.5 mb-6">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--re-brand)] animate-pulse" />
              <span className="font-mono text-xs font-medium text-[var(--re-brand)] tracking-wide">
                FSMA 204 Food Traceability Compliance
              </span>
            </div>

            <h1 className="font-display text-[clamp(2rem,5vw,3.25rem)] font-bold text-[var(--re-text-primary)] leading-[1.1] tracking-tight mb-6">
              Supply chain traceability that protects your brand.
            </h1>

            <p className="text-lg text-[var(--re-text-secondary)] leading-relaxed mb-8 max-w-[520px]">
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
                className="inline-flex items-center justify-center gap-2 border border-[var(--re-border-default)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-lg text-sm font-medium transition-all duration-200 hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] min-h-[48px]"
              >
                Check Your Readiness (Free)
              </Link>
              <Link
                href="/docs"
                className="inline-flex items-center justify-center gap-2 border border-[var(--re-border-default)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-lg text-sm font-medium transition-all duration-200 hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] min-h-[48px]"
              >
                <Code2 className="h-4 w-4" />
                View API Docs
              </Link>
            </div>

            {/* Trust bar */}
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
              {TRUST_SIGNALS.map((signal) => (
                <span
                  key={signal}
                  className="inline-flex items-center gap-1.5 text-xs text-[var(--re-text-muted)] font-medium"
                >
                  <CheckCircle2 className="h-3.5 w-3.5 text-[var(--re-brand)]" />
                  {signal}
                </span>
              ))}
            </div>
          </div>

          {/* Right — Audit response demo card */}
          <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl overflow-hidden shadow-re-lg">
            <div className="px-5 py-3 border-b border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center gap-3">
              <span className="w-2 h-2 rounded-full bg-[var(--re-warning)]" />
              <span className="font-mono text-[0.65rem] font-medium text-[var(--re-text-muted)] tracking-wide uppercase">
                Incoming: Supplier Audit Request
              </span>
            </div>
            <div className="p-5">
              <p className="font-serif text-[1rem] font-medium text-[var(--re-text-primary)] leading-snug mb-5">
                &ldquo;Provide complete chain of custody for{" "}
                <span className="text-[var(--re-brand)]">
                  Romaine Lettuce Lot&nbsp;R&#8209;2026&#8209;0312
                </span>{" "}
                from farm to distribution center. Due by end of business Friday.&rdquo;
              </p>
              <div className="border-t border-[var(--re-surface-border)] pt-4">
                <p className="font-mono text-[0.65rem] font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3">
                  RegEngine Response — 3 minutes later
                </p>
                <div className="space-y-2.5">
                  {[
                    { label: "CTEs found", value: "12 of 12", badge: "Complete", color: "emerald" },
                    { label: "Coverage", value: "100%", badge: "Verified", color: "emerald" },
                    { label: "Format", value: "EPCIS 2.0 + PDF", badge: "FDA-ready", color: "blue" },
                    { label: "Chain integrity", value: "SHA-256", badge: "Verified", color: "emerald" },
                  ].map((row) => (
                    <div key={row.label} className="flex items-center justify-between gap-2">
                      <span className="text-xs text-[var(--re-text-secondary)]">{row.label}</span>
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-xs font-medium text-[var(--re-text-primary)]">
                          {row.value}
                        </span>
                        <span className={`text-[0.6rem] font-semibold px-1.5 py-0.5 rounded-full border ${
                          row.color === "blue"
                            ? "bg-blue-500/10 text-blue-400 border-blue-500/20"
                            : "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
                        }`}>
                          {row.badge}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="px-5 py-3 border-t border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] flex items-center justify-between">
              <span className="text-xs text-[var(--re-text-muted)]">
                Audit package assembled and export-ready
              </span>
              <Zap className="h-4 w-4 text-[var(--re-brand)]" />
            </div>
          </div>
        </div>
      </section>

      {/* ── OPERATIONAL VALUE / BRAND PROTECTION ── */}
      <section className="border-y border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
        <div className="max-w-[1200px] mx-auto px-4 sm:px-6 py-12 sm:py-16">
          <div className="text-center mb-10">
            <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3">
              Operational value, not just compliance
            </p>
            <h2 className="font-display text-[clamp(1.5rem,3.5vw,2.25rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight max-w-[700px] mx-auto">
              Traceability that pays for itself in the first recall drill.
            </h2>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-10">
            {OPERATIONAL_STATS.map((stat) => (
              <div
                key={stat.label}
                className="text-center p-6 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-base)]"
              >
                <p className={`font-display font-bold text-[var(--re-brand)] mb-2 ${
                  stat.compact ? "text-xl sm:text-2xl" : "text-2xl sm:text-3xl"
                }`}>
                  {stat.value}
                </p>
                <p className="text-sm text-[var(--re-text-secondary)] leading-relaxed">
                  {stat.label}
                </p>
              </div>
            ))}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {BRAND_PROTECTION_CARDS.map((problem) => (
              <div key={problem.title} className="flex gap-3 p-4 rounded-lg">
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
        <div className="text-center mb-12">
          <p className="font-mono text-xs font-medium text-[var(--re-brand)] uppercase tracking-widest mb-3">
            Free tools — no signup required
          </p>
          <h2 className="font-display text-[clamp(1.5rem,3.5vw,2.25rem)] font-bold text-[var(--re-text-primary)] tracking-tight leading-tight mb-4 max-w-[600px] mx-auto">
            See your compliance gaps before you commit.
          </h2>
          <p className="text-[var(--re-text-secondary)] max-w-[480px] mx-auto">
            Use these tools now. No account needed. Understand your exposure, then decide.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {FREE_TOOLS.map((tool) => (
            <Link
              key={tool.title}
              href={tool.href}
              className="group flex flex-col p-5 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl transition-all duration-200 hover:border-[var(--re-brand)]/50 hover:shadow-re-glow hover:-translate-y-0.5"
            >
              <div className="flex items-center gap-3 mb-3">
                <div className="w-10 h-10 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] flex items-center justify-center group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] transition-colors duration-200">
                  <tool.icon className="h-5 w-5 text-[var(--re-brand)] group-hover:text-white transition-colors duration-200" />
                </div>
                {tool.tag && (
                  <span className="font-mono text-[0.6rem] font-semibold text-[var(--re-brand)] bg-[var(--re-brand-muted)] px-2 py-0.5 rounded">
                    {tool.tag}
                  </span>
                )}
              </div>
              <h3 className="font-display text-[0.95rem] font-semibold text-[var(--re-text-primary)] mb-1.5">
                {tool.title}
              </h3>
              <p className="text-sm text-[var(--re-text-tertiary)] leading-relaxed flex-1">
                {tool.desc}
              </p>
              <span className="inline-flex items-center gap-1 text-xs font-medium text-[var(--re-brand)] mt-3 group-hover:gap-2 transition-all duration-200">
                Try it now <ArrowRight className="h-3 w-3" />
              </span>
            </Link>
          ))}
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
              From messy data to FDA&#8209;ready in three steps.
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
            Messy CSV in. Defensible FDA package out.
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
            Drop your CSV and RegEngine evaluates it against FSMA 204 traceability requirements across all 7 CTE types in real time. Nothing is stored.
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
