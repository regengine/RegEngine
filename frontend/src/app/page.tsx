import Link from "next/link";
import {
  AlertTriangle,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  FlaskConical,
  Gauge,
  Layers,
  ShieldCheck,
  Siren,
  Truck,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";

const PERSONAS = [
  {
    title: "Food Safety and QA Directors",
    pain: "You own FDA readiness, but traceability data is split across spreadsheets, emails, and supplier portals that do not connect.",
    outcome: "Get unified traceability records across your supply chain, audit-ready in minutes.",
    icon: ShieldCheck,
  },
  {
    title: "Mid-Market Supplier Ops Leads",
    pain: "Walmart, Kroger, and Costco expect supplier-level FSMA 204 readiness now, not in 2028.",
    outcome: "Produce retailer-ready EPCIS 2.0 exports without custom integration projects.",
    icon: Truck,
  },
  {
    title: "Compliance Officers",
    pain: "If the FDA requested traceability records tomorrow, most teams would miss the 24-hour window.",
    outcome: "Generate recall-ready records fast with versioned, hashed, independently verifiable data.",
    icon: ClipboardCheck,
  },
];

const HOW_IT_WORKS = [
  {
    title: "Connect Your Supply Chain",
    description:
      "Ingest traceability data by API, CSV, or supplier portal. RegEngine normalizes everything to EPCIS 2.0.",
    icon: Layers,
  },
  {
    title: "Monitor Compliance in Real Time",
    description:
      "Track CTE and KDE coverage, flag gaps, and score recall readiness across FTL-covered products.",
    icon: Gauge,
  },
  {
    title: "Export When It Matters",
    description:
      "For FDA requests or retailer audits, export recall-ready records in minutes, not days.",
    icon: FileSearch,
  },
];

const FREE_TOOLS = [
  {
    title: "FTL Coverage Checker",
    subtitle: "Are your products on the FDA Food Traceability List?",
    href: "/tools/ftl-checker",
    icon: CheckCircle2,
  },
  {
    title: "Retailer Readiness Assessment",
    subtitle: "Could you pass a Walmart supplier audit today?",
    href: "/retailer-readiness",
    icon: ClipboardCheck,
  },
  {
    title: "Supply Chain Explorer",
    subtitle: "See how traceability works across real recall scenarios.",
    href: "/demo/supply-chains",
    icon: Database,
  },
  {
    title: "Anomaly Simulator",
    subtitle: "Test your cold-chain monitoring against real failure patterns.",
    href: "/tools/drill-simulator",
    icon: FlaskConical,
  },
];

const COMMAND_CENTER_FEATURES = [
  {
    title: "Compliance Dashboard",
    description:
      "See exactly where you stand with real-time scoring across every product, supplier, and traceability event.",
    icon: Gauge,
    href: "/dashboard/compliance",
  },
  {
    title: "Smart Alerts",
    description:
      "Know before the FDA does with automated alerts for data gaps, cold-chain breaks, and deadline risk.",
    icon: AlertTriangle,
    href: "/dashboard/alerts",
  },
  {
    title: "Recall Readiness",
    description:
      "Six-dimension scoring shows where you would fail and what to fix before a real recall request.",
    icon: Siren,
    href: "/dashboard/recall-report",
  },
  {
    title: "Audit Trail",
    description:
      "Every record is versioned, hashed, and independently verifiable so your team can prove chain integrity on demand.",
    icon: BookOpen,
    href: "/verify",
  },
];

export default function RegEngineLanding() {
  return (
    <div className="re-page overflow-x-hidden">
      <div className="re-noise" />

      <section className="relative z-[2] max-w-[1120px] mx-auto pt-[96px] pb-[72px] px-6">
        <div className="absolute top-[-80px] left-1/2 -translate-x-1/2 w-[640px] h-[420px] bg-[radial-gradient(ellipse,rgba(16,185,129,0.08)_0%,transparent_72%)] pointer-events-none" />

        <div className="re-badge-brand mb-7">
          <span className="re-dot bg-[var(--re-brand)] animate-pulse" />
          RegEngine - FSMA 204 Compliance Infrastructure
        </div>

        <h1 className="text-[clamp(36px,5vw,56px)] font-bold text-[var(--re-text-primary)] leading-[1.08] mb-6 max-w-[860px] tracking-[-0.02em]">
          The FDA will require your traceability data in 24 hours.
          <br />
          Can you deliver?
        </h1>

        <p className="text-lg text-[var(--re-text-muted)] leading-relaxed mb-10 max-w-[760px]">
          RegEngine connects your suppliers, lots, and events into one auditable record - so when
          the FDA or Walmart asks, you respond in minutes, not days.
        </p>

        <div className="flex gap-3 flex-wrap">
          <Link href="/retailer-readiness">
            <Button size="lg" className="h-16 px-10 rounded-3xl bg-[var(--re-brand)] text-white text-lg font-black italic uppercase shadow-[0_20px_40px_-10px_rgba(16,185,129,0.4)] group">
              Retailer Readiness Assessment
              <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
            </Button>
          </Link>
          <Link href="/tools/ftl-checker">
            <Button size="lg" variant="outline" className="h-16 px-10 rounded-3xl text-lg font-black italic uppercase border-2 group">
              Check Your Coverage
              <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
            </Button>
          </Link>
        </div>
      </section>

      <section className="relative z-[2] border-y border-white/[0.04] bg-white/[0.01]">
        <div className="max-w-[1120px] mx-auto px-6 grid grid-cols-2 md:grid-cols-4">
          {[
            { value: "23", label: "FDA categories verified" },
            { value: "1 API call", label: "to generate FDA-ready records" },
            { value: "24hr", label: "Recall response window" },
            { value: "Verifiable", label: "Independent verification tooling included" },
          ].map((stat, idx) => (
            <div
              key={stat.label}
              className={`py-7 px-5 text-center ${idx < 3 ? "md:border-r md:border-white/[0.04]" : ""}`}
            >
              <div className="text-2xl font-bold text-[var(--re-brand)] mb-1">{stat.value}</div>
              <div className="text-[13px] font-semibold text-[var(--re-text-primary)]">{stat.label}</div>
            </div>
          ))}
        </div>
      </section>

      <section className="relative z-[2] max-w-[1120px] mx-auto py-[88px] px-6">
        <div className="text-center mb-10">
          <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
            Who Is This For?
          </span>
          <h2 className="text-[32px] font-bold text-[var(--re-text-primary)] mt-3">
            Built for teams that get the FDA call
          </h2>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {PERSONAS.map((persona) => {
            const Icon = persona.icon;
            return (
              <article
                key={persona.title}
                className="p-7 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl"
              >
                <div className="flex items-center gap-2 text-[var(--re-brand)] mb-4">
                  <Icon size={18} />
                  <span className="text-[11px] re-mono uppercase tracking-widest">Buyer Persona</span>
                </div>
                <h3 className="text-[18px] font-semibold text-[var(--re-text-primary)] mb-3">{persona.title}</h3>
                <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mb-4">{persona.pain}</p>
                <p className="text-sm text-[var(--re-text-primary)] font-medium leading-relaxed">{persona.outcome}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="relative z-[2] bg-[rgba(239,68,68,0.04)] border-y border-[rgba(239,68,68,0.16)]">
        <div className="max-w-[1120px] mx-auto py-[72px] px-6">
          <span className="text-[11px] re-mono font-medium text-red-500 tracking-widest uppercase">The Problem</span>
          <h2 className="text-[32px] font-bold text-[var(--re-text-primary)] mt-3 mb-4 max-w-[840px]">
            FSMA 204 requires traceability records within 24 hours of FDA request.
          </h2>
          <p className="text-base text-[var(--re-text-muted)] max-w-[860px] leading-relaxed">
            The deadline is July 20, 2028. Most teams still need 3 to 5 days because traceability data
            sits across suppliers, spreadsheets, and disconnected systems that were never built for
            regulatory export.
          </p>
        </div>
      </section>

      <section className="relative z-[2] max-w-[1120px] mx-auto py-[88px] px-6">
        <div className="text-center mb-10">
          <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
            How It Works
          </span>
          <h2 className="text-[32px] font-bold text-[var(--re-text-primary)] mt-3 mb-2">
            Three steps to recall-ready operations
          </h2>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {HOW_IT_WORKS.map((step, index) => {
            const Icon = step.icon;
            return (
              <article
                key={step.title}
                className="p-7 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl"
              >
                <div className="flex items-center justify-between mb-5">
                  <div className="h-9 w-9 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] flex items-center justify-center font-bold">
                    {index + 1}
                  </div>
                  <Icon size={18} className="text-[var(--re-brand)]" />
                </div>
                <h3 className="text-[18px] font-semibold text-[var(--re-text-primary)] mb-3">{step.title}</h3>
                <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{step.description}</p>
              </article>
            );
          })}
        </div>
      </section>

      <section className="relative z-[2] bg-[rgba(16,185,129,0.03)] border-y border-[rgba(16,185,129,0.08)]">
        <div className="max-w-[1120px] mx-auto py-[70px] px-6">
          <div className="text-center mb-10">
            <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
              Free Compliance Tools
            </span>
            <h2 className="text-[30px] font-bold text-[var(--re-text-primary)] mt-3 mb-3">
              No signup required
            </h2>
            <p className="text-base text-[var(--re-text-muted)] max-w-[760px] mx-auto leading-relaxed">
              Built by a food industry founder who knows the FSMA 204 deadline is real.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {FREE_TOOLS.map((tool) => {
              const Icon = tool.icon;
              return (
                <Link
                  key={tool.title}
                  href={tool.href}
                  className="p-6 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl transition-all duration-300 hover:-translate-y-1 hover:border-[var(--re-brand-muted)] hover:shadow-[0_12px_24px_-10px_rgba(16,185,129,0.15)]"
                >
                  <Icon size={18} className="text-[var(--re-brand)] mb-4" />
                  <h3 className="text-[16px] font-semibold text-[var(--re-text-primary)] mb-2">{tool.title}</h3>
                  <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{tool.subtitle}</p>
                </Link>
              );
            })}
          </div>
        </div>
      </section>

      <section className="relative z-[2] max-w-[1120px] mx-auto py-[88px] px-6">
        <div className="p-8 md:p-10 rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] text-[10px] font-black uppercase tracking-[0.18em] border border-[var(--re-brand-muted)]">
            Recall Simulation
          </span>
          <h2 className="text-[30px] font-bold text-[var(--re-text-primary)] mt-5 mb-3">What happens when the FDA calls?</h2>
          <p className="text-[var(--re-text-muted)] leading-relaxed max-w-[860px] mb-8">
            Scenario: E. coli O157:H7 detected in romaine lettuce. A regional distributor must trace
            affected lots from farm to shelf and respond inside the FDA window.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            <div className="p-6 rounded-xl border border-red-300/20 bg-red-500/5">
              <h3 className="text-lg font-semibold text-[var(--re-text-primary)] mb-4">Without RegEngine</h3>
              <ul className="space-y-2 text-sm text-[var(--re-text-muted)]">
                <li>Response time: 18 hours</li>
                <li>Data sources: 7 disconnected systems</li>
                <li>Data completeness: 62%</li>
                <li>Chain of custody: difficult to verify</li>
              </ul>
            </div>
            <div className="p-6 rounded-xl border border-[var(--re-brand-muted)] bg-[rgba(16,185,129,0.08)]">
              <h3 className="text-lg font-semibold text-[var(--re-text-primary)] mb-4">With RegEngine</h3>
              <ul className="space-y-2 text-sm text-[var(--re-text-primary)]">
                <li>Response time: 42 minutes (synthetic scenario)</li>
                <li>Data sources: 1 API call</li>
                <li>Data completeness: 98% (synthetic scenario)</li>
                <li>Chain of custody: cryptographically verifiable</li>
              </ul>
            </div>
          </div>

          <div className="p-5 rounded-xl bg-black text-white dark:bg-white dark:text-black flex flex-col md:flex-row items-start md:items-center justify-between gap-4 mb-6">
            <div>
              <p className="text-4xl font-bold">96%</p>
              <p className="text-sm opacity-80">Reduction in recall response time (synthetic scenario)</p>
            </div>
            <Link href="/demo/recall-simulation">
              <Button className="h-11 px-6 rounded-xl bg-[var(--re-brand)] text-white hover:opacity-95">
                Run This Simulation
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>

          <p className="text-xs text-[var(--re-text-disabled)]">
            Simulated scenario using synthetic supply chain data based on FSMA 204 requirements and common FDA recall response patterns.
          </p>
        </div>
      </section>

      <section className="relative z-[2] max-w-[1120px] mx-auto pb-[24px] px-6">
        <div className="p-7 rounded-2xl border border-[var(--re-surface-border)] bg-white/[0.01]">
          <h2 className="text-[24px] font-bold text-[var(--re-text-primary)] mb-3">Built by someone who knows food compliance</h2>
          <p className="text-sm text-[var(--re-text-muted)] leading-relaxed max-w-[880px]">
            Family restaurant kid. Organic farm hand. AmeriCorps volunteer. U.S. Senate staff. Startup closer.
            I built RegEngine because compliance shouldn&apos;t require a six-figure platform and a twelve-month implementation.
            Your traceability data should be verified, exportable, and ready before anyone asks for it.
          </p>
          <p className="text-sm text-[var(--re-text-secondary)] mt-4">
            Every Retailer Readiness Assessment is scored automatically against live FDA requirements and retailer-specific benchmarks. Results in minutes, not weeks.
            <Link href="/retailer-readiness" className="text-[var(--re-brand)] hover:underline ml-1">
              Run the assessment.
            </Link>
          </p>
        </div>
      </section>

      <section className="relative z-[2] max-w-[1120px] mx-auto pb-[90px] px-6" id="product">
        <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
          Compliance Command Center
        </span>
        <h2 className="sr-only">Compliance Command Center</h2>
        <p className="text-base text-[var(--re-text-muted)] leading-relaxed max-w-[880px] mt-4 mb-8">
          Every record in RegEngine is deterministic, versioned, and independently verifiable. No
          AI guessing. No black boxes.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {COMMAND_CENTER_FEATURES.map((feature) => {
            const Icon = feature.icon;
            return (
              <Link
                key={feature.title}
                href={feature.href}
                className="p-5 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl transition-all duration-300 hover:-translate-y-1 hover:border-[var(--re-brand-muted)]"
              >
                <Icon size={18} className="text-[var(--re-brand)] mb-3" />
                <h3 className="text-[15px] font-semibold text-[var(--re-text-primary)] mb-2">{feature.title}</h3>
                <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{feature.description}</p>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="relative z-[2] max-w-[1120px] mx-auto py-[88px] px-6">
        <div className="rounded-2xl p-9 md:p-12 bg-gradient-to-r from-[rgba(16,185,129,0.2)] to-[rgba(59,130,246,0.18)] border border-[var(--re-surface-border)]">
          <div className="flex items-start gap-4 mb-4">
            <Users size={20} className="text-[var(--re-brand)] mt-1" />
            <div>
              <h2 className="text-[28px] font-bold text-[var(--re-text-primary)] mb-2">Ready to close your FSMA 204 gap?</h2>
              <p className="text-[var(--re-text-secondary)] leading-relaxed">
                Start with a free assessment, then see exactly what it takes to move from reactive traceability to recall-ready infrastructure.
              </p>
              <p className="text-sm text-[var(--re-text-muted)] mt-3">
                Start with a free 14-day trial. <Link href="/pricing" className="font-semibold text-[var(--re-brand)] hover:underline">See all plans.</Link>
              </p>
            </div>
          </div>

          <div className="flex flex-wrap gap-3 mt-7">
            <Link href="/retailer-readiness">
              <Button size="lg" className="h-14 px-8 rounded-2xl bg-[var(--re-brand)] text-white font-bold uppercase">
                Retailer Readiness Assessment
              </Button>
            </Link>
            <Link href="/pricing">
              <Button size="lg" variant="outline" className="h-14 px-8 rounded-2xl font-bold uppercase border-2">
                View Pricing
              </Button>
            </Link>
          </div>
        </div>
      </section>
    </div>
  );
}
