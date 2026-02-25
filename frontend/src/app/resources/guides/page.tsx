'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import {
    ArrowRight,
    BookOpen,
    Leaf,
    Truck,
    Timer,
    CheckCircle2,
    FileText,
    Shield,
    Zap,
} from 'lucide-react';

const GUIDES = [
    {
        title: 'Is Your Product on the FDA Food Traceability List?',
        description:
            'The FDA\'s Food Traceability List covers 23 product categories. This guide explains what\'s on the list, why it matters, and how to check your specific products against the official FTL categories with exact CFR citations.',
        icon: Leaf,
        color: 'var(--re-brand)',
        toolHref: '/tools/ftl-checker',
        toolLabel: 'Try the FTL Coverage Checker',
        tags: ['FSMA 204', 'FTL', '21 CFR 1.1305'],
    },
    {
        title: 'Understanding Critical Tracking Events (CTEs)',
        description:
            'FSMA 204 requires tracking 6 Critical Tracking Events across the supply chain: Harvesting, Cooling, Initial Packing, Shipping, Receiving, and Transformation. Learn which CTEs apply to your supply chain position and what data each requires.',
        icon: Truck,
        color: 'var(--re-info)',
        toolHref: '/tools/cte-mapper',
        toolLabel: 'Map Your CTEs',
        tags: ['CTEs', 'KDEs', '§1.1325–§1.1350'],
    },
    {
        title: 'How to Run a 24-Hour Mock Recall Drill',
        description:
            'The FDA can request your traceability records within 24 hours. Can you produce them? This guide walks through how to set up, execute, and score a practice drill so you know where the gaps are before an actual outbreak.',
        icon: Timer,
        color: 'var(--re-danger)',
        toolHref: '/tools/drill-simulator',
        toolLabel: 'Try the Drill Simulator',
        tags: ['Recall Readiness', '24-Hour Mandate', '§1.1455'],
    },
    {
        title: 'FSMA 204 Compliance Readiness Self-Assessment',
        description:
            'Score your facility\'s readiness across product coverage, CTE tracking, KDE completeness, and system capabilities. This step-by-step assessment produces a gap report covering the areas that matter most for compliance.',
        icon: CheckCircle2,
        color: 'var(--re-brand)',
        toolHref: '/tools/readiness-assessment',
        toolLabel: 'Take the Assessment',
        tags: ['Compliance Score', 'Gap Analysis', 'Readiness'],
    },
];

const REGULATORY_RESOURCES = [
    {
        title: 'FDA FSMA 204 Final Rule',
        href: 'https://www.fda.gov/food/food-safety-modernization-act-fsma/fsma-final-rule-requirements-additional-traceability-records-certain-foods',
        source: 'FDA.gov',
    },
    {
        title: '21 CFR Part 1, Subpart S',
        href: 'https://www.ecfr.gov/current/title-21/part-1/subpart-S',
        source: 'eCFR',
    },
    {
        title: 'FDA Food Traceability List',
        href: 'https://www.fda.gov/food/food-safety-modernization-act-fsma/food-traceability-list',
        source: 'FDA.gov',
    },
];

