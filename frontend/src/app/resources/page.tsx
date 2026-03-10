import { Metadata } from 'next';
import Link from 'next/link';
import { FileText, Calculator, DollarSign, Download, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

export const metadata: Metadata = {
    title: 'FSMA 204 Resources | RegEngine',
    description: 'FSMA 204 white papers, implementation guides, and pricing resources for food safety teams.',
};

export default function ResourcesPage() {
    return (
        <div className="min-h-screen flex flex-col">
            <main className="flex-1">
                <div className="bg-gradient-to-br from-emerald-50 via-teal-50 to-blue-50 border-b">
                    <div className="max-w-6xl mx-auto px-4 py-16">
                        <h1 className="text-5xl font-bold text-gray-900 mb-4">
                            FSMA 204 Resource Center
                        </h1>
                        <p className="text-xl text-gray-600 mb-8 max-w-3xl">
                            Practical resources for food safety teams preparing for traceability requirements and recall readiness.
                        </p>
                        <div className="flex gap-4 items-center flex-wrap">
                            <div className="flex gap-2 text-sm text-gray-600">
                                <FileText className="h-5 w-5 text-emerald-600" />
                                <span>FSMA white paper</span>
                            </div>
                            <div className="flex gap-2 text-sm text-gray-600">
                                <Calculator className="h-5 w-5 text-blue-600" />
                                <span>Recall readiness calculators</span>
                            </div>
                            <div className="flex gap-2 text-sm text-gray-600">
                                <DollarSign className="h-5 w-5 text-purple-600" />
                                <span>Revenue-tier pricing</span>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="max-w-6xl mx-auto px-4 pt-12">
                    <div className="grid md:grid-cols-3 gap-4">
                        <Link
                            href="/resources/guides"
                            className="rounded-lg border bg-white p-5 hover:shadow-sm transition-shadow"
                        >
                            <p className="text-sm font-semibold text-gray-900">Implementation Guides</p>
                            <p className="text-sm text-gray-600 mt-1">
                                Step-by-step FSMA rollout checklists and onboarding guidance.
                            </p>
                        </Link>
                        <Link
                            href="/resources/whitepapers"
                            className="rounded-lg border bg-white p-5 hover:shadow-sm transition-shadow"
                        >
                            <p className="text-sm font-semibold text-gray-900">FSMA White Paper</p>
                            <p className="text-sm text-gray-600 mt-1">
                                Traceability implementation and compliance-ready architecture overview.
                            </p>
                        </Link>
                        <Link
                            href="/resources/calculators"
                            className="rounded-lg border bg-white p-5 hover:shadow-sm transition-shadow"
                        >
                            <p className="text-sm font-semibold text-gray-900">ROI Calculator</p>
                            <p className="text-sm text-gray-600 mt-1">
                                Estimate savings from faster response time and reduced audit prep overhead.
                            </p>
                        </Link>
                    </div>
                </div>

                <div className="bg-gray-50 border-y mt-12">
                    <div className="max-w-6xl mx-auto px-4 py-16">
                        <div className="text-center mb-12">
                            <h2 className="text-3xl font-bold text-gray-900 mb-4">Download FSMA Materials</h2>
                            <p className="text-lg text-gray-600 max-w-2xl mx-auto">
                                Get the latest white paper and implementation references for your internal planning.
                            </p>
                        </div>

                        <div className="grid md:grid-cols-3 gap-6">
                            <div className="bg-white border rounded-lg p-6 text-center">
                                <FileText className="h-12 w-12 text-emerald-600 mx-auto mb-4" />
                                <h3 className="text-lg font-bold mb-2">FSMA White Paper</h3>
                                <p className="text-sm text-gray-600 mb-4">Architecture, implementation patterns, and operational outcomes.</p>
                                <Link href="/resources/whitepapers">
                                    <Button variant="outline" className="w-full">
                                        <Download className="h-4 w-4 mr-2" />
                                        View White Paper
                                    </Button>
                                </Link>
                            </div>

                            <div className="bg-white border rounded-lg p-6 text-center">
                                <Calculator className="h-12 w-12 text-blue-600 mx-auto mb-4" />
                                <h3 className="text-lg font-bold mb-2">ROI Calculators</h3>
                                <p className="text-sm text-gray-600 mb-4">Model recall and compliance efficiency improvements.</p>
                                <Link href="/resources/calculators">
                                    <Button variant="outline" className="w-full">
                                        <ArrowRight className="h-4 w-4 mr-2" />
                                        Open Calculators
                                    </Button>
                                </Link>
                            </div>

                            <div className="bg-white border rounded-lg p-6 text-center">
                                <DollarSign className="h-12 w-12 text-purple-600 mx-auto mb-4" />
                                <h3 className="text-lg font-bold mb-2">Pricing Guide</h3>
                                <p className="text-sm text-gray-600 mb-4">Growth, Scale, and Enterprise plan details.</p>
                                <Link href="/pricing">
                                    <Button variant="outline" className="w-full">
                                        <ArrowRight className="h-4 w-4 mr-2" />
                                        View Pricing
                                    </Button>
                                </Link>
                            </div>
                        </div>
                    </div>
                </div>

                <div className="max-w-4xl mx-auto px-4 py-16 text-center">
                    <h2 className="text-3xl font-bold text-gray-900 mb-4">
                        Need a FSMA Gap Review?
                    </h2>
                    <p className="text-lg text-gray-600 mb-8">
                        Schedule a walkthrough to benchmark your current traceability workflow.
                    </p>
                    <div className="flex gap-4 justify-center">
                        <a href="mailto:sales@regengine.co?subject=Schedule FSMA Demo&body=Hi, I'd like to schedule an FSMA 204 walkthrough.">
                            <Button size="lg" className="bg-emerald-600 hover:bg-emerald-700">
                                Schedule Demo
                            </Button>
                        </a>
                        <Link href="/tools">
                            <Button size="lg" variant="outline">
                                Try Free Tools
                            </Button>
                        </Link>
                    </div>
                </div>
            </main>
        </div>
    );
}
