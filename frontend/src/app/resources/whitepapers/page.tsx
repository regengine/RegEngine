'use client';

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Download, FileText, Filter } from 'lucide-react';
import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue,
} from '@/components/ui/select';

interface WhitePaper {
    id: string;
    title: string;
    vertical: string;
    verticalSlug: string;
    regulation: string;
    description: string;
    roi: string;
    primaryValue: string;
    pages: number;
}

const whitePapers: WhitePaper[] = [
    {
        id: 'finance-sox',
        title: 'Automating SOX/SEC Compliance',
        vertical: 'Finance',
        verticalSlug: 'finance',
        regulation: 'SOX 404, SOX 302, SEC Regulation S-K',
        description: 'Transform SOX 404 compliance from a cost center into a revenue accelerator with tamper-evident evidence chains and instant enterprise sales proof.',
        roi: '200%+ annual return',
        primaryValue: 'Sales velocity ($5M+/year revenue acceleration)',
        pages: 35,
    },
    {
        id: 'healthcare-hipaa',
        title: 'Automating HIPAA/HITECH Compliance',
        vertical: 'Healthcare',
        verticalSlug: 'healthcare',
        regulation: 'HIPAA Security Rule, HITECH Act, State Breach Laws',
        description: 'Prevent breaches with continuous PHI access monitoring backed by cryptographically sealed audit trails that withstand OCR examination.',
        roi: '175%+ annual return',
        primaryValue: 'Breach prevention ($4M+ avoided penalties)',
        pages: 37,
    },
    {
        id: 'energy-nerc',
        title: 'Automating NERC CIP Compliance',
        vertical: 'Energy',
        verticalSlug: 'energy',
        regulation: 'NERC CIP-013, CIP-010, CIP-007, CIP-005',
        description: 'Eliminate $1M/day FERC penalty exposure with real-time BES Cyber System monitoring and automated CIP-013 supply chain verification.',
        roi: '250%+ annual return',
        primaryValue: 'Penalty avoidance ($12M+ FERC violations prevented)',
        pages: 38,
    },
    {
        id: 'nuclear-10cfr',
        title: 'Automating 10 CFR Part 21 & Appendix B QA',
        vertical: 'Nuclear',
        verticalSlug: 'nuclear',
        regulation: '10 CFR Part 21, 10 CFR Part 50 Appendix B',
        description: 'Prevent forced shutdowns with tamper-evident Part 21 evidence chains and real-time common cause failure detection.',
        roi: '300%+ annual return',
        primaryValue: 'Operational continuity ($24M shutdown prevention)',
        pages: 39,
    },
];

