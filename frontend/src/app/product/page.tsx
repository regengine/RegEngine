'use client';

import Link from "next/link";
import { motion } from "framer-motion";
import {
  AlertTriangle,
  ArrowRight,
  BadgeCheck,
  BookOpen,
  CheckCircle2,
  ClipboardCheck,
  Database,
  FileSearch,
  Gauge,
  Layers,
  ShieldCheck,
  Siren,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const fadeUp = {
  hidden: { opacity: 0, y: 18 },
  show: { opacity: 1, y: 0 },
};

const stagger = {
  hidden: { opacity: 0 },
  show: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
    },
  },
};

const PILLARS = [
  {
    title: "Scan -> Ingest",
    description:
      "Scan a GS1 barcode. Auto-fill CTE fields. Ingested in one tap.",
    detail:
      "Supports GS1 Digital Link and GS1 AI 01/10/17/21 on mobile + desktop with offline-capable capture.",
    icon: ClipboardCheck,
  },
  {
    title: "Ask -> Answer",
    description:
      "Type a question. Get traced results with evidence.",
    detail:
      "Natural language query interface with 6 intent types, confidence scoring, and no SQL required.",
    icon: BookOpen,
  },
  {
    title: "Export -> Comply",
    description:
      "Generate a verifiable FDA package in one API call.",
    detail:
      "SHA-256 chain verification with CSV, manifest, and verification JSON to meet 24-hour recall response workflows.",
    icon: FileSearch,
  },
];

const FLOW_STEPS = [
  {
    title: "Connect",
    description: "API, CSV, EDI 856, and supplier portal ingestion paths.",
    icon: Layers,
  },
  {
    title: "Scan & Capture",
    description: "QR decode, mobile field capture, and CTE auto-fill.",
    icon: ClipboardCheck,
  },
  {
    title: "Monitor",
    description: "Compliance scoring, smart alerts, and knowledge graph views.",
    icon: Gauge,
  },
  {
    title: "Export",
    description: "FDA package, recall simulation outputs, and retailer audit exports.",
    icon: FileSearch,
  },
];

const FREE_TOOLS = [
  {
    title: "FTL Checker",
    description: "Verify Food Traceability List coverage by product category.",
    href: "/tools/ftl-checker",
  },
  {
    title: "CTE Mapper",
    description: "Map your supply-chain events to required FSMA CTE structure.",
    href: "/tools/cte-mapper",
  },
  {
    title: "KDE Checker",
    description: "Validate KDE completeness before audit or recall requests.",
    href: "/tools/kde-checker",
  },
  {
    title: "Knowledge Graph",
    description: "Visualize lot lineage and traceability events in one view.",
    href: "/tools/knowledge-graph",
  },
  {
    title: "Recall Readiness",
    description: "Run simulation drills and score your 24-hour response posture.",
    href: "/tools/recall-readiness",
  },
  {
    title: "Retailer Readiness",
    description: "Benchmark supplier readiness against retailer expectations.",
    href: "/retailer-readiness",
  },
];

const INTEGRATION_HITS = [
  "Multi-tenant RLS",
  "RBAC enforcement",
  "Tenant rate limiting",
  "Webhook ingestion",
  "EPCIS 2.0 exchange",
  "EDI 856 inbound",
  "Stripe billing",
];

