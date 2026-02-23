'use client';
// Redeploy trigger: 2026-02-21T00:55:00Z

import { motion } from 'framer-motion';
import {
    Shield,
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
    LayoutDashboard,
    Users,
    FileText
} from 'lucide-react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
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
        tag: 'Essential'
    },
    {
        step: 2,
        id: 'exemption-qualifier',
        title: 'Eligibility',
        toolTitle: 'Exemption Qualifier',
        description: 'Quickly determine your FSMA 204 compliance status and eligibility for small business or other exemptions.',
        icon: Shield,
        color: 'var(--re-brand)',
        tag: 'Compliance'
    },
    {
        step: 3,
        id: 'cte-mapper',
        title: 'Traceability Foundation',
        toolTitle: 'CTE Coverage Mapper',
        description: 'Visualize your supply chain nodes to see exactly who owes whom data for every transaction.',
        icon: Truck,
        color: 'var(--re-info)',
        tag: 'Integration'
    },
    {
        step: 4,
        id: 'kde-checker',
        title: 'Data Integrity',
        toolTitle: 'KDE Completeness Checker',
        description: 'Generate your customized Key Data Element (KDE) checklist based on your specific FTL product and trading role.',
        icon: ClipboardList,
        color: 'var(--re-info)',
        tag: 'Data Quality'
    },
    {
        step: 5,
        id: 'tlc-validator',
        title: 'Compliance Validation',
        toolTitle: 'TLC Validator',
        description: 'Stress-test your Traceability Lot Code (TLC) format against GS1 standards and FDA\'s requirement for uniqueness.',
        icon: FlaskConical,
        color: 'var(--re-brand)',
        tag: 'Data Integrity'
    },
    {
        step: 6,
        id: 'recall-readiness',
        title: 'Readiness Benchmark',
        toolTitle: 'Recall Readiness Score',
        description: 'Get an A-F grade on your ability to meet the FDA 24-hour records retrieval mandate.',
        icon: ShieldCheck,
        color: 'var(--re-brand)',
        tag: 'Operations'
    },
    {
        step: 7,
        id: 'drill-simulator',
        title: 'Live Simulation',
        toolTitle: '24-Hour Drill Simulator',
        description: 'A scenario-based quest to see if your manual processes can survive a real FDA outbreak investigation.',
        icon: Timer,
        color: 'var(--re-danger)',
        tag: 'Simulation'
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
        isFeatured: true
    }
];

