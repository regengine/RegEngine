'use client';

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import Link from 'next/link';
import {
    Leaf, ClipboardList, Truck, Timer, FlaskConical,
    CheckCircle2, ShieldCheck, TrendingUp, LayoutDashboard,
    FileText, Upload, Network, AlertTriangle, Zap, ArrowRight,
    Map, ListChecks, BarChart3, ScanLine, ScanBarcode,
    MessageSquareText, FileOutput,
} from 'lucide-react';

/* ─── CATEGORY DEFINITIONS ─── */
type Category = 'all' | 'assess' | 'validate' | 'simulate' | 'plan';
const CATEGORIES: { id: Category; label: string; Icon: typeof Leaf }[] = [
    { id: 'all', label: 'All Tools', Icon: Zap },
    { id: 'assess', label: 'Assessments & Scoring', Icon: ClipboardList },
    { id: 'validate', label: 'Mapping & Validation', Icon: Map },
    { id: 'simulate', label: 'Simulations & Drills', Icon: Timer },
    { id: 'plan', label: 'Dashboards & Planning', Icon: LayoutDashboard },
];
/* ─── TOOL DATA ─── */
interface Tool {
    id: string;
    title: string;
    description: string;
    icon: typeof Leaf;
    category: Category;
    maturity: 'ga' | 'pilot';
    featured?: boolean;
    journeyStep?: number;
}

const TOOLS: Tool[] = [
    {
        id: 'ftl-checker',
        title: 'FTL Coverage Checker',
        description: 'Instantly check which of your products fall under the FDA\'s 23 Food Traceability List categories.',
        icon: Leaf,
        category: 'validate',
        maturity: 'ga',
        featured: true,
        journeyStep: 1,
    },
    {
        id: 'cte-mapper',
        title: 'CTE Coverage Mapper',
        description: 'Map your supply chain nodes and see who owes whom data for every Critical Tracking Event.',
        icon: Truck,
        category: 'validate',
        maturity: 'ga',
        journeyStep: 2,
    },
    {
        id: 'kde-checker',
        title: 'KDE Completeness Checker',
        description: 'Generate your customized Key Data Element checklist based on your FTL products and trading role.',
        icon: ClipboardList,
        category: 'validate',
        maturity: 'ga',
        journeyStep: 3,
    },
    {
        id: 'tlc-validator',
        title: 'TLC Validator',
        description: 'Stress-test your Traceability Lot Code format against GS1 standards and FDA uniqueness rules.',
        icon: FlaskConical,
        category: 'validate',
        maturity: 'ga',
        journeyStep: 4,
    },
    {
        id: 'readiness-assessment',
        title: 'FSMA 204 Readiness Assessment',
        description: 'Score your facility across product coverage, CTEs, KDEs, and system capabilities. Get an actionable gap report.',
        icon: CheckCircle2,
        category: 'assess',
        maturity: 'ga',
        journeyStep: 5,
    },
    {
        id: 'recall-readiness',
        title: 'Recall Readiness Score',
        description: 'Get an A–F grade on your ability to meet the FDA 24-hour records retrieval mandate.',
        icon: ShieldCheck,
        category: 'assess',
        maturity: 'ga',
        featured: true,
        journeyStep: 6,
    },
    {
        id: 'drill-simulator',
        title: '24-Hour Drill Simulator',
        description: 'Scenario-based simulation to test if your processes survive a real FDA outbreak investigation.',
        icon: Timer,
        category: 'simulate',
        maturity: 'ga',
        journeyStep: 7,
    },
    {
        id: 'fsma-unified',
        title: 'Unified FSMA Dashboard',
        description: 'Consolidated command center for all your compliance tools, scoring, and readiness metrics.',
        icon: LayoutDashboard,
        category: 'plan',
        maturity: 'ga',
        featured: true,
        journeyStep: 8,
    },
    {
        id: 'roi-calculator',
        title: 'Regulatory ROI Calculator',
        description: 'Quantify the financial impact of manual compliance vs. automation. See your break-even in minutes.',
        icon: TrendingUp,
        category: 'assess',
        maturity: 'ga',
        featured: true,
    },
    {
        id: 'retailer-readiness',
        title: 'Retailer Readiness',
        description: 'Benchmark your traceability posture against major retailer requirements (Walmart, Kroger, Costco).',
        icon: BarChart3,
        category: 'assess',
        maturity: 'ga',
    },
    {
        id: 'anomaly-simulator',
        title: 'Anomaly Simulator',
        description: 'Inject realistic traceability anomalies into sample data to test your detection and response workflows.',
        icon: AlertTriangle,
        category: 'simulate',
        maturity: 'ga',
    },
    {
        id: 'data-import',
        title: 'Data Import Assistant',
        description: 'Map and import your existing spreadsheet data into FSMA-ready CTE/KDE structures with guided validation.',
        icon: Upload,
        category: 'plan',
        maturity: 'ga',
    },
    {
        id: 'knowledge-graph',
        title: 'Knowledge Graph',
        description: 'Visualize your traceability network — suppliers, facilities, products, and their compliance relationships.',
        icon: Network,
        category: 'plan',
        maturity: 'ga',
    },
    {
        id: 'sop-generator',
        title: 'SOP Generator',
        description: 'Auto-generate Standard Operating Procedures for FSMA 204 record-keeping based on your facility profile.',
        icon: FileText,
        category: 'plan',
        maturity: 'ga',
    },
    {
        id: 'label-scanner',
        title: 'Label Scanner',
        description: 'Point your camera at a food label or barcode. AI extracts product name, lot code, GTIN, expiry, and maps it to FSMA 204 KDEs instantly.',
        icon: ScanLine,
        category: 'validate',
        maturity: 'ga',
        featured: true,
    },
    {
        id: 'scan',
        title: 'GS1 Barcode Scanner',
        description: 'Scan a GS1 barcode with your camera. Auto-fill CTE fields and ingest in one tap. Supports GS1-128, Digital Link, and DataMatrix.',
        icon: ScanBarcode,
        category: 'validate',
        maturity: 'ga',
        featured: true,
    },
    {
        id: 'ask',
        title: 'Traceability Query Engine',
        description: 'Ask questions about your supply chain in plain English. Get traced results with evidence and confidence scores.',
        icon: MessageSquareText,
        category: 'plan',
        maturity: 'ga',
        featured: true,
    },
    {
        id: 'export',
        title: 'FDA Export Package Generator',
        description: 'Generate a verifiable 21 CFR 1.1455 compliance package with SHA-256 chain verification in one click.',
        icon: FileOutput,
        category: 'plan',
        maturity: 'ga',
        featured: true,
    },
];
const JOURNEY_STEPS = TOOLS
    .filter(t => t.journeyStep)
    .sort((a, b) => (a.journeyStep ?? 0) - (b.journeyStep ?? 0));