export default function ProductPage() {
  return (
    <div className="re-page overflow-x-hidden">
      <div className="re-noise" />

      <motion.section
        className="relative z-[2] max-w-[1120px] mx-auto pt-[104px] pb-[74px] px-6"
        variants={fadeUp}
        initial="hidden"
        animate="show"
        transition={{ duration: 0.45, ease: "easeOut" }}
      >
        <div className="absolute top-[-96px] left-1/2 -translate-x-1/2 w-[680px] h-[460px] bg-[radial-gradient(ellipse,rgba(16,185,129,0.09)_0%,transparent_72%)] pointer-events-none" />
        <div className="re-badge-brand mb-7">
          <span className="re-dot bg-[var(--re-brand)] animate-pulse" />
          Product Tour
        </div>

        <h1 className="text-[clamp(36px,5vw,58px)] font-bold text-[var(--re-text-primary)] leading-[1.07] tracking-[-0.02em] mb-5 max-w-[900px]">
          Traceability that works in 42 minutes, not 18 hours
        </h1>

        <p className="text-lg text-[var(--re-text-muted)] leading-relaxed max-w-[780px] mb-9">
          RegEngine is an FSMA 204 compliance engine that takes your team from scan to
          verified export in one flow: capture events, query traceability, and generate FDA-ready
          records fast.
        </p>

        <div className="flex gap-3 flex-wrap">
          <Link href="/signup" className="w-full sm:w-auto">
            <Button size="lg" className="w-full sm:w-auto h-14 px-8 rounded-2xl bg-[var(--re-brand)] text-white font-black italic uppercase group">
              Start Free Trial
              <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
            </Button>
          </Link>
          <Link href="/tools" className="w-full sm:w-auto">
            <Button size="lg" variant="outline" className="w-full sm:w-auto h-14 px-8 rounded-2xl font-black italic uppercase border-2 group">
              Try Free Tools
              <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
            </Button>
          </Link>
        </div>
      </motion.section>

      <motion.section
        className="relative z-[2] max-w-[1120px] mx-auto py-[78px] px-6"
        variants={stagger}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-80px" }}
      >
        <motion.div variants={fadeUp} className="text-center mb-10">
          <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
            Three-Pillar Workflow
          </span>
          <h2 className="text-[32px] font-bold text-[var(--re-text-primary)] mt-3">
            Built for the moments that decide compliance outcomes
          </h2>
        </motion.div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {PILLARS.map((pillar) => {
            const Icon = pillar.icon;
            return (
              <motion.article
                key={pillar.title}
                variants={fadeUp}
                whileHover={{ y: -5, scale: 1.01 }}
                transition={{ duration: 0.2 }}
                className="p-7 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl"
              >
                <div className="flex items-center justify-between mb-5">
                  <div className="h-10 w-10 rounded-2xl bg-[var(--re-brand-muted)] text-[var(--re-brand)] flex items-center justify-center">
                    <Icon size={19} />
                  </div>
                  <span className="h-1.5 w-10 rounded-full bg-[var(--re-brand-muted)]" />
                </div>
                <h3 className="text-[20px] font-semibold text-[var(--re-text-primary)] mb-3">{pillar.title}</h3>
                <p className="text-[15px] text-[var(--re-text-primary)] leading-relaxed mb-3">
                  {pillar.description}
                </p>
                <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                  {pillar.detail}
                </p>
              </motion.article>
            );
          })}
        </div>
      </motion.section>

      <motion.section
        className="relative z-[2] border-y border-white/[0.05] bg-white/[0.01]"
        variants={stagger}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-80px" }}
      >
        <div className="max-w-[1120px] mx-auto py-[74px] px-6">
          <motion.div variants={fadeUp} className="text-center mb-10">
            <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
              How It Works
            </span>
            <h2 className="text-[32px] font-bold text-[var(--re-text-primary)] mt-3">
              One flow from ingest to audit response
            </h2>
          </motion.div>

          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
            {FLOW_STEPS.map((step, idx) => {
              const Icon = step.icon;
              return (
                <motion.article
                  key={step.title}
                  variants={fadeUp}
                  className="p-6 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl"
                >
                  <div className="flex items-center justify-between mb-4">
                    <div className="h-9 w-9 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] flex items-center justify-center font-bold text-sm">
                      {idx + 1}
                    </div>
                    <Icon className="text-[var(--re-brand)]" size={18} />
                  </div>
                  <h3 className="text-[18px] font-semibold text-[var(--re-text-primary)] mb-2">{step.title}</h3>
                  <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{step.description}</p>
                </motion.article>
              );
            })}
          </div>
        </div>
      </motion.section>

      <motion.section
        className="relative z-[2] max-w-[1120px] mx-auto py-[82px] px-6"
        variants={stagger}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-80px" }}
      >
        <motion.div variants={fadeUp} className="p-8 md:p-10 rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] text-[10px] font-black uppercase tracking-[0.18em] border border-[var(--re-brand-muted)]">
            Live Comparison
          </span>
          <h2 className="text-[30px] font-bold text-[var(--re-text-primary)] mt-5 mb-3">
            E. coli romaine scenario: how fast can your team respond?
          </h2>
          <p className="text-[var(--re-text-muted)] leading-relaxed max-w-[860px] mb-8">
            Scenario: regional contamination flag, distributor must isolate lots, trace supplier chain,
            and deliver records in the FDA response window.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
            <div className="p-6 rounded-xl border border-red-300/20 bg-red-500/5">
              <h3 className="text-lg font-semibold text-[var(--re-text-primary)] mb-4">Without RegEngine</h3>
              <ul className="space-y-2 text-sm text-[var(--re-text-muted)]">
                <li>Response time: 18 hours</li>
                <li>Data sources: 7 systems</li>
                <li>Data completeness: 62%</li>
              </ul>
            </div>
            <div className="p-6 rounded-xl border border-[var(--re-brand-muted)] bg-[rgba(16,185,129,0.08)]">
              <h3 className="text-lg font-semibold text-[var(--re-text-primary)] mb-4">With RegEngine</h3>
              <ul className="space-y-2 text-sm text-[var(--re-text-primary)]">
                <li>Response time: 42 minutes</li>
                <li>Data sources: 1 API call</li>
                <li>Data completeness: 98%</li>
              </ul>
            </div>
          </div>

          <Link href="/tools/recall-readiness">
            <Button variant="outline" className="rounded-2xl border-2 font-black uppercase italic group">
              Run This Simulation
              <ArrowRight className="ml-2 h-4 w-4 group-hover:translate-x-1 transition-transform" />
            </Button>
          </Link>
        </motion.div>
      </motion.section>

      <motion.section
        className="relative z-[2] border-y border-[rgba(16,185,129,0.08)] bg-[rgba(16,185,129,0.03)]"
        variants={stagger}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-80px" }}
      >
        <div className="max-w-[1120px] mx-auto py-[74px] px-6">
          <motion.div variants={fadeUp} className="text-center mb-10">
            <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
              Free Tools
            </span>
            <h2 className="text-[30px] font-bold text-[var(--re-text-primary)] mt-3 mb-3">
              Explore without creating an account
            </h2>
            <Badge className="bg-[var(--re-brand-muted)] text-[var(--re-brand)] border border-[var(--re-brand-muted)]">
              Free - No Login Required
            </Badge>
          </motion.div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {FREE_TOOLS.map((tool) => (
              <motion.div key={tool.title} variants={fadeUp}>
                <Link
                  href={tool.href}
                  className="block p-6 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl transition-all duration-300 hover:-translate-y-1 hover:border-[var(--re-brand-muted)] hover:shadow-[0_12px_24px_-10px_rgba(16,185,129,0.15)]"
                >
                  <div className="flex items-center gap-2 mb-3 text-[var(--re-brand)]">
                    <CheckCircle2 size={16} />
                    <span className="text-[11px] re-mono uppercase tracking-widest">Tool</span>
                  </div>
                  <h3 className="text-[17px] font-semibold text-[var(--re-text-primary)] mb-2">{tool.title}</h3>
                  <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{tool.description}</p>
                </Link>
              </motion.div>
            ))}
          </div>
        </div>
      </motion.section>

      <motion.section
        className="relative z-[2] max-w-[1120px] mx-auto py-[84px] px-6"
        variants={stagger}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-80px" }}
      >
        <motion.div variants={fadeUp} className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          <article className="lg:col-span-3 p-7 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl">
            <div className="flex items-center gap-2 mb-4 text-[var(--re-brand)]">
              <Database size={16} />
              <span className="text-[11px] re-mono uppercase tracking-widest">Integrations</span>
            </div>
            <h3 className="text-[24px] font-semibold text-[var(--re-text-primary)] mb-3">Integration-ready for real operations</h3>
            <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mb-5">
              Designed for production ingestion and enterprise controls, without rebuilding your stack.
            </p>
            <div className="flex flex-wrap gap-2">
              {INTEGRATION_HITS.map((hit) => (
                <span
                  key={hit}
                  className="inline-flex items-center px-2.5 py-1 rounded-full text-[11px] font-semibold bg-white/[0.04] border border-white/[0.07] text-[var(--re-text-primary)]"
                >
                  {hit}
                </span>
              ))}
            </div>
          </article>

          <article className="lg:col-span-2 p-7 bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl">
            <div className="flex items-center gap-2 mb-4 text-[var(--re-brand)]">
              <ShieldCheck size={16} />
              <span className="text-[11px] re-mono uppercase tracking-widest">Trust</span>
            </div>
            <h3 className="text-[24px] font-semibold text-[var(--re-text-primary)] mb-4">Built for buyer diligence</h3>
            <ul className="space-y-3 text-sm text-[var(--re-text-muted)]">
              <li className="flex items-start gap-2"><BadgeCheck size={16} className="mt-0.5 text-[var(--re-brand)]" /> Multi-tenant isolation and least-privilege access patterns</li>
              <li className="flex items-start gap-2"><AlertTriangle size={16} className="mt-0.5 text-[var(--re-brand)]" /> Alerting and audit workflow tied to real traceability events</li>
              <li className="flex items-start gap-2"><Siren size={16} className="mt-0.5 text-[var(--re-brand)]" /> Recall drill exports and FDA package verification included</li>
            </ul>
          </article>
        </motion.div>
      </motion.section>

      <motion.section
        className="relative z-[2] max-w-[1120px] mx-auto pb-[98px] px-6"
        variants={fadeUp}
        initial="hidden"
        whileInView="show"
        viewport={{ once: true, margin: "-80px" }}
      >
        <div className="rounded-2xl border border-[var(--re-brand-muted)] bg-[linear-gradient(130deg,rgba(16,185,129,0.12),rgba(16,185,129,0.02)_60%)] p-8 md:p-10">
          <span className="text-[11px] re-mono font-medium text-[var(--re-brand)] tracking-widest uppercase">
            Ready To Move?
          </span>
          <h2 className="text-[32px] font-bold text-[var(--re-text-primary)] mt-3 mb-3">
            Ready to close your FSMA 204 gap?
          </h2>
          <p className="text-[var(--re-text-muted)] max-w-[760px] leading-relaxed mb-7">
            Start with free tools, run your first traceability workflow, and upgrade when you are
            ready to operationalize onboarding and export at scale.
          </p>
          <div className="flex flex-wrap gap-3">
            <Link href="/signup" className="w-full sm:w-auto">
              <Button size="lg" className="w-full sm:w-auto h-14 px-8 rounded-2xl bg-[var(--re-brand)] text-white font-black italic uppercase group">
                Start Free Trial
                <ArrowRight className="ml-2 h-5 w-5 group-hover:translate-x-1 transition-transform" />
              </Button>
            </Link>
            <Link href="/pricing" className="w-full sm:w-auto">
              <Button size="lg" variant="outline" className="w-full sm:w-auto h-14 px-8 rounded-2xl font-black italic uppercase border-2">
                View Pricing
              </Button>
            </Link>
          </div>
        </div>
      </motion.section>
    </div>
  );
}
