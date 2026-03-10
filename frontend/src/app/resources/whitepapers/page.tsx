'use client';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Download, FileText } from 'lucide-react';

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
        id: 'fsma-204-traceability',
        title: 'FSMA 204 Traceability Implementation Guide',
        vertical: 'Food Safety',
        verticalSlug: 'food-safety',
        regulation: 'FSMA 204 / 21 CFR Part 1 Subpart S',
        description: 'A practical implementation guide for CTE/KDE capture, traceability queries, and FDA-ready exports.',
        roi: '42-minute simulated recall response',
        primaryValue: '24-hour FDA request readiness',
        pages: 28,
    },
];

export default function WhitePapersPage() {
    const paper = whitePapers[0];

    return (
        <div className="min-h-screen bg-gray-50">
            <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                <div className="text-center mb-12">
                    <Badge className="mb-4">FSMA 204 Resource</Badge>
                    <h1 className="text-4xl font-bold text-gray-900 mb-4">
                        FSMA 204 White Paper
                    </h1>
                    <p className="text-xl text-gray-600 max-w-3xl mx-auto">
                        Implementation material for food safety and compliance teams preparing for traceability enforcement.
                    </p>
                </div>

                <Card className="max-w-3xl mx-auto flex flex-col hover:shadow-lg transition-shadow">
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
                                <span className="font-semibold text-gray-900 min-w-[96px]">Outcome:</span>
                                <span className="text-gray-700">{paper.roi}</span>
                            </div>
                            <div className="flex items-start gap-2">
                                <span className="font-semibold text-gray-900 min-w-[96px]">Primary Value:</span>
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
                            onClick={() => window.location.href = '/tools'}
                        >
                            <Download className="mr-2 h-4 w-4" />
                            Open Free Tools
                        </Button>
                    </CardFooter>
                </Card>
            </main>
        </div>
    );
}
