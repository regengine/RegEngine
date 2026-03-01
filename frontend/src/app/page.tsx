'use client';

import { useState, useEffect } from "react";
import {
  Database,
  Hash,
  ShieldCheck,
  Settings,
  Activity,
  Search,
  ArrowRight,
  FileText,
  Truck,
  Zap,
  ChevronRight,
  Network,
  FileCheck
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";

/* ───────────────────────── INDUSTRY DATA ───────────────────────── */

const industries = [
  {
    name: "Food & Beverage",
    status: "live" as const,
    description: "FSMA 204 traceability, FDA Food Traceability List coverage, exemption analysis, and 24-hour recall response.",
    regulations: ["FSMA 204", "21 CFR Part 1 Subpart S", "FDA FTL"],
    link: "/ftl-checker",
    linkLabel: "Try FTL Checker →",
  },
  {
    name: "Energy",
    status: "coming-soon" as const,
    description: "NERC CIP compliance, FERC regulatory tracking, pipeline safety (49 CFR 192/195), and emissions reporting.",
    regulations: ["NERC CIP", "FERC", "EPA Clean Air Act"],
    link: "/verticals/energy",
    linkLabel: "Explore Energy →",
  },
  {
    name: "Nuclear",
    status: "coming-soon" as const,
    description: "NRC 10 CFR compliance, safety analysis reports, inspection readiness, and decommissioning requirements.",
    regulations: ["10 CFR 50", "NRC RG 1.174", "IAEA Safety Standards"],
    link: "/verticals/nuclear",
    linkLabel: "Explore Nuclear →",
  },
  {
    name: "Finance",
    status: "coming-soon" as const,
    description: "SEC reporting, SOX compliance, AML/KYC regulatory tracking, and cross-jurisdiction harmonization.",
    regulations: ["SOX", "Dodd-Frank", "EU DORA", "Basel III"],
    link: "/verticals/finance",
    linkLabel: "Explore Finance →",
  },
  {
    name: "Healthcare",
    status: "coming-soon" as const,
    description: "HIPAA compliance monitoring, FDA device regulations, CMS conditions of participation, and state licensure tracking.",
    regulations: ["HIPAA", "21 CFR 820", "CMS CoP", "HITECH"],
    link: "/verticals/healthcare",
    linkLabel: "Explore Healthcare →",
  },
  {
    name: "Manufacturing",
    status: "coming-soon" as const,
    description: "OSHA compliance, EPA environmental permits, ISO standard tracking, and supply chain due diligence.",
    regulations: ["OSHA 29 CFR 1910", "EPA RCRA", "ISO 9001/14001"],
    link: "/verticals/manufacturing",
    linkLabel: "Explore Manufacturing →",
  },
  {
    name: "Automotive",
    status: "coming-soon" as const,
    description: "NHTSA safety standards, EPA emissions compliance, IATF 16949, and EV battery regulations.",
    regulations: ["FMVSS", "EPA Tier 3", "EU Euro 7"],
    link: "/verticals/automotive",
    linkLabel: "Explore Automotive →",
  },
  {
    name: "Aerospace",
    status: "coming-soon" as const,
    description: "FAA airworthiness directives, ITAR/EAR export controls, AS9100 quality, and EASA harmonization.",
    regulations: ["FAR Part 21", "ITAR", "AS9100", "EASA CS"],
    link: "/verticals/aerospace",
    linkLabel: "Explore Aerospace →",
  },
  {
    name: "Construction",
    status: "coming-soon" as const,
    description: "OSHA construction standards, building code tracking, environmental permits, and prevailing wage compliance.",
    regulations: ["OSHA 29 CFR 1926", "IBC/IRC", "EPA Stormwater"],
    link: "/verticals/construction",
    linkLabel: "Explore Construction →",
  },
  {
    name: "Gaming",
    status: "coming-soon" as const,
    description: "State gaming commission regulations, AML compliance, responsible gaming requirements, and multi-jurisdiction licensing.",
    regulations: ["State Gaming Acts", "FinCEN", "NIGC MICS"],
    link: "/verticals/gaming",
    linkLabel: "Explore Gaming →",
  },
  {
    name: "Entertainment",
    status: "coming-soon" as const,
    description: "FCC broadcast compliance, content rating requirements, IP/licensing regulations, and labor law (SAG-AFTRA, IATSE).",
    regulations: ["FCC Rules", "COPPA", "DMCA", "State Film Incentives"],
    link: "/verticals/entertainment",
    linkLabel: "Explore Entertainment →",
  },
];

/* ───────────────────────── MAIN COMPONENT ───────────────────────── */

export default function RegEngineLanding() {
  const [animateIn, setAnimateIn] = useState(false);
  const [expandedIndustry, setExpandedIndustry] = useState<string | null>(null);
  const [waitlistEmail, setWaitlistEmail] = useState("");
  const [waitlistIndustry, setWaitlistIndustry] = useState<string | null>(null);
  const [waitlistSubmitted, setWaitlistSubmitted] = useState<Record<string, string>>({});

  useEffect(() => {
    setAnimateIn(true);
  }, []);

  const handleWaitlistSubmit = (industryName: string) => {
    if (waitlistEmail) {
      setWaitlistSubmitted((prev) => ({ ...prev, [industryName]: waitlistEmail }));
      setWaitlistEmail("");
      setWaitlistIndustry(null);
    }
  };

  return (
    <div className="re-page overflow-x-hidden">
      {/* ─── NOISE TEXTURE OVERLAY ─── */}
      <div className="re-noise" />

      {/* ─── HERO ─── */}
      <section className="relative z-[2] max-w-[1120px] mx-auto pt-[100px] pb-[80px] px-6">
        {/* Gradient glow */}
        <div className="absolute top-[-80px] left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-[radial-gradient(ellipse,rgba(16,185,129,0.06)_0%,transparent_70%)] pointer-events-none" />

        <div
          className={`transition-all duration-1000 ease-[cubic-bezier(0.16,1,0.3,1)] ${animateIn ? "opacity-100 translate-y-0" : "opacity-0 translate-y-5"
            }`}
        >
          {/* Regulatory badge */}
          <div className="re-badge-brand mb-7">
            <span className="re-dot bg-[var(--re-brand)] animate-pulse" />
            FSMA 204 Deadline: July 20, 2028
          </div>

          <h1 className="text-[clamp(36px,5vw,56px)] font-bold text-[var(--re-text-primary)] leading-[1.1] mb-5 max-w-[700px] tracking-[-0.02em]">
            FDA wants your
            <br />
            traceability data
            <br />
            <span className="text-[var(--re-brand)]">in 24 hours.</span>
            <a
              href="https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455#p-1.1455(c)"
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-[var(--re-text-muted)] hover:text-[var(--re-brand)] transition-colors align-super"
              title="21 CFR § 1.1455(c) Requirement"
            >
              [FDA]
            </a>
          </h1>

          <p className="text-lg text-[var(--re-text-muted)] leading-relaxed mb-10 max-w-[520px]">
            Most food companies can't deliver. RegEngine gives you API-first
            FSMA 204 compliance with cryptographic proof that your data is
            accurate — verifiable by anyone, including the FDA.
          </p>

          <div className="flex gap-3 flex-wrap">
            <Link href="/ftl-checker">
              <Button size="lg" className="h-16 px-10 rounded-3xl bg-[var(--re-brand)] text-white text-lg font-black italic uppercase shadow-[0_20px_40px_-10px_rgba(16,185,129,0.4)] group">
                Check Your Coverage <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
            <Link href="/retailer-readiness">
              <Button size="lg" variant="outline" className="h-16 px-10 rounded-3xl text-lg font-black italic uppercase border-2 group">
                Retailer Readiness →
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* ─── GS1 EPCIS ANNOUNCEMENT BANNER ─── */}
      <section className="relative z-[2] bg-gradient-to-r from-[rgba(16,185,129,0.08)] to-[rgba(59,130,246,0.08)] border-y border-[rgba(16,185,129,0.2)]">
        <div className="max-w-[1120px] mx-auto py-4 px-6 flex flex-wrap items-center justify-center gap-4">
          <div className="inline-flex items-center gap-2 px-3 py-1 bg-[rgba(16,185,129,0.15)] rounded text-[11px] font-bold text-[var(--re-brand)] tracking-widest uppercase">
            NEW
          </div>
          <span className="text-[var(--re-text-primary)] text-sm font-medium">
            Now supporting <strong className="text-[var(--re-brand)]">GS1 EPCIS 2.0</strong> for major retailer supplier automation
          </span>
          <Link href="/ftl-checker">
            <Button variant="ghost" size="sm" className="h-8 text-xs font-bold text-[var(--re-text-secondary)] hover:text-[var(--re-brand)]">
              Check Your Coverage →
            </Button>
          </Link>
        </div>
      </section>

      {/* ─── PROOF STRIP ─── */}
      <section className="relative z-[2] border-y border-white/[0.04] bg-white/[0.01]">
        <div className="max-w-[1120px] mx-auto px-6 grid grid-cols-2 md:grid-cols-4">
          {[
            { value: "23", label: "FDA categories", sublabel: "verified against FTL" },
            { value: "EPCIS 2.0", label: "GS1 Export", sublabel: "Retailer-ready" },
            { value: "SHA-256", label: "Audit trail", sublabel: "cryptographic hashing" },
            { value: "24hr", label: "FDA response", sublabel: "recall-ready export" },
          ].map((stat, i) => (
            <div
              key={i}
              className={`py-7 px-5 text-center transition-all duration-700 delay-[${300 + i * 100}ms] ${animateIn ? "opacity-100 translate-y-0" : "opacity-0 translate-y-[10px]"
                } ${i < 3 ? "md:border-r md:border-white/[0.04]" : ""}`}
            >
              <div className={`text-2xl font-bold text-[var(--re-brand)] mb-1 ${stat.value.includes("-") ? "re-mono" : ""}`}>
                {stat.value}
              </div>
              <div className="text-[13px] font-semibold text-[var(--re-text-primary)] mb-0.5">
                {stat.label}
              </div>
              <div className="text-[11px] text-[var(--re-text-disabled)] re-mono uppercase">
                {stat.sublabel}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ─── THE REGULATORY PROOF CHAIN ─── */}
      <section id="blueprint" className="relative z-[2] max-w-[1120px] mx-auto py-[120px] px-6">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-16 items-center">
          <div className="space-y-8">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] text-[10px] font-black uppercase tracking-[0.2em] border border-[var(--re-brand-muted)]">
              <Zap className="h-3 w-3" /> System Intelligence
            </div>
            <div className="space-y-4">
              <h2 className="text-4xl md:text-5xl re-heading-industrial">
                Compliance You Can <span className="text-[var(--re-brand)]">Verify</span> Yourself
              </h2>
              <p className="text-xl text-[var(--re-text-secondary)] font-bold leading-relaxed">
                We don't ask you to trust our database. We give you the math and let you check it.
                Every fact is hashed, versioned, and independently auditable.
              </p>
            </div>

            <div className="space-y-6">
              {[
                { title: 'Deterministic Extraction', desc: 'No LLM hallucinations. Just pure, hashed legal facts.' },
                { title: 'Immutable Lineage', desc: 'Every update creates a permanent, auditable version history.' },
                { title: 'Proof-of-Integrity', desc: 'Run your own scripts to verify our work in seconds.' }
              ].map((item, i) => (
                <div key={i} className="flex gap-4">
                  <div className="mt-1 h-5 w-5 rounded-full bg-[var(--re-brand)] flex items-center justify-center flex-shrink-0">
                    <ChevronRight className="h-3 w-3 text-white" />
                  </div>
                  <div>
                    <h4 className="font-black italic uppercase text-sm tracking-tight text-[var(--re-text-primary)]">{item.title}</h4>
                    <p className="text-sm text-[var(--re-text-tertiary)] font-medium">{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>

            <div className="pt-4">
              <Link href="/blueprint">
                <Button size="lg" className="h-16 px-10 rounded-3xl bg-black text-white dark:bg-white dark:text-black text-lg font-black italic uppercase shadow-xl hover:scale-105 transition-transform group">
                  Explore the Blueprint <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
                </Button>
              </Link>
            </div>
          </div>

          {/* Visual Preview */}
          <div className="relative group cursor-pointer" onClick={() => window.location.href = '/blueprint'}>
            <div className="absolute -inset-4 bg-gradient-to-r from-[var(--re-brand)] to-blue-500 rounded-[3rem] blur-2xl opacity-10 group-hover:opacity-20 transition duration-1000" />
            <div className="relative aspect-square rounded-[3rem] bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] p-8 overflow-hidden shadow-2xl flex items-center justify-center">
              <div className="absolute top-8 left-8 flex items-center gap-2">
                <div className="h-2 w-2 rounded-full bg-[var(--re-brand)] animate-ping" />
                <span className="text-[10px] font-black text-[var(--re-brand)] uppercase tracking-widest">Live Engine Visualization</span>
              </div>
              <Network className="h-40 w-40 text-[var(--re-brand)] opacity-20 group-hover:scale-110 transition-transform duration-700" />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="h-64 w-64 border border-[var(--re-brand)]/20 rounded-full animate-[spin_20s_linear_infinite]" />
                <div className="h-48 w-48 border-2 border-[var(--re-brand)]/10 rounded-full animate-[spin_15s_linear_infinite_reverse]" />
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ─── LIVE TOOLS ─── */}
      <section className="relative z-[2] bg-[rgba(16,185,129,0.03)] border-y border-[rgba(16,185,129,0.08)]">
        <div className="max-w-[1120px] mx-auto py-[60px] px-6">
          <div className="text-center mb-10">
            <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
              Live now — no signup required
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[
              {
                title: "FTL Coverage Checker",
                description: "Check if your products are on the FDA Food Traceability List. Includes all 23 categories with exclusion notes and CFR citations.",
                icon: <FileCheck size={20} />,
                href: "/tools/ftl-checker",
                cta: "Check Your Products →",
                badge: "Free",
              },
              {
                title: "Supply Chain Explorer",
                description: "Explore 3 real-world recall scenarios with 430 cryptographically verified traceability records across dairy, seafood, and produce supply chains.",
                icon: <Database size={20} />,
                href: "/tools/supply-chain-explorer",
                cta: "Explore Supply Chains →",
                badge: "New",
              },
              {
                title: "Retailer Readiness Assessment",
                description: "Interactive FSMA 204 compliance checklist. Self-assess your gaps and get a founder-led analysis of what needs fixing.",
                icon: <ShieldCheck size={20} />,
                href: "/tools/retailer-readiness",
                cta: "Assess Your Readiness →",
                badge: "Free",
              },
            ].map((tool, i) => (
              <Link
                key={i}
                href={tool.href}
                className="p-8 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl transition-all duration-300 flex flex-col hover:-translate-y-1 hover:border-[var(--re-brand-muted)] hover:shadow-[0_12px_24px_-10px_rgba(16,185,129,0.15)]"
              >
                <div className="flex justify-between items-start mb-5">
                  <div className="text-[var(--re-brand)]">{tool.icon}</div>
                  <div className="text-[10px] font-bold text-[var(--re-brand)] px-2 py-0.5 bg-[rgba(16,185,129,0.1)] rounded uppercase tracking-wider">
                    {tool.badge}
                  </div>
                </div>
                <h3 className="text-[17px] font-semibold text-[var(--re-text-primary)] mb-3">
                  {tool.title}
                </h3>
                <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mb-6 flex-grow">
                  {tool.description}
                </p>
                <div className="text-[13px] font-semibold text-[var(--re-brand)] flex items-center gap-1.5 transition-colors group-hover:text-[var(--re-brand-light)]">
                  {tool.cta}
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* ─── PLATFORM CAPABILITIES ─── */}
      <section id="product" className="relative z-[2] max-w-[1120px] mx-auto py-[80px] px-6">
        <div className="text-center mb-12">
          <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
            Compliance Command Center
          </span>
          <h2 className="text-[32px] font-bold text-[var(--re-text-primary)] mt-3 mb-3 tracking-[-0.01em]">
            Everything You Need to <span className="text-[var(--re-brand)]">Stay Compliant</span>
          </h2>
          <p className="text-base text-[var(--re-text-muted)] max-w-[520px] mx-auto">
            Real-time monitoring, automated alerts, supplier management, and audit-ready exports — all in one platform.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {[
            { title: 'Compliance Dashboard', desc: 'Real-time score with automated grading across CTEs, KDEs, and supply chain integrity.', href: '/dashboard/compliance', icon: <ShieldCheck size={20} /> },
            { title: 'Smart Alerts', desc: 'Configurable alerts for missing data, temperature excursions, and approaching deadlines.', href: '/dashboard/alerts', icon: <Activity size={20} /> },
            { title: 'Recall Readiness', desc: '6-dimension assessment scoring your ability to respond to FDA within 24 hours.', href: '/dashboard/recall-report', icon: <Truck size={20} /> },
            { title: 'Supplier Portal', desc: 'No-login CTE submission for suppliers. Track compliance across your entire network.', href: '/dashboard/suppliers', icon: <Network size={20} /> },
            { title: 'Product Catalog', desc: 'Manage FTL-covered products with CTE tracking, GTIN/SKU, and supplier mapping.', href: '/dashboard/products', icon: <Database size={20} /> },
            { title: 'Audit Trail', desc: 'Immutable, SHA-256 hashed event log for every action. Tamper-proof by design.', href: '/dashboard/audit-log', icon: <Hash size={20} /> },
          ].map((item, i) => (
            <Link
              key={i}
              href={item.href}
              className="p-6 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl transition-all duration-300 flex flex-col hover:-translate-y-1 hover:border-[var(--re-brand-muted)] hover:shadow-[0_12px_24px_-10px_rgba(16,185,129,0.15)]"
            >
              <div className="text-[var(--re-brand)] mb-4">{item.icon}</div>
              <h3 className="text-[15px] font-semibold text-[var(--re-text-primary)] mb-2">{item.title}</h3>
              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed flex-grow">{item.desc}</p>
            </Link>
          ))}
        </div>

        <div className="text-center mt-10">
          <Link href="/onboarding">
            <Button size="lg" className="h-14 px-10 rounded-3xl bg-gradient-to-r from-[var(--re-brand)] to-blue-500 text-white text-base font-bold shadow-xl hover:scale-105 transition-transform group">
              Get Started Free <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
            </Button>
          </Link>
        </div>
      </section>

      {/* ─── INDUSTRIES GRID ─── */}
      <section id="industries" className="relative z-[2] max-w-[1120px] mx-auto py-[100px] px-6">
        <div className="text-center mb-16">
          <h2 className="text-[32px] font-bold text-[var(--re-text-primary)] mb-4 tracking-[-0.01em]">
            Built for Industrial Certainty.
          </h2>
          <p className="text-base text-[var(--re-text-muted)] max-w-[560px] mx-auto leading-relaxed">
            Regulatory complexity doesn't scale with humans. It scale with graphs.
            Explore unified intelligence across 15+ complex verticals.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {industries.map((ind, i) => (
            <div
              key={i}
              onMouseEnter={() => setExpandedIndustry(ind.name)}
              onMouseLeave={() => setExpandedIndustry(null)}
              className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-6 transition-all duration-300 relative overflow-hidden"
            >
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-lg font-semibold text-[var(--re-text-primary)]">{ind.name}</h3>
                {ind.status === "live" ? (
                  <div className="text-[10px] font-bold text-[var(--re-brand)] px-2 py-0.5 bg-[rgba(16,185,129,0.1)] rounded-full uppercase">
                    Live
                  </div>
                ) : (
                  <div className="text-[10px] font-medium text-[var(--re-text-disabled)] px-2 py-0.5 bg-white/[0.03] rounded-full uppercase">
                    Soon
                  </div>
                )}
              </div>

              <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mb-5">
                {ind.description}
              </p>

              <div className="flex flex-wrap gap-1.5 mb-6">
                {ind.regulations.map((reg, ri) => (
                  <span
                    key={ri}
                    className="text-[10px] re-mono text-[var(--re-text-disabled)] px-1.5 py-0.5 bg-white/[0.02] border border-white/[0.04] rounded"
                  >
                    {reg}
                  </span>
                ))}
              </div>

              {ind.status === "live" ? (
                <Link
                  href={ind.link}
                  className="text-sm font-semibold text-[var(--re-brand)] flex items-center gap-1.5 hover:text-[var(--re-brand-light)] transition-colors"
                >
                  {ind.linkLabel}
                </Link>
              ) : waitlistSubmitted[ind.name] ? (
                <div className="text-sm text-[var(--re-brand)] font-medium flex items-center gap-2">
                  Joined waitlist for {ind.name}
                </div>
              ) : (
                <div className="flex gap-2">
                  <input
                    type="email"
                    placeholder="your@email.com"
                    value={waitlistIndustry === ind.name ? waitlistEmail : ""}
                    onChange={(e) => {
                      setWaitlistIndustry(ind.name);
                      setWaitlistEmail(e.target.value);
                    }}
                    className="flex-1 bg-white/[0.02] border border-white/[0.08] rounded-md px-3 py-2 text-[13px] text-[var(--re-text-primary)] outline-none focus:border-[var(--re-brand-muted)] transition-colors"
                  />
                  <button
                    onClick={() => handleWaitlistSubmit(ind.name)}
                    className="bg-[var(--re-text-primary)] text-[var(--re-surface-base)] border-none rounded-md px-3 py-2 text-xs font-semibold cursor-pointer hover:opacity-90 transition-opacity"
                  >
                    Join
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </section>

    </div>
  );
}
