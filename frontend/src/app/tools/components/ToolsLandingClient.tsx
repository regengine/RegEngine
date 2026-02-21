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
    Search,
    Users,
    FileText
} from 'lucide-react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const TOOLS = [
    {
        id: 'bias-checker',
        title: 'AI Model Bias Checker',
        description: 'Compute Disparate Impact Ratios (DIR) and 80% Rule compliance for credit models using our demographic parity engine.',
        icon: Users,
        color: '#71717a',
        tag: 'Soon',
        status: 'coming-soon'
    },
    {
        id: 'obligation-scanner',
        title: 'Regulatory Obligation Scanner',
        description: 'Instantly map your financial product features to applicable US regulations across ECOA, TILA, and FCRA.',
        icon: Shield,
        color: '#71717a',
        tag: 'Soon',
        status: 'coming-soon'
    },
    {
        id: 'notice-validator',
        title: 'Notice Validator (A-F)',
        description: 'Paste your adverse action notice text to receive a compliance grade based on 11 critical regulatory requirements.',
        icon: FileText,
        color: '#71717a',
        tag: 'Soon',
        status: 'coming-soon'
    },
    {
        id: 'ftl-checker',
        title: 'FTL Coverage Checker',
        description: 'Instantly verify if your food products are covered by FDA FSMA 204 requirements using our 23-tier high-integrity standard.',
        icon: Leaf,
        color: 'var(--re-brand)',
        tag: 'Essential',
        status: 'featured'
    },
    {
        id: 'fsma-unified',
        title: 'Unified FSMA Dashboard',
        description: 'A consolidated command center for all your FSMA 204 compliance tools, scoring, and readiness metrics.',
        icon: ShieldCheck,
        color: 'var(--re-brand)',
        tag: 'Command Center',
        status: 'featured'
    },
    {
        id: 'roi-calculator',
        title: 'Regulatory ROI Calculator',
        description: 'Quantify the financial impact of manual compliance vs. the RegEngine platform with our personalized ROI engine.',
        icon: TrendingUp,
        color: 'var(--re-brand)',
        tag: 'Strategy',
        status: 'featured'
    },
    {
        id: 'exemption-qualifier',
        title: 'Exemption Qualifier',
        description: 'Quickly determine your FSMA 204 compliance status and eligibility for small business or other exemptions.',
        icon: Shield,
        color: 'var(--re-brand)',
        tag: 'Compliance',
        status: 'featured'
    },
    {
        id: 'recall-readiness',
        title: 'Recall Readiness Score',
        description: 'Get an A-F grade on your ability to meet the FDA 24-hour records retrieval mandate.',
        icon: ShieldCheck,
        color: 'var(--re-brand)',
        tag: 'Operations',
        status: 'standard'
    },
    {
        id: 'kde-checker',
        title: 'KDE Completeness Checker',
        description: 'Generate your customized Key Data Element (KDE) checklist based on your specific FTL product and trading role.',
        icon: ClipboardList,
        color: 'var(--re-info)',
        tag: 'Data Quality',
        status: 'standard'
    },
    {
        id: 'tlc-validator',
        title: 'TLC Validator',
        description: 'Stress-test your Traceability Lot Code (TLC) format against GS1 standards and FDAs requirement for uniqueness.',
        icon: FlaskConical,
        color: 'var(--re-brand)',
        tag: 'Data Integrity',
        status: 'standard'
    },
    {
        id: 'cte-mapper',
        title: 'CTE Coverage Mapper',
        description: 'Visualize your supply chain nodes to see exactly who owes whom data for every transaction.',
        icon: Truck,
        color: 'var(--re-brand)',
        tag: 'Integration',
        status: 'standard'
    },
    {
        id: 'drill-simulator',
        title: '24-Hour Drill Simulator',
        description: 'A scenario-based quest to see if your manual processes can survive a real FDA outbreak investigation.',
        icon: Timer,
        color: 'var(--re-danger)',
        tag: 'Simulation',
        status: 'standard'
    }
];

