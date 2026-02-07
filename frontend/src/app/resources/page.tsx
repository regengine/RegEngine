import { Metadata } from 'next';
import Link from 'next/link';
import { FileText, Calculator, DollarSign, Download, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

export const metadata: Metadata = {
    title: 'Sales Enablement Resources | RegEngine',
    description: 'White papers, TCO calculators, and pricing information for all 10 RegEngine verticals.',
};

const verticals = [
    { id: 'gaming', name: 'Gaming', description: 'ESRB, PEGI & COPPA Compliance', roi: '$161K/year', payback: '18.6 mo' },
    { id: 'automotive', name: 'Automotive', description: 'IATF 16949 & PPAP Tracking', roi: '$122.5K/year', payback: '24.5 mo' },
    { id: 'aerospace', name: 'Aerospace', description: 'AS9100 & NADCAP Evidence', roi: '$136K/year', payback: '30.8 mo' },
    { id: 'manufacturing', name: 'Manufacturing', description: 'ISO 9001/14001/45001 Triple-Cert', roi: '$197K/year', payback: '9.1 mo' },
    { id: 'construction', name: 'Construction', description: 'ISO 19650 & OSHA 1926', roi: '$437K/year', payback: '4.1 mo' },
    { id: 'energy', name: 'Energy', description: 'NERC CIP & Grid Security', roi: '$286K/year', payback: '12.6 mo' },
    { id: 'nuclear', name: 'Nuclear', description: 'NRC 10 CFR Compliance', roi: 'License Protection', payback: 'Regulatory' },
    { id: 'finance', name: 'Finance', description: 'SOX, GLBA & Dodd-Frank', roi: '$165K/year', payback: '72.7 mo' },
    { id: 'healthcare', name: 'Healthcare', description: 'HIPAA & Patient Privacy', roi: '$241K/year', payback: '9.9 mo' },
    { id: 'technology', name: 'Technology', description: 'SOC 2 & ISO 27001', roi: '$436K/year', payback: '3.3 mo' },
];

export default function ResourcesPage() {
    return (
        <div className="min-h-screen flex flex-col">
            <main className="flex-1">
                {/* Hero Section */}
                <div className="bg-gradient-to-br from-emerald-50 via-teal-50 to-blue-50 border-b">
                    <div className="max-w-6xl mx-auto px-4 py-16">
                        <h1 className="text-5xl font-bold text-gray-900 mb-4">
                            Sales Enablement Resources
                        </h1>
                        <p className="text-xl text-gray-600 mb-8 max-w-3xl">
                            Comprehensive white papers, ROI calculators, and pricing information for all 10 RegEngine industry verticals.
                        </p>
                        <div className="flex gap-4 items-center">
                            <div className="flex gap-2 text-sm text-gray-600">
                                <FileText className="h-5 w-5 text-emerald-600" />
                                <span>10 White Papers</span>
                            </div>
                            <div className="flex gap-2 text-sm text-gray-600">
                                <Calculator className="h-5 w-5 text-blue-600" />
                                <span>10 TCO Calculators</span>
                            </div>
                            <div className="flex gap-2 text-sm text-gray-600">
                                <DollarSign className="h-5 w-5 text-purple-600" />
                                <span>Unified Pricing</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Verticals Grid */}
                <div className="max-w-6xl mx-auto px-4 py-16">
                    <h2 className="text-3xl font-bold text-gray-900 mb-8">Industry Verticals</h2>
                    <div className="grid md:grid-cols-2 gap-6">
                        {verticals.map((vertical) => (
                            <div
                                key={vertical.id}
                                className="border rounded-lg p-6 hover:shadow-lg transition-shadow bg-white"
                            >
                                <div className="flex justify-between items-start mb-4">
                                    <div>
                                        <h3 className="text-xl font-bold text-gray-900 mb-1">{vertical.name}</h3>
                                        <p className="text-sm text-gray-600">{vertical.description}</p>
                                    </div>
                                    <div className="text-right">
                                        <p className="text-sm text-gray-500">Annual Savings</p>
                                        <p className="text-lg font-bold text-emerald-600">{vertical.roi}</p>
                                        <p className="text-xs text-gray-500">Payback: {vertical.payback}</p>
                                    </div>
                                </div>

                                <div className="flex gap-2">
                                    <Link href={`/verticals/${vertical.id}/whitepaper`} className="flex-1">
                                        <Button variant="outline" className="w-full">
                                            <FileText className="h-4 w-4 mr-2" />
                                            White Paper
                                        </Button>
                                    </Link>
                                    <Link href={`/verticals/${vertical.id}/calculator`} className="flex-1">
                                        <Button variant="outline" className="w-full">
                                            <Calculator className="h-4 w-4 mr-2" />
                                            Calculator
                                        </Button>
                                    </Link>
                                    <Link href={`/verticals/${vertical.id}/pricing`}>
                                        <Button className="bg-emerald-600 hover:bg-emerald-700">
                                            <DollarSign className="h-4 w-4 mr-1" />
                                            Pricing
                                        </Button>
                                    </Link>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Download Section */}
                <div className="bg-gray-50 border-y">
                    <div className="max-w-6xl mx-auto px-4 py-16">
                        <div className="text-center mb-12">
                            <h2 className="text-3xl font-bold text-gray-900 mb-4">Download All Materials</h2>
                            <p className="text-lg text-gray-600 max-w-2xl mx-auto">
                                Get the complete sales enablement package with all white papers, calculators, and pricing guides.
                            </p>
                        </div>

                        <div className="grid md:grid-cols-3 gap-6">
                            <div className="bg-white border rounded-lg p-6 text-center">
                                <FileText className="h-12 w-12 text-emerald-600 mx-auto mb-4" />
                                <h3 className="text-lg font-bold mb-2">White Papers</h3>
                                <p className="text-sm text-gray-600 mb-4">Complete competitive analysis for all 10 verticals</p>
                                <a href="mailto:sales@regengine.co?subject=Request White Paper Bundle&body=Hi, I'd like to request the complete white paper bundle for all 10 verticals.">
                                    <Button variant="outline" className="w-full">
                                        <Download className="h-4 w-4 mr-2" />
                                        Download Bundle (PDF)
                                    </Button>
                                </a>
                            </div>

                            <div className="bg-white border rounded-lg p-6 text-center">
                                <Calculator className="h-12 w-12 text-blue-600 mx-auto mb-4" />
                                <h3 className="text-lg font-bold mb-2">TCO Calculators</h3>
                                <p className="text-sm text-gray-600 mb-4">ROI models with 3-year financial projections</p>
                                <a href="mailto:sales@regengine.co?subject=Request TCO Calculator Bundle&body=Hi, I'd like to request the complete TCO calculator bundle for all 10 verticals.">
                                    <Button variant="outline" className="w-full">
                                        <Download className="h-4 w-4 mr-2" />
                                        Download Bundle (Excel)
                                    </Button>
                                </a>
                            </div>

                            <div className="bg-white border rounded-lg p-6 text-center">
                                <DollarSign className="h-12 w-12 text-purple-600 mx-auto mb-4" />
                                <h3 className="text-lg font-bold mb-2">Pricing Guide</h3>
                                <p className="text-sm text-gray-600 mb-4">Tier definitions and service alignment</p>
                                <Link href="/pricing">
                                    <Button variant="outline" className="w-full">
                                        <ArrowRight className="h-4 w-4 mr-2" />
                                        View Interactive Pricing
                                    </Button>
                                </Link>
                            </div>
                        </div>
                    </div>
                </div>

                {/* CTA Section */}
                <div className="max-w-4xl mx-auto px-4 py-16 text-center">
                    <h2 className="text-3xl font-bold text-gray-900 mb-4">
                        Ready to See RegEngine in Action?
                    </h2>
                    <p className="text-lg text-gray-600 mb-8">
                        Schedule a demo to see how RegEngine can transform your compliance operations.
                    </p>
                    <div className="flex gap-4 justify-center">
                        <a href="mailto:sales@regengine.co?subject=Schedule Demo&body=Hi, I'd like to schedule a demo of RegEngine.">
                            <Button size="lg" className="bg-emerald-600 hover:bg-emerald-700">
                                Schedule Demo
                            </Button>
                        </a>
                        <Link href="/ftl-checker">
                            <Button size="lg" variant="outline">
                                Try Free Tool
                            </Button>
                        </Link>
                    </div>
                </div>
            </main>        </div>
    );
}