function badgeClasses(maturity: 'ga' | 'pilot', featured?: boolean): string {
    if (featured) return 'bg-[var(--re-brand)] text-white';
    if (maturity === 'ga') return 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20';
    return 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20';
}

function badgeLabel(maturity: 'ga' | 'pilot', featured?: boolean): string {
    if (featured) return 'Popular';
    if (maturity === 'ga') return 'Live';
    return 'Pilot';
}

/* ─── COMPONENT ─── */
export function ToolsLandingClient() {
    const [activeCategory, setActiveCategory] = useState<Category>('all');
    const [journeyOpen, setJourneyOpen] = useState(false);

    const filtered = activeCategory === 'all'
        ? TOOLS
        : TOOLS.filter(t => t.category === activeCategory);

    return (
        <div className="re-page min-h-screen">
            {/* ═══ HERO ═══ */}
            <section className="relative z-[2] max-w-[1120px] mx-auto pt-14 sm:pt-20 pb-10 sm:pb-12 px-4 sm:px-6 text-center">
                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] text-xs font-bold uppercase tracking-widest mb-6 border border-[var(--re-brand)]/20"
                >
                    <Zap className="h-3 w-3" /> 15 Free Tools &middot; No Login Required
                </motion.div>
                <motion.h1
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.05 }}
                    className="text-4xl md:text-6xl font-bold text-[var(--re-text-primary)] leading-tight mb-5"
                >
                    Free FSMA 204<br />
                    <span className="bg-gradient-to-r from-[var(--re-brand)] to-emerald-400 bg-clip-text text-transparent">
                        Compliance Tools
                    </span>
                </motion.h1>

                <motion.p
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.1 }}
                    className="text-lg text-[var(--re-text-muted)] max-w-[580px] mx-auto mb-8 leading-relaxed"
                >
                    Instant results. Built for growers, packers, and processors who need to move fast before retailer deadlines hit.
                </motion.p>

                <motion.div
                    initial={{ opacity: 0, y: 16 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: 0.15 }}
                    className="flex flex-col sm:flex-row gap-3 justify-center"
                >
                    <Link href="/tools/recall-readiness">
                        <button className="inline-flex items-center gap-2 px-6 py-3 rounded-xl bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold text-sm transition-all hover:-translate-y-0.5"
                            style={{ boxShadow: '0 4px 16px var(--re-brand-muted)' }}
                        >
                            Start with Readiness Assessment
                            <ArrowRight className="w-4 h-4" />
                        </button>
                    </Link>
                    <button
                        onClick={() => document.getElementById('tool-grid')?.scrollIntoView({ behavior: 'smooth' })}
                        className="px-6 py-3 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-secondary)] font-semibold text-sm hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] transition-all"
                    >
                        Browse All Tools
                    </button>
                </motion.div>
            </section>
            {/* ═══ CATEGORY FILTER TABS ═══ */}
            <section id="tool-grid" className="relative z-[2] max-w-[1120px] mx-auto px-4 sm:px-6 pb-4 pt-8">
                <div className="flex gap-2 justify-start sm:justify-center overflow-x-auto pb-2 sm:pb-0 sm:flex-wrap -mx-4 px-4 sm:mx-0 sm:px-0 scrollbar-none">
                    {CATEGORIES.map(cat => (
                        <button
                            key={cat.id}
                            onClick={() => setActiveCategory(cat.id)}
                            className={`inline-flex items-center gap-1.5 px-4 py-2.5 rounded-full text-sm font-medium whitespace-nowrap transition-all ${
                                activeCategory === cat.id
                                    ? 'bg-[var(--re-brand)] text-white shadow-md'
                                    : 'bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] text-[var(--re-text-muted)] hover:border-[var(--re-brand)] hover:text-[var(--re-brand)]'
                            }`}
                        >
                            <cat.Icon className="w-3.5 h-3.5" />
                            {cat.label}
                        </button>
                    ))}
                </div>
            </section>
            {/* ═══ CARD GRID ═══ */}
            <section className="relative z-[2] max-w-[1120px] mx-auto px-4 sm:px-6 py-8">
                <AnimatePresence mode="wait">
                    <motion.div
                        key={activeCategory}
                        initial={{ opacity: 0, y: 8 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -8 }}
                        transition={{ duration: 0.2 }}
                        className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5"
                    >
                        {filtered.map((tool) => (
                            <Link key={tool.id} href={tool.id === 'retailer-readiness' ? '/retailer-readiness' : `/tools/${tool.id}`}>
                                <div
                                    className={`group relative h-full rounded-2xl border bg-[var(--re-surface-card)] p-6 transition-all hover:-translate-y-1 ${
                                        tool.featured
                                            ? 'border-[var(--re-brand)]/40'
                                            : 'border-[var(--re-surface-border)] hover:border-[var(--re-brand)]/30'
                                    }`}
                                    style={{
                                        boxShadow: tool.featured
                                            ? '0 4px 24px rgba(0,0,0,0.10), 0 0 0 1px var(--re-surface-border), 0 0 20px var(--re-brand-muted)'
                                            : '0 2px 12px rgba(0,0,0,0.06)',
                                    }}
                                >
                                    {/* Header row: icon + badge */}
                                    <div className="flex items-center justify-between mb-4">
                                        <div className="w-12 h-12 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] flex items-center justify-center group-hover:bg-[var(--re-brand)] group-hover:border-[var(--re-brand)] transition-all duration-300">
                                            <tool.icon className="h-6 w-6 text-[var(--re-brand)] group-hover:text-white transition-colors duration-300" />
                                        </div>
                                        <span className={`text-[10px] font-bold uppercase tracking-wider px-2.5 py-1 rounded-full ${badgeClasses(tool.maturity, tool.featured)}`}>
                                            {badgeLabel(tool.maturity, tool.featured)}
                                        </span>
                                    </div>
                                    <h3 className="text-lg font-bold text-[var(--re-text-primary)] mb-2 group-hover:text-[var(--re-brand)] transition-colors">
                                        {tool.title}
                                    </h3>
                                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mb-5">
                                        {tool.description}
                                    </p>
                                    {/* CTA */}
                                    <div className="mt-auto">
                                        {tool.maturity === 'ga' ? (
                                            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-[var(--re-brand)] group-hover:gap-2.5 transition-all">
                                                Launch Tool <ArrowRight className="h-4 w-4" />
                                            </span>
                                        ) : (
                                            <span className="inline-flex items-center gap-1.5 text-sm font-semibold text-amber-500">
                                                Coming Soon
                                            </span>
                                        )}
                                    </div>
                                </div>
                            </Link>
                        ))}
                    </motion.div>
                </AnimatePresence>
            </section>
            {/* ═══ RECOMMENDED JOURNEY (collapsible) ═══ */}
            <section className="relative z-[2] max-w-[860px] mx-auto px-4 sm:px-6 py-10">
                <button
                    onClick={() => setJourneyOpen(!journeyOpen)}
                    className="w-full flex items-center justify-between gap-4 rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5 text-left hover:border-[var(--re-brand)] transition-all"
                    style={{ boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}
                >
                    <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-lg bg-[var(--re-brand-muted)] border border-[var(--re-brand)]/20 flex items-center justify-center flex-shrink-0">
                            <ListChecks className="w-5 h-5 text-[var(--re-brand)]" />
                        </div>
                        <div>
                            <h2 className="text-lg font-bold text-[var(--re-text-primary)]">
                                New to FSMA 204? Follow the 8-step compliance journey
                            </h2>
                            <p className="text-sm text-[var(--re-text-muted)] mt-0.5">
                                A logical path from scope assessment to full audit readiness.
                            </p>
                        </div>
                    </div>
                    <span className={`text-[var(--re-text-disabled)] text-2xl transition-transform flex-shrink-0 ${journeyOpen ? 'rotate-45' : ''}`}>
                        +
                    </span>
                </button>

                <AnimatePresence>
                    {journeyOpen && (
                        <motion.div
                            initial={{ height: 0, opacity: 0 }}
                            animate={{ height: 'auto', opacity: 1 }}
                            exit={{ height: 0, opacity: 0 }}
                            transition={{ duration: 0.3 }}
                            className="overflow-hidden"
                        >
                            <div className="mt-4 space-y-3">
                                {JOURNEY_STEPS.map((tool) => (
                                    <Link key={tool.id} href={tool.id === 'retailer-readiness' ? '/retailer-readiness' : `/tools/${tool.id}`}>
                                        <div className="flex items-center gap-4 p-4 rounded-xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] hover:border-[var(--re-brand)] transition-all group"
                                            style={{ boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
                                        >
                                            <div className="w-9 h-9 rounded-full bg-[var(--re-brand)] text-white flex items-center justify-center text-sm font-bold shrink-0">
                                                {tool.journeyStep}
                                            </div>
                                            <div className="flex-grow min-w-0">
                                                <h3 className="text-sm font-bold text-[var(--re-text-primary)] group-hover:text-[var(--re-brand)] transition-colors">
                                                    {tool.title}
                                                </h3>
                                                <p className="text-xs text-[var(--re-text-muted)] truncate">{tool.description}</p>
                                            </div>
                                            <span className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full shrink-0 ${badgeClasses(tool.maturity)}`}>
                                                {badgeLabel(tool.maturity)}
                                            </span>
                                            <ArrowRight className="h-4 w-4 text-[var(--re-text-disabled)] group-hover:text-[var(--re-brand)] shrink-0 transition-colors" />
                                        </div>
                                    </Link>
                                ))}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </section>
            {/* ═══ ALPHA CTA ═══ */}
            <section className="relative z-[2] max-w-[860px] mx-auto px-4 sm:px-6 pb-20 pt-8">
                <motion.div
                    initial={{ opacity: 0, scale: 0.97 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    className="relative overflow-hidden rounded-3xl border border-[var(--re-brand)]/20 text-center p-6 sm:p-12"
                    style={{
                        background: 'var(--re-brand-muted)',
                        boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
                    }}
                >
                    <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--re-brand)] opacity-5 blur-[100px] -mr-32 -mt-32" />
                    <div className="relative z-10">
                        <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-[var(--re-brand)] text-white mb-6"
                            style={{ boxShadow: '0 4px 16px var(--re-brand-muted)' }}
                        >
                            <CheckCircle2 className="h-7 w-7" />
                        </div>
                        <h2 className="text-3xl md:text-4xl font-bold text-[var(--re-text-primary)] mb-4">
                            Ready to automate?
                        </h2>
                        <p className="text-[var(--re-text-muted)] max-w-lg mx-auto mb-8 leading-relaxed">
                            Move beyond free tools to full automation. Alpha partners get white-glove onboarding, real-time monitoring, and direct founder access.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-3 justify-center">
                            <Link href="/alpha">
                                <button className="inline-flex items-center gap-2 px-8 py-3.5 rounded-xl bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white font-semibold transition-all hover:-translate-y-0.5"
                                    style={{ boxShadow: '0 4px 16px var(--re-brand-muted)' }}
                                >
                                    Become a Founding Design Partner
                                    <ArrowRight className="w-4 h-4" />
                                </button>
                            </Link>
                            <Link href="/tools/recall-readiness">
                                <button className="px-8 py-3.5 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-secondary)] font-semibold hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] transition-all">
                                    Get Free Assessment
                                </button>
                            </Link>
                        </div>
                    </div>
                </motion.div>
            </section>
        </div>
    );
}
