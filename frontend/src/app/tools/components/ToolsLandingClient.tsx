'use client';
// Redeploy trigger: 2026-02-21T00:55:00Z

import { motion } from 'framer-motion';
import {
    Activity,
    ClipboardList,
    Truck,
    Timer,
    FlaskConical,
    CheckCircle2,
    ArrowRight,
    ShieldCheck,
    Zap,
    TrendingUp,
    Leaf,
    LayoutDashboard
} from 'lucide-react';
import Link from 'next/link';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const FSMA_JOURNEY = [
    {
        step: 1,
        id: 'ftl-checker',
        title: 'Scope Assessment',
        toolTitle: 'FTL Coverage Checker',
        description: 'Instantly verify if your food products are covered by FDA FSMA 204 requirements using our 23-tier high-integrity standard.',
        icon: Leaf,
        color: 'var(--re-brand)',
        tag: 'Essential',
        status: 'featured'
    },
    {
        step: 2,
        id: 'cte-mapper',
        title: 'Traceability Foundation',
        toolTitle: 'CTE Coverage Mapper',
        description: 'Visualize your supply chain nodes to see exactly who owes whom data for every transaction.',
        icon: Truck,
        color: 'var(--re-info)',
        tag: 'Integration',
        status: 'beta'
    },
    {
        step: 3,
        id: 'kde-checker',
        title: 'Data Integrity',
        toolTitle: 'KDE Completeness Checker',
        description: 'Generate your customized Key Data Element (KDE) checklist based on your specific FTL product and trading role.',
        icon: ClipboardList,
        color: 'var(--re-info)',
        tag: 'Data Quality',
        status: 'beta'
    },
    {
        step: 4,
        id: 'tlc-validator',
        title: 'Compliance Validation',
        toolTitle: 'TLC Validator',
        description: 'Stress-test your Traceability Lot Code (TLC) format against GS1 standards and FDA\'s requirement for uniqueness.',
        icon: FlaskConical,
        color: 'var(--re-brand)',
        tag: 'Data Integrity',
        status: 'standard'
    },
    {
        step: 5,
        id: 'readiness-assessment',
        title: 'Compliance Readiness',
        toolTitle: 'FSMA 204 Readiness Assessment',
        description: 'Score your facility\'s compliance readiness across product coverage, CTEs, KDEs, and system capabilities. Get an actionable gap report.',
        icon: CheckCircle2,
        color: 'var(--re-brand)',
        tag: 'Assessment',
        status: 'standard'
    },
    {
        step: 6,
        id: 'recall-readiness',
        title: 'Readiness Benchmark',
        toolTitle: 'Recall Readiness Score',
        description: 'Get an A-F grade on your ability to meet the FDA 24-hour records retrieval mandate.',
        icon: ShieldCheck,
        color: 'var(--re-brand)',
        tag: 'Operations',
        status: 'standard'
    },
    {
        step: 7,
        id: 'drill-simulator',
        title: 'Live Simulation',
        toolTitle: '24-Hour Drill Simulator',
        description: 'A scenario-based quest to see if your manual processes can survive a real FDA outbreak investigation.',
        icon: Timer,
        color: 'var(--re-danger)',
        tag: 'Simulation',
        status: 'beta'
    },
    {
        step: 8,
        id: 'fsma-unified',
        title: 'Command Center',
        toolTitle: 'Unified FSMA Dashboard',
        description: 'A consolidated command center for all your FSMA 204 compliance tools, scoring, and readiness metrics.',
        icon: LayoutDashboard,
        color: 'var(--re-brand)',
        tag: 'Strategic',
        isFeatured: true,
        status: 'featured'
    }
];

const STRATEGIC_TOOLS = [
    {
        id: 'roi-calculator',
        title: 'Regulatory ROI Calculator',
        description: 'Quantify the financial impact of manual compliance vs. the RegEngine platform with our personalized ROI engine.',
        icon: TrendingUp,
        color: 'var(--re-brand)',
        tag: 'Strategy'
    }
];