export default function WhitePapersPage() {
    const [selectedVertical, setSelectedVertical] = useState<string>('all');

    const filteredPapers = selectedVertical === 'all'
        ? whitePapers
        : whitePapers.filter(paper => paper.vertical === selectedVertical);

    const verticals = ['all', ...Array.from(new Set(whitePapers.map(p => p.vertical)))];

    return (
        <div className="min-h-screen bg-gray-50">
            <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                {/* Hero Section */}
                <div className="text-center mb-12">
                    <Badge className="mb-4">Sales Resources</Badge>
                    <h1 className="text-4xl font-bold text-gray-900 mb-4">
                        Competitive White Papers
                    </h1>
                    <p className="text-xl text-gray-600 max-w-3xl mx-auto">
                        Executive positioning materials for CFO, CISO, and compliance decision-makers.
                        Each white paper quantifies ROI from tamper-evident evidence architecture.
                    </p>
                </div>

                {/* Filter Section */}
                <div className="mb-8 flex items-center justify-between">
                    <div className="flex items-center gap-2">
                        <Filter className="h-5 w-5 text-gray-500" />
                        <span className="text-sm font-medium text-gray-700">Filter by vertical:</span>
                        <Select value={selectedVertical} onValueChange={setSelectedVertical}>
                            <SelectTrigger className="w-[180px]">
                                <SelectValue placeholder="All Verticals" />
                            </SelectTrigger>
                            <SelectContent>
                                {verticals.map(vertical => (
                                    <SelectItem key={vertical} value={vertical}>
                                        {vertical === 'all' ? 'All Verticals' : vertical}
                                    </SelectItem>
                                ))}
                            </SelectContent>
                        </Select>
                    </div>

                    <div className="text-sm text-gray-500">
                        {filteredPapers.length} white paper{filteredPapers.length !== 1 ? 's' : ''} available
                    </div>
                </div>

                {/* White Papers Grid */}
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                    {filteredPapers.map(paper => (
                        <Card key={paper.id} className="flex flex-col hover:shadow-lg transition-shadow">
                            <CardHeader>
                                <div className="flex items-start justify-between mb-2">
                                    <Badge variant="outline" className="text-blue-600 border-blue-600">
                                        {paper.vertical}
                                    </Badge>
                                    <div className="text-xs text-gray-500">
                                        {paper.pages} pages
                                    </div>
                                </div>
                                <CardTitle className="text-2xl">{paper.title}</CardTitle>
                                <CardDescription className="text-sm text-gray-500">
                                    {paper.regulation}
                                </CardDescription>
                            </CardHeader>

                            <CardContent className="flex-grow">
                                <p className="text-gray-700 mb-4">
                                    {paper.description}
                                </p>

                                <div className="space-y-2 text-sm">
                                    <div className="flex items-start gap-2">
                                        <span className="font-semibold text-gray-900 min-w-[80px]">ROI:</span>
                                        <span className="text-gray-700">{paper.roi}</span>
                                    </div>
                                    <div className="flex items-start gap-2">
                                        <span className="font-semibold text-gray-900 min-w-[80px]">Primary Value:</span>
                                        <span className="text-gray-700">{paper.primaryValue}</span>
                                    </div>
                                </div>
                            </CardContent>

                            <CardFooter className="flex gap-3">
                                <Button
                                    variant="default"
                                    className="flex-1"
                                    onClick={() => window.location.href = `/verticals/${paper.verticalSlug}/whitepaper`}
                                >
                                    <FileText className="mr-2 h-4 w-4" />
                                    View White Paper
                                </Button>
                                <Button
                                    variant="outline"
                                    onClick={() => window.location.href = `/verticals/${paper.verticalSlug}/calculator`}
                                >
                                    <Download className="mr-2 h-4 w-4" />
                                    ROI Calculator
                                </Button>
                            </CardFooter>
                        </Card>
                    ))}
                </div>

                {/* CTA Section */}
                <div className="mt-16 bg-blue-50 border border-blue-100 rounded-lg p-8 text-center">
                    <h2 className="text-2xl font-bold text-gray-900 mb-4">
                        Need a Custom White Paper?
                    </h2>
                    <p className="text-gray-700 mb-6 max-w-2xl mx-auto">
                        We can generate industry-specific white papers for your vertical with custom ROI models,
                        competitive positioning, and regulatory focus.
                    </p>
                    <div className="flex gap-4 justify-center">
                        <Button size="lg" onClick={() => window.location.href = 'mailto:sales@regengine.co'}>
                            Contact Sales
                        </Button>
                        <Button size="lg" variant="outline" onClick={() => window.location.href = '/demo'}>
                            Schedule Demo
                        </Button>
                    </div>
                </div>

                {/* What's Included Section */}
                <div className="mt-16">
                    <h2 className="text-2xl font-bold text-gray-900 mb-6 text-center">
                        What's Included in Each White Paper
                    </h2>
                    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg">Executive Summary</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ul className="space-y-2 text-sm text-gray-700">
                                    <li>• TL;DR for decision-makers</li>
                                    <li>• Quantified pain points</li>
                                    <li>• Business outcomes table</li>
                                    <li>• ROI summary with payback period</li>
                                </ul>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg">Technical Deep Dive</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ul className="space-y-2 text-sm text-gray-700">
                                    <li>• Tamper-evident architecture</li>
                                    <li>• Cryptographic proof examples</li>
                                    <li>• Integration requirements</li>
                                    <li>• Trust model transparency</li>
                                </ul>
                            </CardContent>
                        </Card>

                        <Card>
                            <CardHeader>
                                <CardTitle className="text-lg">Business Case</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <ul className="space-y-2 text-sm text-gray-700">
                                    <li>• Cost-benefit analysis</li>
                                    <li>• Competitive comparison table</li>
                                    <li>• Implementation methodology</li>
                                </ul>
                            </CardContent>
                        </Card>
                    </div>
                </div>
            </main>        </div>
    );
}
