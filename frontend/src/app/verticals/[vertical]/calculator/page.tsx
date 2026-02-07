import fs from 'fs';
import path from 'path';
import { notFound } from 'next/navigation';
import Link from 'next/link';
import { ArrowLeft, FileText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface CalculatorPageProps {
    params: {
        vertical: string;
    };
}

const verticalNames: Record<string, string> = {
    gaming: 'Gaming',
    automotive: 'Automotive',
    aerospace: 'Aerospace',
    manufacturing: 'Manufacturing',
    construction: 'Construction',
    energy: 'Energy',
    nuclear: 'Nuclear',
    finance: 'Finance',
    healthcare: 'Healthcare',
    technology: 'Technology',
};

export async function generateStaticParams() {
    return Object.keys(verticalNames).map((vertical) => ({
        vertical,
    }));
}

export async function generateMetadata({ params }: CalculatorPageProps) {
    const verticalName = verticalNames[params.vertical];
    return {
        title: `${verticalName} TCO Calculator | RegEngine`,
        description: `Calculate your 3-year ROI with RegEngine for ${verticalName} compliance.`,
    };
}

export default function CalculatorPage({ params }: CalculatorPageProps) {
    const { vertical } = params;
    const verticalName = verticalNames[vertical];

    if (!verticalName) {
        notFound();
    }

    // Read markdown file from sales_enablement directory
    const markdownPath = path.join(
        process.cwd(),
        '..',
        'sales_enablement',
        'calculators',
        `${vertical}_tco_calculator.md`
    );

    let content = '';
    try {
        content = fs.readFileSync(markdownPath, 'utf-8');
    } catch (error) {
        console.error(`Failed to load calculator for ${vertical}:`, error);
        content = `# Calculator Not Found\n\nThe TCO calculator for ${verticalName} is currently unavailable.`;
    }

    return (
        <div className="min-h-screen flex flex-col">
            <main className="flex-1">
                {/* Header Section */}
                <div className="bg-gradient-to-br from-blue-50 to-indigo-50 border-b">
                    <div className="max-w-4xl mx-auto px-4 py-12">
                        <Link
                            href={`/verticals/${vertical}`}
                            className="inline-flex items-center gap-2 text-blue-600 hover:text-blue-700 mb-6"
                        >
                            <ArrowLeft className="h-4 w-4" />
                            Back to {verticalName} Vertical
                        </Link>

                        <div className="flex items-start gap-4 mb-6">
                            <div className="flex-1">
                                <h1 className="text-4xl font-bold text-gray-900 mb-2">
                                    {verticalName} TCO Calculator
                                </h1>
                                <p className="text-xl text-gray-600">
                                    Calculate Your 3-Year ROI with RegEngine
                                </p>
                            </div>
                        </div>

                        <div className="flex gap-4">
                            <Link href={`/verticals/${vertical}/whitepaper`}>
                                <Button variant="outline">
                                    <FileText className="h-4 w-4 mr-2" />
                                    View White Paper
                                </Button>
                            </Link>
                            <Link href={`/verticals/${vertical}/pricing`}>
                                <Button className="bg-blue-600 hover:bg-blue-700">
                                    View Pricing
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>

                {/* Content Section */}
                <div className="max-w-4xl mx-auto px-4 py-12">
                    <article className="prose prose-lg prose-blue max-w-none">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {content}
                        </ReactMarkdown>
                    </article>

                    <div className="mt-12 p-8 bg-gradient-to-r from-blue-600 to-indigo-600 rounded-lg text-white">
                        <h3 className="text-2xl font-bold mb-2">Ready to See Your Savings?</h3>
                        <p className="mb-4">Contact our sales team for a customized ROI calculation based on your specific needs.</p>
                        <div className="flex gap-4">
                            <a href="mailto:sales@regengine.co?subject=Request Custom ROI Calculation&body=Hi, I'd like to request a customized ROI calculation for my organization.">
                                <Button className="bg-white text-blue-600 hover:bg-gray-100">
                                    Schedule Consultation
                                </Button>
                            </a>
                            <Link href={`/verticals/${vertical}/whitepaper`}>
                                <Button variant="outline" className="border-white text-white hover:bg-white/10">
                                    Read White Paper
                                </Button>
                            </Link>
                        </div>
                    </div>
                </div>
            </main>        </div>
    );
}