export function ToolsLandingClient() {
    return (
        <div className="min-h-screen py-20 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
            <div className="max-w-7xl mx-auto">
                <div className="text-center mb-16 space-y-4">
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
                        className="text-4xl md:text-6xl font-black"
                    >
                        Simplify your <span className="text-[var(--re-brand)]">Traceability</span>
                    </motion.h1>
                    <motion.p
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 }}
                        className="text-xl text-[var(--re-text-tertiary)] max-w-2xl mx-auto"
                    >
                        Stop guessing about compliance. Our free, interactive tools help you benchmark your readiness and identify critical gaps across Food Safety and Finance in minutes.
                    </motion.p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {TOOLS.map((tool, idx) => (
                        <motion.div
                            key={tool.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 * idx }}
                            whileHover={tool.status === 'coming-soon' ? {} : { y: -8 }}
                            className={`${tool.status === 'featured' ? 'md:col-span-2' : ''} ${tool.status === 'coming-soon' ? 'opacity-60 cursor-not-allowed' : ''}`}
                        >
                            <Link
                                href={tool.status === 'coming-soon' ? '#' : `/tools/${tool.id}`}
                                className={tool.status === 'coming-soon' ? 'pointer-events-none' : ''}
                            >
                                <Card className={`h-full border-[var(--re-border-default)] bg-[var(--re-surface-card)] transition-all group overflow-hidden ${tool.status === 'featured' ? 'ring-1 ring-[var(--re-brand-muted)] shadow-[0_0_20px_-12px_rgba(var(--re-brand-rgb,34,197,94),0.3)]' : ''
                                    } ${tool.status !== 'coming-soon' ? 'hover:border-[var(--re-border-subtle)] cursor-pointer' : ''}`}>
                                    <div className="h-1.5 w-full" style={{ background: tool.color }} />
                                    <CardHeader className="space-y-4">
                                        <div className="flex justify-between items-start">
                                            <div className="p-3 rounded-2xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] group-hover:border-[var(--re-border-subtle)] transition-colors">
                                                <tool.icon className="h-6 w-6" style={{ color: tool.color }} />
                                                <div className="text-[8px] opacity-20">[REGENGINE-TOOLS-V11]</div>
                                            </div>
                                            <div className="flex items-center gap-2">
                                                {tool.status === 'featured' && (
                                                    <Badge className="bg-[var(--re-brand)] text-white text-[10px] uppercase font-black px-1.5 h-4 border-none">
                                                        NEW
                                                    </Badge>
                                                )}
                                                <Badge variant="outline" className="text-[10px] uppercase font-bold text-[var(--re-text-muted)] group-hover:text-[var(--re-text-secondary)] transition-colors">
                                                    {tool.tag}
                                                    {tool.status === 'beta' && ' (BETA)'}
                                                </Badge>
                                            </div>
                                        </div>
                                        <div>
                                            <CardTitle className={`font-bold group-hover:text-[var(--re-brand)] transition-colors ${tool.status === 'featured' ? 'text-2xl md:text-3xl' : 'text-xl'
                                                }`}>
                                                {tool.title}
                                            </CardTitle>
                                            <CardDescription className={`mt-2 leading-relaxed ${tool.status === 'featured' ? 'text-base line-clamp-3 max-w-2xl' : 'text-sm line-clamp-2'
                                                }`}>
                                                {tool.description}
                                            </CardDescription>
                                        </div>
                                    </CardHeader>
                                    <CardContent>
                                        <div className={`flex items-center text-sm font-bold transition-all ${tool.status === 'coming-soon'
                                            ? 'text-[var(--re-text-muted)] opacity-100'
                                            : 'text-[var(--re-brand)] opacity-0 group-hover:opacity-100 translate-x-[-10px] group-hover:translate-x-0'
                                            }`}>
                                            {tool.status === 'coming-soon' ? 'Available in Q2' : 'Launch Tool'}
                                            <ArrowRight className="ml-2 h-4 w-4" />
                                        </div>
                                    </CardContent>
                                </Card>
                            </Link>
                        </motion.div>
                    ))}
                </div>

                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.8 }}
                    className="mt-20 p-8 rounded-3xl border border-[var(--re-border-default)] bg-gradient-to-br from-[var(--re-surface-card)] to-[var(--re-surface-elevated)] text-center space-y-6"
                >
                    <div className="flex justify-center -space-x-3">
                        <div className="text-[10px] text-[var(--re-text-disabled)] mb-4">[REGENGINE-TOOLS-V11]</div>
                        {[1, 2, 3, 4].map(i => (
                            <div key={i} className="w-12 h-12 rounded-full border-4 border-[var(--re-surface-card)] bg-[var(--re-surface-elevated)] flex items-center justify-center font-bold text-xs">
                                {String.fromCharCode(64 + i)}
                            </div>
                        ))}
                    </div>
                    <h2 className="text-2xl font-bold">Need a Custom Compliance Blueprint?</h2>
                    <p className="text-[var(--re-text-tertiary)] max-w-xl mx-auto text-sm">
                        Join 450+ companies using RegEngine to automate their Rule 204 recordkeeping.
                        Schedule a session with an expert to map your specific supply chain risks.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Button size="lg" className="bg-[var(--re-brand)] px-10 h-12">
                            Book FSMA Strategy Session
                        </Button>
                        <Button size="lg" variant="outline" className="h-12 border-[var(--re-border-default)]">
                            View Enterprise Pricing
                        </Button>
                    </div>
                </motion.div>
            </div>
        </div>
    );
}
