'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
    FileText,
    Download,
    Filter,
    Zap,
    Lock,
    Activity,
    Server as ServerIcon,
    AlertTriangle,
    Cog,
    Car,
    Plane,
    Building,
    Gamepad2,
    ArrowRight,
    CheckCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

// White paper metadata
const whitePapers = [
    {
        id: 'energy',
        title: 'Energy Sector Compliance',
        subtitle: 'Automating NERC CIP Compliance with Immutable Evidence Architecture',
        icon: Zap,
        framework: 'NERC CIP',
        size: '19KB',
        pages: '~12 pages',
        status: 'available',
        topics: ['Immutable evidence vault', 'NERC CIP-013 supply chain', 'Audit prep 95% reduction', '$285K/year savings'],
        description: 'How electric utilities achieve NERC CIP compliance with cryptographic evidence integrity.',
    },
    {
        id: 'finance',
        title: 'Finance Compliance',
        subtitle: 'Accelerating B2B SaaS Sales Velocity with SOX Automation',
        icon: Lock,
        framework: 'SOX / SEC',
        size: '43KB',
        pages: '~18 pages',
        status: 'available',
        topics: ['Sales velocity acceleration', 'Instant SOX proof', '67% faster sales cycles', '$5M+ revenue growth'],
        description: 'How B2B SaaS companies turn SOX compliance into a competitive sales advantage.',
    },
    {
        id: 'healthcare',
        title: 'Healthcare Compliance',
        subtitle: 'Automating HIPAA/HITECH Compliance with Immutable PHI Access Architecture',
        icon: Activity,
        framework: 'HIPAA / HITECH',
        size: '46KB',
        pages: '~20 pages',
        status: 'available',
        topics: ['Breach prevention ($800K/year)', '72-hour incident response', 'OCR audit readiness', 'Insider threat detection'],
        description: 'How healthcare organizations prevent $10.1M breaches with immutable PHI access logs.',
    },
    {
        id: 'technology',
        title: 'Technology Compliance',
        subtitle: 'Accelerating Enterprise Sales with SOC 2 Trust Pages',
        icon: ServerIcon,
        framework: 'SOC 2 / ISO 27001',
        size: '47KB',
        pages: '~19 pages',
        status: 'available',
        topics: ['Instant compliance trust pages', 'SOC 2 automation', 'Win rate +13 points', '$4M+ ARR growth'],
        description: 'How B2B SaaS companies close enterprise deals 67% faster with instant SOC 2 proof.',
    },
    {
        id: 'nuclear',
        title: 'Nuclear Compliance',
        subtitle: 'Database-Enforced Immutability for NRC 10 CFR Compliance',
        icon: AlertTriangle,
        framework: 'NRC 10 CFR',
        size: '51KB',
        pages: '~21 pages',
        status: 'available',
        topics: ['License protection', 'Database-enforced immutability', 'PostgreSQL CHECK constraints', 'NRC-ready architecture'],
        description: 'How nuclear facilities achieve mathematically-provable evidence integrity for NRC inspections.',
    },
    {
        id: 'gaming',
        title: 'Gaming Compliance',
        subtitle: 'Multi-Jurisdiction Gaming License Protection',
        icon: Gamepad2,
        framework: 'AML / Gaming Commission',
        size: '11KB',
        pages: '~8 pages',
        status: 'coming-soon',
        topics: ['License protection', 'Real-time self-exclusion', 'AML false positive reduction', 'Multi-jurisdiction compliance'],
        description: 'How gaming operators protect licenses with real-time compliance across multiple states.',
    },
    {
        id: 'manufacturing',
        title: 'Manufacturing Compliance',
        subtitle: 'FDA Recall Prevention with Immutable Lot Traceability',
        icon: Cog,
        framework: 'ISO 9001 / FDA QSR',
        size: '5.2KB',
        pages: '~5 pages',
        status: 'coming-soon',
        topics: ['Product recall prevention ($20M-$100M)', 'FDA lot traceability', 'CAPA effectiveness', 'Warning letter prevention'],
        description: 'How manufacturers prevent $50M product recalls with immutable supply chain traceability.',
    },
    {
        id: 'automotive',
        title: 'Automotive Compliance',
        subtitle: 'Tier Supplier Traceability for Automotive Recalls',
        icon: Car,
        framework: 'IATF 16949 / ISO 26262',
        size: '8.6KB',
        pages: '~7 pages',
        status: 'coming-soon',
        topics: ['Automotive recall prevention', 'PPAP automation', 'Tier-to-tier traceability', 'OEM audit efficiency'],
        description: 'How automotive tier suppliers prevent $100M+ recalls with safety-critical part traceability.',
    },
    {
        id: 'aerospace',
        title: 'Aerospace Compliance',
        subtitle: 'Part Lineage for Airworthiness Certification',
        icon: Plane,
        framework: 'AS9100 / FAA',
        size: '5.7KB',
        pages: '~6 pages',
        status: 'coming-soon',
        topics: ['Airworthiness certification', 'Counterfeit part prevention', 'FAA Form 8130-3 automation', 'As9100 first article inspection'],
        description: 'How aerospace suppliers achieve airworthiness with immutable part lineage and counterfeit detection.',
    },
    {
        id: 'construction',
        title: 'Construction Compliance',
        subtitle: 'Multi-Site Worker Safety & OSHA Compliance',
        icon: Building,
        framework: 'OSHA / Building Codes',
        size: '5.3KB',
        pages: '~5 pages',
        status: 'coming-soon',
        topics: ['Worker safety tracking', 'OSHA fine prevention ($50K-$500K)', 'Multi-site monitoring', 'Insurance premium reduction (20%)'],
        description: 'How general contractors prevent OSHA violations with real-time multi-site safety tracking.',
    },
];

