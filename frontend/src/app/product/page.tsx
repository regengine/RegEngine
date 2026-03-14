import type { Metadata } from 'next';
import Link from "next/link";
import {
  AlertTriangle, ArrowRight, BadgeCheck, BookOpen, CheckCircle2,
  ClipboardCheck, Database, FileSearch, Gauge, Layers, ShieldCheck, Siren,
  Search, Map, ListChecks, Network, Timer, BarChart3,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

export const metadata: Metadata = {
    title: 'Product Tour | RegEngine',
    description: 'FSMA 204 compliance in one flow: scan a GS1 barcode, query traceability in plain language, export a verifiable FDA package in minutes.',
    openGraph: {
        title: 'Product Tour | RegEngine',
        description: 'FSMA 204 compliance in one flow: scan, query, export.',
        url: 'https://www.regengine.co/product',
        type: 'website',
    },
};

const PILLARS = [
  { title: "Scan → Ingest", description: "Scan a GS1 barcode. Auto-fill CTE fields. Ingested in one tap.", detail: "Supports GS1 Digital Link and GS1 AI 01/10/17/21 on mobile + desktop with offline-capable capture.", Icon: ClipboardCheck },
  { title: "Ask → Answer", description: "Type a question. Get traced results with evidence.", detail: "Natural language query interface with 6 intent types, confidence scoring, and no SQL required.", Icon: BookOpen },
  { title: "Export → Comply", description: "Generate a verifiable FDA package in one API call.", detail: "SHA-256 chain verification with CSV, manifest, and verification JSON to meet 24-hour recall response workflows.", Icon: FileSearch },
];

const FLOW_STEPS = [
  { title: "Connect", description: "API, CSV, EDI 856, and supplier portal ingestion paths.", Icon: Layers },
  { title: "Scan & Capture", description: "QR decode, mobile field capture, and CTE auto-fill.", Icon: ClipboardCheck },
  { title: "Monitor", description: "Compliance scoring, smart alerts, and knowledge graph views.", Icon: Gauge },
  { title: "Export", description: "FDA package, recall simulation outputs, and retailer audit exports.", Icon: FileSearch },
];

const FREE_TOOLS = [
  { title: "FTL Checker", description: "Verify Food Traceability List coverage by product category.", href: "/tools/ftl-checker", Icon: Search },
  { title: "CTE Mapper", description: "Map your supply-chain events to required FSMA CTE structure.", href: "/tools/cte-mapper", Icon: Map },
  { title: "KDE Checker", description: "Validate KDE completeness before audit or recall requests.", href: "/tools/kde-checker", Icon: ListChecks },
  { title: "Knowledge Graph", description: "Visualize lot lineage and traceability events in one view.", href: "/tools/knowledge-graph", Icon: Network },
  { title: "Recall Readiness", description: "Run simulation drills and score your 24-hour response posture.", href: "/tools/recall-readiness", Icon: Timer },
  { title: "Retailer Readiness", description: "Benchmark supplier readiness against retailer expectations.", href: "/retailer-readiness", Icon: BarChart3 },
];

const INTEGRATION_HITS = ["Multi-tenant RLS", "RBAC enforcement", "Tenant rate limiting", "Webhook ingestion", "EPCIS 2.0 exchange", "EDI 856 inbound", "Stripe billing"];

export default function ProductPage() {
    return (
        <div className="re-page">
            {/* Hero */}
            <section className="relative z-[2] max-w-[800px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-12 sm:pb-16 text-center">
                <Badge className="mb-5 bg-[var(--re-brand-muted)] text-[var(--re-brand)] border-[var(--re-brand)]/20">
                    Product Tour
                </Badge>
                <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold text-re-text-primary leading-tight mb-5">
                    FSMA 204 compliance<br />
                    <span className="text-re-brand">in three moves</span>
                </h1>
                <p className="text-lg text-re-text-muted max-w-xl mx-auto leading-relaxed mb-8">
                    Scan a barcode. Ask a question. Export a verifiable FDA package.
                    Built for food safety teams who need speed without sacrificing auditability.
                </p>
                <div className="flex gap-3 justify-center flex-wrap">
                    <Link href="/alpha">
                        <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold px-6 shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                            Join Alpha Program
                            <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                    <Link href="/tools/ftl-checker">
                        <Button variant="outline" className="border-[var(--re-surface-border)] text-re-text-secondary hover:border-[var(--re-brand)]/30 px-6">
                            Try Free Tools
                        </Button>
                    </Link>
                </div>
            </section>

            {/* Three Pillars */}
            <section className="relative z-[2] max-w-[1000px] mx-auto px-4 sm:px-6 pb-12 sm:pb-16">
                <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4 sm:gap-5">
                    {PILLARS.map((p) => (
                        <article
                            key={p.title}
                            className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6 flex flex-col"
                            style={{
                                borderTop: '3px solid var(--re-brand)',
                                boxShadow: '0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border)',
                            }}
                        >
                            <div className="flex items-center gap-3 mb-4">
                                <div className="p-2 rounded-lg bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20">
                                    <p.Icon className="w-5 h-5 text-[var(--re-brand)]" />
                                </div>
                                <h2 className="text-lg font-semibold text-re-text-primary">{p.title}</h2>
                            </div>
                            <p className="text-sm text-re-text-muted leading-relaxed mb-3">{p.description}</p>
                            <p className="text-xs text-re-text-disabled leading-relaxed mt-auto">{p.detail}</p>
                        </article>
                    ))}
                </div>
            </section>

            {/* How It Works Flow */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
                <div className="max-w-[800px] mx-auto py-16 px-6">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-3 text-center">How it works</h2>
                    <p className="text-sm text-re-text-muted text-center mb-10 max-w-md mx-auto">
                        Four stages from raw supply-chain data to FDA-ready compliance package.
                    </p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
                        {FLOW_STEPS.map((s, i) => (
                            <div
                                key={s.title}
                                className="rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] p-5 text-center"
                                style={{
                                    boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
                                }}
                            >
                                <div className="w-8 h-8 rounded-full bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 flex items-center justify-center mx-auto mb-3">
                                    <span className="text-xs font-bold text-[var(--re-brand)]">{i + 1}</span>
                                </div>
                                <h3 className="text-sm font-semibold text-re-text-primary mb-1">{s.title}</h3>
                                <p className="text-xs text-re-text-muted leading-relaxed">{s.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* What this flow depends on — callout box */}
            <section className="relative z-[2] max-w-[900px] mx-auto py-16 px-6">
                <div
                    className="rounded-2xl border-2 border-[var(--re-warning-bg)] p-5 sm:p-8"
                    style={{
                        background: 'var(--re-warning-bg)',
                        boxShadow: '0 4px 24px rgba(0,0,0,0.06)',
                    }}
                >
                    <div className="flex items-center gap-3 mb-4">
                        <div className="p-2 rounded-lg bg-amber-500/10 border border-amber-500/20">
                            <AlertTriangle className="w-5 h-5 text-amber-400" />
                        </div>
                        <h2 className="text-xl font-bold text-re-text-primary">What this flow still depends on</h2>
                    </div>
                    <p className="text-sm text-re-text-muted mb-6 max-w-xl">
                        RegEngine accelerates traceability evidence, but implementation still depends on clean upstream records, identity normalization, and customer-controlled archives.
                    </p>
                    <div className="grid md:grid-cols-2 gap-3">
                        {[
                            'Source-system data still has to be mapped into FSMA CTE and KDE structures.',
                            'Lot codes, GLNs, products, and facilities have to be normalized before lineage is trustworthy.',
                            'Missing KDEs and conflicting identities require review, not blind automation.',
                            'Hashing proves integrity after ingest, not the correctness of the upstream source record.',
                        ].map((item) => (
                            <div key={item} className="rounded-lg border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-4 text-sm text-re-text-muted flex items-start gap-3">
                                <CheckCircle2 className="w-4 h-4 text-amber-400 mt-0.5 flex-shrink-0" />
                                <span>{item}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Free Tools */}
            <section className="relative z-[2] max-w-[900px] mx-auto py-12 sm:py-16 px-4 sm:px-6">
                <div className="text-center mb-10">
                    <Badge className="mb-4 bg-[var(--re-brand-muted)] text-[var(--re-brand)] border-[var(--re-brand)]/20">
                        Free Tools
                    </Badge>
                    <h2 className="text-2xl font-bold text-re-text-primary mb-3">
                        18 free compliance tools. No login required.
                    </h2>
                    <p className="text-sm text-re-text-muted max-w-md mx-auto">
                        Start checking your FSMA 204 readiness before you buy anything.
                    </p>
                </div>
                <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-4">
                    {FREE_TOOLS.map((tool) => (
                        <Link
                            key={tool.title}
                            href={tool.href}
                            className="group rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5 hover:border-[var(--re-brand)]/30 transition-all hover:-translate-y-0.5"
                            style={{
                                boxShadow: '0 2px 12px rgba(0,0,0,0.06)',
                            }}
                        >
                            <div className="flex items-start gap-3">
                                <div className="w-9 h-9 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] flex items-center justify-center flex-shrink-0 group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] transition-colors duration-300">
                                    <tool.Icon className="h-4 w-4 text-[var(--re-brand)] group-hover:text-white transition-colors duration-300" />
                                </div>
                                <div>
                                    <h3 className="text-sm font-semibold text-re-text-primary mb-1 group-hover:text-[var(--re-brand)] transition-colors">
                                        {tool.title}
                                    </h3>
                                    <p className="text-xs text-re-text-muted leading-relaxed">{tool.description}</p>
                                </div>
                            </div>
                        </Link>
                    ))}
                </div>
            </section>

            {/* Infrastructure Badges */}
            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]">
                <div className="max-w-[800px] mx-auto py-16 px-6 text-center">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-3">Built for production</h2>
                    <p className="text-sm text-re-text-muted mb-8 max-w-md mx-auto">
                        Enterprise-grade infrastructure from day one.
                    </p>
                    <div className="flex flex-wrap justify-center gap-3">
                        {INTEGRATION_HITS.map((hit) => (
                            <span
                                key={hit}
                                className="text-xs font-mono px-3 py-1.5 rounded-full border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-re-text-disabled"
                                style={{
                                    boxShadow: '0 1px 4px rgba(0,0,0,0.04)',
                                }}
                            >
                                {hit}
                            </span>
                        ))}
                    </div>
                </div>
            </section>

            {/* Alpha Callout */}
            <section className="relative z-[2] max-w-[700px] mx-auto px-6 pb-8">
                <div
                    className="rounded-2xl border border-[var(--re-brand)]/20 p-8 text-center"
                    style={{
                        background: 'var(--re-brand-muted)',
                        boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
                    }}
                >
                    <Badge className="mb-4 bg-[var(--re-brand)]/10 text-[var(--re-brand)] border-[var(--re-brand)]/20">
                        Alpha Program
                    </Badge>
                    <h3 className="text-xl font-bold text-re-text-primary mb-2">Shape the product with us</h3>
                    <p className="text-sm text-re-text-muted max-w-md mx-auto mb-5">
                        Early access. Direct founder access. Influence the roadmap before GA.
                    </p>
                    <Link href="/alpha">
                        <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold px-6 shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                            Join Alpha Program
                            <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                </div>
            </section>

            {/* CTA */}
            <section className="relative z-[2] bg-[var(--re-brand-muted)] border-t border-[var(--re-surface-border)]">
                <div className="max-w-[600px] mx-auto py-12 px-6 text-center">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-2">Ready to explore the workflow?</h2>
                    <p className="text-sm text-re-text-muted mb-6">
                        Start with the free tools or join the alpha for full platform access.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/alpha">
                            <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold px-6 shadow-[0_4px_16px_var(--re-brand-muted)] hover:-translate-y-0.5 transition-all">
                                Join Alpha Program
                                <ArrowRight className="ml-2 w-4 h-4" />
                            </Button>
                        </Link>
                        <Link href="/trust">
                            <Button variant="outline" className="border-[var(--re-surface-border)] text-re-text-secondary hover:border-[var(--re-brand)]/30 px-6">
                                Review Trust Center
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
