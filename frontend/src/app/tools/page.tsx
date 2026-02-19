'use client';

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
    TrendingUp
} from 'lucide-react';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

const TOOLS = [
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
        status: 'featured'
    },
    {
        id: 'kde-checker',
        title: 'KDE Completeness Checker',
        description: 'Generate your customized Key Data Element (KDE) checklist based on your specific FTL product and trading role.',
        icon: ClipboardList,
        color: 'var(--re-info)',
        tag: 'Data Quality',
        status: 'beta'
    },
    {
        id: 'tlc-validator',
        title: 'TLC Validator',
        description: 'Stress-test your Traceability Lot Code (TLC) format against GS1 standards and FDAs requirement for uniqueness.',
        icon: FlaskConical,
        color: 'var(--re-brand)',
        tag: 'Data Integrity',
        status: 'beta'
    },
    {
        id: 'cte-mapper',
        title: 'CTE Coverage Mapper',
        description: 'Visualize your supply chain nodes to see exactly who owes whom data for every transaction.',
        icon: Truck,
        color: 'var(--re-brand)',
        tag: 'Integration',
        status: 'beta'
    },
    {
        id: 'drill-simulator',
        title: '24-Hour Drill Simulator',
        description: 'A scenario-based quest to see if your manual processes can survive a real FDA outbreak investigation.',
        icon: Timer,
        color: 'var(--re-danger)',
        tag: 'Simulation',
        status: 'beta'
    }
];

export default function ToolsLandingPage() {
    return (
        <div className="min-h-screen py-20 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
            <div className="max-w-7xl mx-auto">
                <div className="text-center mb-16 space-y-4">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[var(--re-brand-muted)] text-[var(--re-brand)] text-xs font-bold uppercase tracking-widest"
                    >
                        <Zap className="h-3 w-3" /> Free FSMA 204 Toolkit
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
                        Stop guessing about FSMA 204. Our free, interactive tools help you benchmark your readiness and identify critical gaps in minutes.
                    </motion.p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
                    {TOOLS.map((tool, idx) => (
                        <motion.div
                            key={tool.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: 0.1 * idx }}
                            whileHover={{ y: -8 }}
                        >
                            <Link href={`/tools/${tool.id}`}>
                                <Card className="h-full border-[var(--re-border-default)] bg-[var(--re-surface-card)] hover:border-[var(--re-border-subtle)] transition-colors group cursor-pointer overflow-hidden">
                                    <div className="h-1.5 w-full" style={{ background: tool.color }} />
                                    <CardHeader className="space-y-4">
                                        <div className="flex justify-between items-start">
                                            <div className="p-3 rounded-2xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] group-hover:border-[var(--re-border-subtle)] transition-colors">
                                                <tool.icon className="h-6 w-6" style={{ color: tool.color }} />
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
                                            <CardTitle className="text-xl font-bold group-hover:text-[var(--re-brand)] transition-colors">{tool.title}</CardTitle>
                                            <CardDescription className="text-sm mt-2 line-clamp-2 leading-relaxed">
                                                {tool.description}
                                            </CardDescription>
                                        </div>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="flex items-center text-sm font-bold text-[var(--re-brand)] opacity-0 group-hover:opacity-100 transition-opacity translate-x-[-10px] group-hover:translate-x-0">
                                            Launch Tool <ArrowRight className="ml-2 h-4 w-4" />
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
