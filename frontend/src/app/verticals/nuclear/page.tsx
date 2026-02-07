'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Atom, Shield, Lock, CheckCircle, Code, Book, FileText, Download } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { nuclearIndustryData, nuclearApiEndpoints, nuclearSdkExamples } from './data';

export default function NuclearDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
                {/* Hero Section */}
                <div className="relative overflow-hidden bg-gradient-to-r from-orange-600 to-red-700 dark:from-orange-900 dark:to-red-900">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-orange-500/20 rounded-full">
                                <Atom className="h-5 w-5 text-orange-200" />
                                <span className="text-sm font-medium text-orange-100">Nuclear Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
                                The API for<br />
                                <span className="text-orange-200">Nuclear Compliance</span>
                            </h1>

                            <p className="text-xl text-orange-100 mb-8 max-w-2xl mx-auto">
                                First NRC-compliant evidence record in 5 minutes. Not 5 weeks.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-orange-600 rounded-lg font-semibold hover:bg-orange-50 transition-colors inline-flex items-center justify-center gap-2"
                                >
                                    <Code className="h-5 w-5" />
                                    Get API Key
                                </Link>
                                <Link
                                    href="/docs/nuclear"
                                    className="px-8 py-4 bg-orange-500/20 text-white rounded-lg font-semibold hover:bg-orange-500/30 transition-colors inline-flex items-center justify-center gap-2 border border-white/20"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex items-center gap-6 text-sm text-orange-200">
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    5-min quickstart
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    SDKs for Node, Python, Go
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    10 CFR compliant
                                </span>
                            </div>
                        </div>
                    </div>

                    {/* Wave decoration */}
                    <div className="absolute bottom-0 left-0 right-0">
                        <svg viewBox="0 0 1440 120" fill="none" xmlns="http://www.w3.org/2000/svg">
                            <path d="M0 120L60 110C120 100 240 80 360 70C480 60 600 60 720 65C840 70 960 80 1080 85C1200 90 1320 90 1380 90L1440 90V120H1380C1320 120 1200 120 1080 120C960 120 840 120 720 120C600 120 480 120 360 120C240 120 120 120 60 120H0Z" fill="currentColor" className="text-gray-50 dark:text-gray-900" />
                        </svg>
                    </div>
                </div>

                {/* Tabs Navigation */}
                <VerticalTabs activeTab={activeTab} onTabChange={setActiveTab} colorScheme="orange" />

                {/* Tab Content */}
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    {activeTab === 'overview' && (
                        <IndustryOverviewSection
                            industry={nuclearIndustryData.industry}
                            industryDescription={nuclearIndustryData.description}
                            regulations={nuclearIndustryData.regulations}
                            challenges={nuclearIndustryData.challenges}
                            marketplaceSolutions={nuclearIndustryData.marketplaceSolutions}
                            ourApproach={nuclearIndustryData.ourApproach}
                            icon={Atom}
                        />
                    )}

                    {activeTab === 'api' && (
                        <ApiReferenceSection
                            vertical="Nuclear"
                            baseUrl="https://api.regengine.co/v1/nuclear"
                            endpoints={nuclearApiEndpoints}
                            sdkExamples={nuclearSdkExamples}
                            colorScheme="orange"
                        />
                    )}

                    {activeTab === 'quickstart' && (
                        <div className="space-y-8">
                            <div>
                                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                                    5-Minute Quickstart
                                </h2>
                                <p className="text-lg text-gray-700 dark:text-gray-300 mb-8">
                                    Create your first NRC-compliant, immutable record in under 5 minutes.
                                </p>
                            </div>

                            <CodePlayground
                                title="Try It Live - Nuclear Record Creation"
                                description="Edit and run this code to create an immutable NRC-compliant record"
                                initialCode={`// Nuclear SDK Quickstart
const facilities = [
  { id: 'NPP-UNIT-1', name: 'Unit 1', docket: '50-12345' },
  { id: 'NPP-UNIT-2', name: 'Unit 2', docket: '50-12346' }
];

console.log('🏭 Nuclear Facilities:');
facilities.forEach(f => {
  console.log(\`  \${f.name} (Docket: \${f.docket})\`);
});

// Simulate record creation
const record = {
  id: 'rec_0193abc...',
  facilityId: facilities[0].id,
  recordType: 'CYBER_SECURITY_PLAN',
  integrity: {
    sealed: true,
    contentHash: 'sha256:abc123...',
    chainStatus: 'valid'
  },
  createdAt: new Date().toISOString()
};

console.log('\\n✅ Record created:');
console.log('  ID:', record.id);
console.log('  Sealed:', record.integrity.sealed);
console.log('  Hash:', record.integrity.contentHash);
console.log('  Chain:', record.integrity.chainStatus);`}
                                language="javascript"
                                height="500px"
                            />
                        </div>
                    )}

                    {activeTab === 'examples' && (
                        <div className="space-y-12">
                            <div>
                                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                                    Code Examples
                                </h2>
                                <p className="text-lg text-gray-700 dark:text-gray-300">
                                    Real-world examples for nuclear compliance workflows.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link href="/docs/nuclear/quickstart" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Quickstart (5 minutes)
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Create your first NRC-compliant record
                                    </p>
                                </Link>

                                <Link href="/docs/nuclear/inspection" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        NRC Inspection Readiness
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Cryptographically prove record integrity
                                    </p>
                                </Link>

                                <Link href="/docs/nuclear/legal-hold" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Legal Hold & Discovery
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Preserve evidence for enforcement actions
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* White Paper Download Section */}
                <div className="bg-orange-50 dark:bg-orange-900/10 border-y border-orange-100 dark:border-orange-900/30 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-4xl mx-auto">
                            <div className="flex items-start gap-6">
                                <div className="flex-shrink-0">
                                    <div className="w-16 h-16 bg-orange-100 dark:bg-orange-900/30 rounded-lg flex items-center justify-center">
                                        <FileText className="h-8 w-8 text-orange-600 dark:text-orange-400" />
                                    </div>
                                </div>
                                <div className="flex-1">
                                    <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-3">
                                        Nuclear Compliance White Paper
                                    </h2>
                                    <p className="text-gray-700 dark:text-gray-300 mb-4">
                                        <strong>Automating 10 CFR Part 21 & Appendix B QA with Tamper-Evident Documentation</strong>
                                    </p>
                                    <p className="text-gray-600 dark:text-gray-400 mb-4 text-sm">
                                        39-page executive white paper quantifying how tamper-evident Part 21 evidence chains prevent forced shutdowns ($24M per 12-day event) and accelerate license amendments (36 months → 14 months). Includes customer success story from 1,100 MWe PWR achieving 300%+ ROI.
                                    </p>
                                    <div className="flex flex-wrap gap-3">
                                        <Link
                                            href="/resources/whitepapers"
                                            className="inline-flex items-center gap-2 px-6 py-3 bg-orange-600 hover:bg-orange-700 text-white rounded-lg font-semibold transition-colors"
                                        >
                                            <Download className="h-4 w-4" />
                                            Download White Paper
                                        </Link>
                                        <Link
                                            href="/resources/whitepapers"
                                            className="inline-flex items-center gap-2 px-6 py-3 bg-white dark:bg-gray-800 hover:bg-gray-50 dark:hover:bg-gray-700 text-gray-700 dark:text-gray-300 rounded-lg font-semibold transition-colors border border-gray-300 dark:border-gray-600"
                                        >
                                            <FileText className="h-4 w-4" />
                                            View All White Papers
                                        </Link>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                {/* CTA Section */}
                <div className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="bg-gradient-to-r from-orange-600 to-red-600 rounded-2xl p-12 text-center">
                            <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                            <p className="text-xl text-orange-100 mb-8">
                                Get your API key and create your first NRC-compliant record in under 5 minutes.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-orange-600 rounded-lg font-semibold hover:bg-orange-50 transition-colors"
                                >
                                    Get Free API Key
                                </Link>
                                <Link
                                    href="/verticals/nuclear/pricing"
                                    className="px-8 py-4 bg-orange-500/20 text-white rounded-lg font-semibold hover:bg-orange-500/30 transition-colors border border-white/20"
                                >
                                    View Pricing
                                </Link>
                            </div>
                        </div>
                    </div>
                </div>
            </div>        </>
    );
}
