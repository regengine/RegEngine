import type { Metadata } from 'next';
import Link from "next/link";
import {
  AlertTriangle, ArrowRight, BadgeCheck, BookOpen, CheckCircle2,
  ClipboardCheck, Database, FileSearch, Gauge, Layers, ShieldCheck, Siren,
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
  { title: "Scan \u2192 Ingest", description: "Scan a GS1 barcode. Auto-fill CTE fields. Ingested in one tap.", detail: "Supports GS1 Digital Link and GS1 AI 01/10/17/21 on mobile + desktop with offline-capable capture.", Icon: ClipboardCheck },
  { title: "Ask \u2192 Answer", description: "Type a question. Get traced results with evidence.", detail: "Natural language query interface with 6 intent types, confidence scoring, and no SQL required.", Icon: BookOpen },
  { title: "Export \u2192 Comply", description: "Generate a verifiable FDA package in one API call.", detail: "SHA-256 chain verification with CSV, manifest, and verification JSON to meet 24-hour recall response workflows.", Icon: FileSearch },
];

const FLOW_STEPS = [
  { title: "Connect", description: "API, CSV, EDI 856, and supplier portal ingestion paths.", Icon: Layers },
  { title: "Scan & Capture", description: "QR decode, mobile field capture, and CTE auto-fill.", Icon: ClipboardCheck },
  { title: "Monitor", description: "Compliance scoring, smart alerts, and knowledge graph views.", Icon: Gauge },
  { title: "Export", description: "FDA package, recall simulation outputs, and retailer audit exports.", Icon: FileSearch },
];

const FREE_TOOLS = [
  { title: "FTL Checker", description: "Verify Food Traceability List coverage by product category.", href: "/tools/ftl-checker" },
  { title: "CTE Mapper", description: "Map your supply-chain events to required FSMA CTE structure.", href: "/tools/cte-mapper" },
  { title: "KDE Checker", description: "Validate KDE completeness before audit or recall requests.", href: "/tools/kde-checker" },
  { title: "Knowledge Graph", description: "Visualize lot lineage and traceability events in one view.", href: "/tools/knowledge-graph" },
  { title: "Recall Readiness", description: "Run simulation drills and score your 24-hour response posture.", href: "/tools/recall-readiness" },
  { title: "Retailer Readiness", description: "Benchmark supplier readiness against retailer expectations.", href: "/retailer-readiness" },
];

const INTEGRATION_HITS = ["Multi-tenant RLS", "RBAC enforcement", "Tenant rate limiting", "Webhook ingestion", "EPCIS 2.0 exchange", "EDI 856 inbound", "Stripe billing"];

export default function ProductPage() {
    return (
        <div className="re-page">
            {/* Hero */}
            <section className="relative z-[2] max-w-[800px] mx-auto pt-20 px-6 pb-16 text-center">
                <Badge className="mb-5 bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
                    Product Tour
                </Badge>
                <h1 className="text-4xl md:text-5xl font-bold text-re-text-primary leading-tight mb-5">
                    FSMA 204 compliance<br />
                    <span className="text-re-brand">in three moves</span>
                </h1>
                <p className="text-lg text-re-text-muted max-w-xl mx-auto leading-relaxed">
                    Scan a barcode. Ask a question. Export a verifiable FDA package.
                    Built for food safety teams who need speed without sacrificing auditability.
                </p>
            </section>

            {/* Three Pillars */}
            <section className="relative z-[2] max-w-[1000px] mx-auto px-6 pb-16">
                <div className="grid md:grid-cols-3 gap-5">
                    {PILLARS.map((p) => (
                        <article
                            key={p.title}
                            className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-6 flex flex-col"
                        >
                            <div className="flex items-center gap-3 mb-4">
                                <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                                    <p.Icon className="w-5 h-5 text-emerald-400" />
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
            <section className="relative z-[2] border-t border-white/[0.06] bg-white/[0.01]">
                <div className="max-w-[800px] mx-auto py-16 px-6">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-3 text-center">How it works</h2>
                    <p className="text-sm text-re-text-muted text-center mb-10 max-w-md mx-auto">
                        Four stages from raw supply-chain data to FDA-ready compliance package.
                    </p>
                    <div className="grid sm:grid-cols-2 md:grid-cols-4 gap-4">
                        {FLOW_STEPS.map((s, i) => (
                            <div key={s.title} className="rounded-lg border border-white/[0.06] bg-white/[0.02] p-5 text-center">
                                <div className="w-8 h-8 rounded-full bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto mb-3">
                                    <span className="text-xs font-bold text-emerald-400">{i + 1}</span>
                                </div>
                                <h3 className="text-sm font-semibold text-re-text-primary mb-1">{s.title}</h3>
                                <p className="text-xs text-re-text-muted leading-relaxed">{s.description}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Free Tools */}
            <section className="relative z-[2] max-w-[900px] mx-auto py-16 px-6">
                <div className="text-center mb-10">
                    <Badge className="mb-4 bg-emerald-500/10 text-emerald-400 border-emerald-500/20">
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
                            className="group rounded-lg border border-white/[0.06] bg-white/[0.02] p-5 hover:border-emerald-500/20 transition-colors"
                        >
                            <h3 className="text-sm font-semibold text-re-text-primary mb-1 group-hover:text-emerald-400 transition-colors">
                                {tool.title}
                            </h3>
                            <p className="text-xs text-re-text-muted leading-relaxed">{tool.description}</p>
                        </Link>
                    ))}
                </div>
            </section>

            {/* Infrastructure Badges */}
            <section className="relative z-[2] border-t border-white/[0.06] bg-white/[0.01]">
                <div className="max-w-[800px] mx-auto py-16 px-6 text-center">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-3">Built for production</h2>
                    <p className="text-sm text-re-text-muted mb-8 max-w-md mx-auto">
                        Enterprise-grade infrastructure from day one.
                    </p>
                    <div className="flex flex-wrap justify-center gap-3">
                        {INTEGRATION_HITS.map((hit) => (
                            <span
                                key={hit}
                                className="text-xs font-mono px-3 py-1.5 rounded-full border border-white/[0.06] bg-white/[0.02] text-re-text-disabled"
                            >
                                {hit}
                            </span>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="relative z-[2] bg-emerald-500/[0.08] border-t border-white/[0.06]">
                <div className="max-w-[600px] mx-auto py-12 px-6 text-center">
                    <h2 className="text-2xl font-bold text-re-text-primary mb-2">Ready to see it live?</h2>
                    <p className="text-sm text-re-text-muted mb-6">
                        Start with the free tools or book a 30-minute walkthrough.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/tools/ftl-checker">
                            <Button className="bg-emerald-500 hover:bg-emerald-600 text-black font-semibold px-6">
                                Try FTL Checker Free
                                <ArrowRight className="ml-2 w-4 h-4" />
                            </Button>
                        </Link>
                        <Link href="/alpha">
                            <Button variant="outline" className="border-white/10 text-re-text-secondary hover:border-emerald-500/30 px-6">
                                Talk to Us
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