export function ToolsLandingClient() {
    return (
        <div className="re-page min-h-screen py-20 px-4">
            <div className="max-w-7xl mx-auto">
                {/* Header Section */}
                <div className="text-center mb-24 space-y-4">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] text-xs font-bold uppercase tracking-widest"
                    >
                        <Zap className="h-3 w-3" /> Free Compliance Toolkit
                    </motion.div>
                    <motion.h1
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.1 }}
                        className="text-4xl md:text-7xl re-heading-industrial mb-6"
                    >
                        Master the <span className="text-[var(--re-brand)]">Flow</span>
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="text-xl text-[var(--re-text-tertiary)] max-w-3xl mx-auto font-bold"
                    >
                        Stop guessing about compliance. Follow our logical blueprints to benchmark your readiness and identify critical gaps in minutes.
                    </motion.p>
                </div>

                {/* FSMA Journey Section */}
                <div className="mb-32">
                    <div className="flex items-center gap-6 mb-16 px-4">
                        <div className="relative group">
                            <div className="absolute -inset-2 bg-gradient-to-r from-[var(--re-brand)] to-emerald-400 rounded-full blur opacity-40 group-hover:opacity-60 transition duration-1000 group-hover:duration-200" />
                            <div className="relative h-16 w-16 rounded-full bg-[var(--re-brand)] flex items-center justify-center text-white shadow-2xl border-4 border-white dark:border-gray-800">
                                <Activity className="h-9 w-9" />
                            </div>
                            <div className="absolute -bottom-1 -right-1 h-6 w-6 rounded-full bg-white dark:bg-gray-800 flex items-center justify-center shadow-md">
                                <span className="w-3 h-3 rounded-full bg-[var(--re-brand)] animate-ping" />
                            </div>
                        </div>
                        <div>
                            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] text-[10px] font-black uppercase tracking-[0.2em] mb-2 border border-[var(--re-brand-muted)]">
                                <Activity className="h-3 w-3" /> Brand Verified Flow
                            </div>
                            <h2 className="text-4xl md:text-5xl re-heading-industrial mb-1">
                                FSMA 204 <span className="bg-gradient-to-r from-[var(--re-brand)] to-emerald-400 bg-clip-text text-transparent italic">Compliance</span> Journey
                            </h2>
                            <p className="text-[var(--re-text-tertiary)] font-bold text-lg flex items-center gap-2 opacity-80">
                                The definitive path to industrial certainty
                            </p>
                        </div>
                    </div>

                    <div className="relative">
                        {/* Standardized Connecting Line */}
                        <div className="absolute left-[23px] top-6 bottom-6 re-journey-line hidden md:block" />

                        <div className="space-y-12">
                            {FSMA_JOURNEY.map((tool, idx) => (
                                <motion.div
                                    key={tool.id}
                                    initial={{ opacity: 0, x: -20 }}
                                    whileInView={{ opacity: 1, x: 0 }}
                                    viewport={{ once: true }}
                                    transition={{ delay: idx * 0.1 }}
                                    className={`relative pl-0 md:pl-16 ${tool.isFeatured ? 'md:col-span-2' : ''}`}
                                >
                                    {/* Standardized Journey Step Marker */}
                                    <div className="absolute left-0 top-1/2 -translate-y-1/2 re-journey-step-marker hidden md:flex">
                                        {tool.step}
                                    </div>

                                    <Link href={`/tools/${tool.id}`}>
                                        <div className={`group relative overflow-hidden border-[var(--re-border-default)] bg-[var(--re-surface-card)] transition-all rounded-3xl hover:border-[var(--re-brand)] hover:shadow-[0_20px_40px_-15px_rgba(34,197,94,0.15)] ${tool.isFeatured ? 'ring-2 ring-[var(--re-brand)]' : 'border'}`}>
                                            <div className="flex flex-col md:flex-row gap-8 p-8">
                                                <div className="flex-shrink-0">
                                                    <div className="w-16 h-16 rounded-2xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] flex items-center justify-center group-hover:bg-[var(--re-brand)] group-hover:text-white transition-all duration-300">
                                                        <tool.icon className="h-8 w-8" style={{ color: tool.color === 'var(--re-brand)' ? undefined : tool.color }} />
                                                    </div>
                                                </div>
                                                <div className="flex-grow">
                                                    <div className="flex items-center gap-3 mb-2">
                                                        <Badge variant="outline" className="text-[10px] uppercase font-black text-[var(--re-brand)] border-[var(--re-brand-muted)] rounded-full">
                                                            {tool.tag}
                                                            {tool.status === 'beta' && ' (BETA)'}
                                                        </Badge>
                                                        <span className="text-[var(--re-text-muted)] text-xs font-bold uppercase tracking-widest md:hidden">Step {tool.step}</span>
                                                    </div>
                                                    <h3 className="text-xl font-black mb-2 flex items-center gap-2">
                                                        <span className="text-[var(--re-text-tertiary)] group-hover:text-[var(--re-brand)] transition-colors">{tool.title}:</span>
                                                        <span>{tool.toolTitle}</span>
                                                    </h3>
                                                    <p className="text-[var(--re-text-tertiary)] font-medium leading-relaxed max-w-3xl">
                                                        {tool.description}
                                                    </p>
                                                </div>
                                                <div className="flex items-center">
                                                    <div className="h-10 w-10 rounded-full bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] flex items-center justify-center group-hover:bg-[var(--re-brand)] group-hover:text-white transition-all">
                                                        <ArrowRight className="h-5 w-5" />
                                                    </div>
                                                </div>
                                            </div>
                                            {/* Step label for mobile */}
                                            {tool.isFeatured && (
                                                <div className="absolute top-0 right-0 px-4 py-1 bg-[var(--re-brand)] text-white text-[10px] font-black uppercase tracking-tighter rounded-bl-xl">
                                                    Strategic Outcome
                                                </div>
                                            )}
                                        </div>
                                    </Link>
                                </motion.div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Strategic Section */}
                <div className="space-y-8 max-w-3xl">
                        <div className="flex items-center gap-4 mb-2">
                            <div className="h-10 w-10 rounded-xl bg-[var(--re-linkage)] flex items-center justify-center text-white shadow-lg">
                                <TrendingUp className="h-5 w-5" />
                            </div>
                            <h2 className="text-2xl re-heading-industrial !italic !tracking-tighter">Business Strategy</h2>
                        </div>
                        <div className="grid gap-4">
                            {STRATEGIC_TOOLS.map((tool) => (
                                <Link key={tool.id} href={`/tools/${tool.id}`}>
                                    <div className="p-6 border border-[var(--re-border-default)] bg-[var(--re-surface-card)] rounded-2xl hover:border-[var(--re-linkage)] transition-all group">
                                        <div className="flex gap-4">
                                            <div className="h-10 w-10 flex-shrink-0 rounded-lg bg-[var(--re-surface-elevated)] flex items-center justify-center border border-[var(--re-border-default)] group-hover:bg-[var(--re-linkage)] group-hover:text-white transition-colors">
                                                <tool.icon className="h-5 w-5" />
                                            </div>
                                            <div>
                                                <h3 className="font-bold group-hover:text-[var(--re-linkage)] transition-colors">{tool.title}</h3>
                                                <p className="text-xs text-[var(--re-text-tertiary)] font-medium mt-1">{tool.description}</p>
                                            </div>
                                        </div>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </div>

                {/* Footer CTA */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    className="re-card-lp text-center p-12 mt-32"
                >
                    <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--re-brand)] opacity-5 blur-[100px] -mr-32 -mt-32" />
                    <div className="relative z-10 space-y-8">
                        <div className="inline-flex h-16 w-16 items-center justify-center rounded-3xl bg-[var(--re-brand)] text-white shadow-2xl">
                            <CheckCircle2 className="h-8 w-8" />
                        </div>
                        <h2 className="text-3xl md:text-5xl font-black re-heading-industrial">Ready to Automate the Flow?</h2>
                        <p className="text-[var(--re-text-tertiary)] max-w-2xl mx-auto text-lg font-bold">
                            Move beyond interactive tools to a fully automated Compliance Control Center.
                            RegEngine manages your KDEs, monitors your CTEs, and guarantees audit readiness.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-6 justify-center pt-4">
                            <Button size="lg" className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white px-12 h-16 text-lg font-black rounded-2xl shadow-xl hover:shadow-2xl transition-all">
                                Get Started Free
                            </Button>
                            <Button size="lg" variant="outline" className="h-16 px-12 text-lg font-bold border-2 rounded-2xl hover:bg-[var(--re-surface-elevated)] transition-all">
                                Book Strategy Session
                            </Button>
                        </div>
                    </div>
                </motion.div>
            </div>
        </div>
    );
}