const FINANCE_TOOLS = [
    {
        id: 'bias-checker',
        title: 'AI Model Bias Checker',
        description: 'Compute Disparate Impact Ratios (DIR) and 80% Rule compliance for credit models using our demographic parity engine.',
        icon: Users,
        color: 'var(--re-brand)',
        tag: 'Finance'
    },
    {
        id: 'notice-validator',
        title: 'Notice Validator (A-F)',
        description: 'Paste your adverse action notice text to receive a compliance grade based on 11 critical regulatory requirements.',
        icon: FileText,
        color: 'var(--re-brand)',
        tag: 'Finance'
    },
    {
        id: 'obligation-scanner',
        title: 'Regulatory Obligation Scanner',
        description: 'Instantly map your financial product features to applicable US regulations across ECOA, TILA, and FCRA.',
        icon: Shield,
        color: 'var(--re-brand)',
        tag: 'Finance'
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
        <div className="min-h-screen py-20 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
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
                        className="text-4xl md:text-7xl font-black mb-6"
                    >
                        Master the <span className="text-[var(--re-brand)]">Flow</span>
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="text-xl text-[var(--re-text-tertiary)] max-w-3xl mx-auto"
                    >
                        Stop guessing about compliance. Follow our logical blueprints to benchmark your readiness and identify critical gaps in minutes.
                    </motion.p>
                </div>

                {/* FSMA Journey Section */}
                <div className="mb-32">
                    <div className="flex items-center gap-4 mb-12">
                        <div className="h-12 w-12 rounded-2xl bg-[var(--re-brand)] flex items-center justify-center text-white shadow-lg">
                            <ShieldCheck className="h-6 w-6" />
                        </div>
                        <div>
                            <h2 className="text-3xl font-black italic uppercase tracking-tighter">FSMA 204 Compliance Journey</h2>
                            <p className="text-[var(--re-text-tertiary)] font-bold">A sequential path to regulatory certainty</p>
                        </div>
                    </div>

                    <div className="relative">
                        {/* Connecting Line for Journey */}
                        <div className="absolute left-[23px] top-6 bottom-6 w-0.5 bg-gradient-to-b from-[var(--re-brand)] via-[var(--re-info)] to-[var(--re-brand-muted)] hidden md:block" />

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
                                    {/* Journey Step Marker */}
                                    <div className="absolute left-0 top-1/2 -translate-y-1/2 w-12 h-12 rounded-full bg-[var(--re-surface-card)] border-4 border-[var(--re-brand)] flex items-center justify-center font-black text-lg z-10 hidden md:flex">
                                        {tool.step}
                                    </div>

                                    <Link href={`/tools/${tool.id}`}>
                                        <Card className={`group relative overflow-hidden border-[var(--re-border-default)] bg-[var(--re-surface-card)] transition-all hover:border-[var(--re-brand)] hover:shadow-[0_20px_40px_-15px_rgba(34,197,94,0.15)] ${tool.isFeatured ? 'ring-2 ring-[var(--re-brand)]' : ''}`}>
                                            <div className="flex flex-col md:flex-row gap-8 p-8">
                                                <div className="flex-shrink-0">
                                                    <div className="w-16 h-16 rounded-2xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] flex items-center justify-center group-hover:bg-[var(--re-brand)] group-hover:text-white transition-all duration-300">
                                                        <tool.icon className="h-8 w-8" style={{ color: tool.color === 'var(--re-brand)' ? undefined : tool.color }} />
                                                    </div>
                                                </div>
                                                <div className="flex-grow">
                                                    <div className="flex items-center gap-3 mb-2">
                                                        <Badge variant="outline" className="text-[10px] uppercase font-black text-[var(--re-brand)] border-[var(--re-brand-muted)]">
                                                            {tool.tag}
                                                        </Badge>
                                                        <span className="text-[var(--re-text-muted)] text-xs font-bold uppercase tracking-widest md:hidden">Step {tool.step}</span>
                                                    </div>
                                                    <h3 className="text-xl font-black mb-2 flex items-center gap-2">
                                                        <span className="text-[var(--re-text-tertiary)] group-hover:text-[var(--re-brand)] transition-colors">{tool.title}:</span>
                                                        <span>{tool.toolTitle}</span>
                                                    </h3>
                                                    <p className="text-[var(--re-text-tertiary)] leading-relaxed max-w-3xl">
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
                                        </Card>
                                    </Link>
                                </motion.div>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Grid Sections */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-16">
                    {/* Finance Section */}
                    <div className="space-y-8">
                        <div className="flex items-center gap-4 mb-2">
                            <div className="h-10 w-10 rounded-xl bg-blue-500 flex items-center justify-center text-white shadow-lg">
                                <Users className="h-5 w-5" />
                            </div>
                            <h2 className="text-2xl font-black italic uppercase tracking-tighter">Finance & Lending</h2>
                        </div>
                        <div className="grid gap-4">
                            {FINANCE_TOOLS.map((tool) => (
                                <Link key={tool.id} href={`/tools/${tool.id}`}>
                                    <Card className="p-6 border-[var(--re-border-default)] bg-[var(--re-surface-card)] hover:border-blue-500/50 transition-all group">
                                        <div className="flex gap-4">
                                            <div className="h-10 w-10 flex-shrink-0 rounded-lg bg-[var(--re-surface-elevated)] flex items-center justify-center border border-[var(--re-border-default)] group-hover:bg-blue-500 group-hover:text-white transition-colors">
                                                <tool.icon className="h-5 w-5" />
                                            </div>
                                            <div>
                                                <h3 className="font-bold group-hover:text-blue-500 transition-colors">{tool.title}</h3>
                                                <p className="text-xs text-[var(--re-text-tertiary)] mt-1">{tool.description}</p>
                                            </div>
                                        </div>
                                    </Card>
                                </Link>
                            ))}
                        </div>
                    </div>

                    {/* Strategic Section */}
                    <div className="space-y-8">
                        <div className="flex items-center gap-4 mb-2">
                            <div className="h-10 w-10 rounded-xl bg-purple-500 flex items-center justify-center text-white shadow-lg">
                                <TrendingUp className="h-5 w-5" />
                            </div>
                            <h2 className="text-2xl font-black italic uppercase tracking-tighter">Business Strategy</h2>
                        </div>
                        <div className="grid gap-4">
                            {STRATEGIC_TOOLS.map((tool) => (
                                <Link key={tool.id} href={`/tools/${tool.id}`}>
                                    <Card className="p-6 border-[var(--re-border-default)] bg-[var(--re-surface-card)] hover:border-purple-500/50 transition-all group">
                                        <div className="flex gap-4">
                                            <div className="h-10 w-10 flex-shrink-0 rounded-lg bg-[var(--re-surface-elevated)] flex items-center justify-center border border-[var(--re-border-default)] group-hover:bg-purple-500 group-hover:text-white transition-colors">
                                                <tool.icon className="h-5 w-5" />
                                            </div>
                                            <div>
                                                <h3 className="font-bold group-hover:text-purple-500 transition-colors">{tool.title}</h3>
                                                <p className="text-xs text-[var(--re-text-tertiary)] mt-1">{tool.description}</p>
                                            </div>
                                        </div>
                                    </Card>
                                </Link>
                            ))}
                        </div>
                    </div>
                </div>

                {/* Footer CTA */}
                <motion.div
                    initial={{ opacity: 0, scale: 0.95 }}
                    whileInView={{ opacity: 1, scale: 1 }}
                    viewport={{ once: true }}
                    className="mt-32 p-12 rounded-[2rem] border border-[var(--re-border-default)] bg-gradient-to-br from-[var(--re-surface-card)] via-[var(--re-surface-elevated)] to-[var(--re-brand-muted)] text-center relative overflow-hidden"
                >
                    <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--re-brand)] opacity-5 blur-[100px] -mr-32 -mt-32" />
                    <div className="relative z-10 space-y-8">
                        <div className="inline-flex h-16 w-16 items-center justify-center rounded-3xl bg-[var(--re-brand)] text-white shadow-2xl">
                            <CheckCircle2 className="h-8 w-8" />
                        </div>
                        <h2 className="text-3xl md:text-5xl font-black">Ready to Automate the Flow?</h2>
                        <p className="text-[var(--re-text-tertiary)] max-w-2xl mx-auto text-lg">
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