export default function GuidesPage() {
    return (
        <div className="min-h-screen bg-background">
            {/* Hero */}
            <section className="relative overflow-hidden border-b border-[var(--re-border-default)]">
                <div className="absolute inset-0 bg-gradient-to-br from-[var(--re-brand)]/5 to-transparent" />
                <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    <Breadcrumbs
                        items={[
                            { label: 'Resources', href: '/resources' },
                            { label: 'FSMA 204 Guides' },
                        ]}
                    />
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="text-center py-12 space-y-6"
                    >
                        <Badge className="bg-[var(--re-brand)] rounded-xl py-1 px-4">
                            <BookOpen className="mr-2 h-4 w-4 inline" />
                            Technical Guides
                        </Badge>
                        <h1 className="text-4xl md:text-5xl font-bold tracking-tight">
                            FSMA 204 Compliance Guides
                        </h1>
                        <p className="text-lg text-muted-foreground max-w-3xl mx-auto">
                            CFR-cited technical guides built by regulatory
                            engineers. Each guide links to a free interactive
                            tool so you can act on the knowledge immediately.
                        </p>
                    </motion.div>
                </div>
            </section>

            {/* Guides Grid */}
            <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    {GUIDES.map((guide, i) => (
                        <motion.div
                            key={guide.title}
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: i * 0.1 }}
                        >
                            <Card className="h-full border-[var(--re-border-default)] hover:border-[var(--re-brand)] transition-all group">
                                <CardHeader className="space-y-4">
                                    <div className="flex items-start justify-between">
                                        <div
                                            className="p-3 rounded-xl"
                                            style={{
                                                background: `color-mix(in srgb, ${guide.color} 10%, transparent)`,
                                            }}
                                        >
                                            <guide.icon
                                                className="h-6 w-6"
                                                style={{
                                                    color: guide.color,
                                                }}
                                            />
                                        </div>
                                        <div className="flex gap-1.5 flex-wrap justify-end">
                                            {guide.tags.map((tag) => (
                                                <Badge
                                                    key={tag}
                                                    variant="outline"
                                                    className="text-[9px] uppercase font-bold tracking-widest rounded-full"
                                                >
                                                    {tag}
                                                </Badge>
                                            ))}
                                        </div>
                                    </div>
                                    <div>
                                        <CardTitle className="text-xl leading-tight">
                                            {guide.title}
                                        </CardTitle>
                                        <CardDescription className="mt-2 leading-relaxed">
                                            {guide.description}
                                        </CardDescription>
                                    </div>
                                </CardHeader>
                                <CardContent>
                                    <Link href={guide.toolHref}>
                                        <Button
                                            className="w-full bg-[var(--re-brand)] hover:brightness-110 text-white"
                                            size="lg"
                                        >
                                            {guide.toolLabel}
                                            <ArrowRight className="ml-2 h-4 w-4" />
                                        </Button>
                                    </Link>
                                </CardContent>
                            </Card>
                        </motion.div>
                    ))}
                </div>
            </section>

            {/* Regulatory Sources */}
            <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-border-default)]">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    <div className="flex items-center gap-3 mb-8">
                        <div className="p-2 rounded-lg bg-[var(--re-brand-muted)]">
                            <FileText className="h-5 w-5 text-[var(--re-brand)]" />
                        </div>
                        <h2 className="text-xl font-bold">
                            Primary Regulatory Sources
                        </h2>
                    </div>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        {REGULATORY_RESOURCES.map((resource) => (
                            <a
                                key={resource.title}
                                href={resource.href}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center justify-between p-4 rounded-xl border border-[var(--re-border-default)] bg-background hover:border-[var(--re-brand)] transition-all group"
                            >
                                <div>
                                    <div className="font-medium text-sm group-hover:text-[var(--re-brand)] transition-colors">
                                        {resource.title}
                                    </div>
                                    <div className="text-xs text-muted-foreground mt-0.5">
                                        {resource.source}
                                    </div>
                                </div>
                                <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-[var(--re-brand)] transition-colors" />
                            </a>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center space-y-8">
                <div className="inline-flex h-16 w-16 items-center justify-center rounded-3xl bg-[var(--re-brand)] text-white shadow-2xl mx-auto">
                    <Zap className="h-8 w-8" />
                </div>
                <h2 className="text-3xl font-bold">
                    Ready to Start Your Journey?
                </h2>
                <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                    Begin with the FTL Coverage Checker to see which of your
                    products are covered, then work through the compliance
                    journey step by step.
                </p>
                <div className="flex flex-col sm:flex-row gap-4 justify-center">
                    <Link href="/tools">
                        <Button
                            size="lg"
                            className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white px-8 h-14 text-lg font-bold rounded-2xl"
                        >
                            Explore All Free Tools
                            <ArrowRight className="ml-2 h-5 w-5" />
                        </Button>
                    </Link>
                    <Link href="/tools/ftl-checker">
                        <Button
                            size="lg"
                            variant="outline"
                            className="h-14 px-8 text-lg font-bold rounded-2xl"
                        >
                            Start with FTL Checker
                        </Button>
                    </Link>
                </div>
            </section>
        </div>
    );
}