export default function WhitePapersPage() {
    const [filterFramework, setFilterFramework] = useState<string>('all');

    const frameworks = ['all', 'NERC CIP', 'SOX / SEC', 'HIPAA / HITECH', 'SOC 2 / ISO 27001', 'NRC 10 CFR', 'AML / Gaming Commission', 'ISO 9001 / FDA QSR', 'IATF 16949 / ISO 26262', 'AS9100 / FAA', 'OSHA / Building Codes'];

    const filteredPapers = filterFramework === 'all'
        ? whitePapers
        : whitePapers.filter(wp => wp.framework === filterFramework);

    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            {/* Hero Section */}
            <section className="pt-20 pb-12 px-4">
                <div className="max-w-6xl mx-auto text-center">
                    <div className="inline-flex items-center gap-2 px-4 py-2 rounded-full bg-emerald-50 dark:bg-emerald-900/20 mb-6">
                        <FileText className="h-4 w-4 text-emerald-600" />
                        <span className="text-sm font-medium text-emerald-900 dark:text-emerald-100">
                            Professional Enterprise White Papers
                        </span>
                    </div>

                    <h1 className="text-4xl md:text-5xl font-bold mb-4">
                        Industry White Papers
                    </h1>
                    <p className="text-xl text-muted-foreground max-w-3xl mx-auto mb-8">
                        Comprehensive compliance strategies for your industry sector. Download professional white papers
                        with ROI calculations, competitive analysis, and customer success stories.
                    </p>

                    {/* Stats */}
                    <div className="flex justify-center gap-8 mb-8">
                        <div>
                            <div className="text-3xl font-bold text-emerald-600">10</div>
                            <div className="text-sm text-muted-foreground">Industry Verticals</div>
                        </div>
                        <div>
                            <div className="text-3xl font-bold text-emerald-600">15-25</div>
                            <div className="text-sm text-muted-foreground">Pages Each</div>
                        </div>
                        <div>
                            <div className="text-3xl font-bold text-emerald-600">5</div>
                            <div className="text-sm text-muted-foreground">Available Now</div>
                        </div>
                    </div>

                    {/* Filter */}
                    <div className="flex items-center justify-center gap-4 mb-8">
                        <Filter className="h-5 w-5 text-muted-foreground" />
                        <select
                            value={filterFramework}
                            onChange={(e) => setFilterFramework(e.target.value)}
                            className="px-4 py-2 border rounded-lg bg-background"
                        >
                            {frameworks.map(fw => (
                                <option key={fw} value={fw}>
                                    {fw === 'all' ? 'All Industries' : fw}
                                </option>
                            ))}
                        </select>
                    </div>
                </div>
            </section>

            {/* White Papers Grid */}
            <section className="py-12 px-4">
                <div className="max-w-6xl mx-auto">
                    <div className="grid md:grid-cols-2 gap-6">
                        {filteredPapers.map((paper) => {
                            const Icon = paper.icon;
                            return (
                                <Card key={paper.id} className="hover:shadow-lg transition-shadow">
                                    <CardHeader>
                                        <div className="flex items-start justify-between mb-2">
                                            <div className="p-3 rounded-lg bg-gradient-to-br from-emerald-50 to-teal-50 dark:from-emerald-900/20 dark:to-teal-900/20">
                                                <Icon className="h-6 w-6 text-emerald-600" />
                                            </div>
                                            {paper.status === 'available' ? (
                                                <Badge className="bg-emerald-600">Available</Badge>
                                            ) : (
                                                <Badge variant="outline">Planned Release</Badge>
                                            )}
                                        </div>
                                        <CardTitle className="text-xl">{paper.title}</CardTitle>
                                        <CardDescription className="text-sm">
                                            {paper.subtitle}
                                        </CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="space-y-4">
                                            {/* Framework Badge */}
                                            <div className="flex items-center gap-2 text-sm text-muted-foreground">
                                                <FileText className="h-4 w-4" />
                                                <span>{paper.framework}</span>
                                                <span className="text-muted-foreground/60">•</span>
                                                <span>{paper.size}</span>
                                                <span className="text-muted-foreground/60">•</span>
                                                <span>{paper.pages}</span>
                                            </div>

                                            {/* Description */}
                                            <p className="text-sm text-muted-foreground">{paper.description}</p>

                                            {/* Topics */}
                                            <div className="space-y-2">
                                                <div className="text-xs font-semibold text-muted-foreground uppercase">Key Topics:</div>
                                                {paper.topics.map((topic, idx) => (
                                                    <div key={idx} className="flex items-start gap-2 text-sm">
                                                        <CheckCircle className="h-4 w-4 text-emerald-600 mt-0.5 flex-shrink-0" />
                                                        <span>{topic}</span>
                                                    </div>
                                                ))}
                                            </div>

                                            {/* CTA */}
                                            {paper.status === 'available' ? (
                                                <Link href={`/verticals/${paper.id}/whitepaper`}>
                                                    <Button className="w-full" variant="default">
                                                        <Download className="mr-2 h-4 w-4" />
                                                        Download White Paper
                                                    </Button>
                                                </Link>
                                            ) : (
                                                <Link href="/waitlist">
                                                    <Button className="w-full" variant="outline">
                                                        Request Priority Access
                                                    </Button>
                                                </Link>
                                            )}
                                        </div>
                                    </CardContent>
                                </Card>
                            );
                        })}
                    </div>
                </div>
            </section>

            {/* CTA Section */}
            <section className="py-16 px-4">
                <div className="max-w-4xl mx-auto">
                    <Card className="bg-gradient-to-r from-emerald-600 to-teal-600 text-white border-0">
                        <CardContent className="pt-6">
                            <div className="text-center space-y-4">
                                <h2 className="text-3xl font-bold">Need a Custom White Paper?</h2>
                                <p className="text-emerald-50 max-w-2xl mx-auto">
                                    Looking for a white paper tailored to your specific compliance requirements?
                                    Our team can create custom compliance documentation for your organization.
                                </p>
                                <div className="flex justify-center gap-4 pt-4">
                                    <Link href="/contact">
                                        <Button size="lg" variant="secondary">
                                            Contact Sales
                                            <ArrowRight className="ml-2 h-4 w-4" />
                                        </Button>
                                    </Link>
                                    <Link href="/resources/calculators">
                                        <Button size="lg" variant="outline" className="border-white text-white hover:bg-white/10">
                                            View ROI Calculators
                                        </Button>
                                    </Link>
                                </div>
                            </div>
                        </CardContent>
                    </Card>
                </div>
            </section>        </div>
    );
}
