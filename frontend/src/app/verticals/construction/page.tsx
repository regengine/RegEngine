'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Building2, CheckCircle, Code, Book } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { constructionIndustryData, constructionApiEndpoints, constructionSdkExamples } from './data';

export default function ConstructionDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
                {/* Hero Section */}
                <div className="relative overflow-hidden bg-gradient-to-r from-amber-600 to-orange-700 dark:from-amber-900 dark:to-orange-950">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-amber-500/20 rounded-full">
                                <Building2 className="h-5 w-5 text-amber-200" />
                                <span className="text-sm font-medium text-amber-100">Construction Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
                                The API for<br />
                                <span className="text-amber-200">BIM \u0026 Construction Safety</span>
                            </h1>

                            <p className="text-xl text-amber-100 mb-8 max-w-2xl mx-auto">
                                ISO 19650 BIM change tracking. Immutable safety records. OSHA-ready.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-amber-700 rounded-lg font-semibold hover:bg-amber-50 transition-colors inline-flex items-center justify-center gap-2"
                                >
                                    <Code className="h-5 w-5" />
                                    Get API Key
                                </Link>
                                <Link
                                    href="/docs/construction"
                                    className="px-8 py-4 bg-amber-500/20 text-white rounded-lg font-semibold hover:bg-amber-500/30 transition-colors inline-flex items-center justify-center gap-2 border border-white/20"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex items-center gap-6 text-sm text-amber-200">
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    4 ISO standards, 1 API
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    BIM change logs
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    OSHA compliance
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
                <VerticalTabs activeTab={activeTab} onTabChange={setActiveTab} colorScheme="amber" />

                {/* Tab Content */}
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    {activeTab === 'overview' && (
                        <IndustryOverviewSection
                            industry={constructionIndustryData.industry}
                            industryDescription={constructionIndustryData.description}
                            regulations={constructionIndustryData.regulations}
                            challenges={constructionIndustryData.challenges}
                            marketplaceSolutions={constructionIndustryData.marketplaceSolutions}
                            ourApproach={constructionIndustryData.ourApproach}
                            icon={Building2}
                        />
                    )}

                    {activeTab === 'api' && (
                        <ApiReferenceSection
                            vertical="Construction"
                            baseUrl="https://api.regengine.co/v1/construction"
                            endpoints={constructionApiEndpoints}
                            sdkExamples={constructionSdkExamples}
                            colorScheme="amber"
                        />
                    )}

                    {activeTab === 'quickstart' && (
                        <div className="space-y-8">
                            <div>
                                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                                    5-Minute Quickstart
                                </h2>
                                <p className="text-lg text-gray-700 dark:text-gray-300 mb-8">
                                    Record BIM changes and safety inspections with cryptographic verification.
                                </p>
                            </div>

                            {/* Step 1 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
                                    Step 1: Get Your API Key
                                </h3>
                                <p className="text-gray-700 dark:text-gray-300">
                                    Visit the{' '}
                                    <Link href="/api-keys" className="text-amber-700 dark:text-amber-400 hover:underline">
                                        API Keys page
                                    </Link>{' '}
                                    to generate your free API key.
                                </p>
                            </div>

                            {/* Step 2 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
                                    Step 2: Install the SDK
                                </h3>
                                <div className="bg-gray-900 rounded-lg p-4">
                                    <code className="text-sm text-green-400 font-mono">
                                        $ npm install @regengine/construction-sdk
                                    </code>
                                </div>
                            </div>

                            {/* Step 3 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
                                    Step 3: Record BIM Change
                                </h3>
                                <CodePlayground
                                    title="Try It Live"
                                    description="Track ISO 19650 BIM design changes"
                                    initialCode={`import { ConstructionCompliance } from '@regengine/construction-sdk';

const construction = new ConstructionCompliance('rge_your_api_key_here');

// Record BIM design change per ISO 19650
const change = await construction.bim.recordChange({
  project_id: 'PROJ-2024-001',
  rfi_number: 'RFI-456',
  change_description: 'Structural steel beam revised from W12x40 to W12x45',
  affected_models: ['STRUCT-L3-REV-D', 'ARCH-L3-REV-C'],
  requested_by: 'Structural Engineer - A. Chen',
  approved_by: 'Project Manager - K. Davis',
  approval_date: new Date().toISOString(),
  iso19650_workflow_stage: 'COORDINATION',
  cde_container: 'WIP'
});

console.log('✅ BIM change sealed:', change.change_id);
console.log('🔒 Content hash:', change.contentHash);
console.log('📋 ISO 19650 compliant:', change.iso19650_compliant);`}
                                    language="typescript"
                                    height="500px"
                                />
                            </div>

                            {/* Next Steps */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
                                    Next Steps
                                </h3>
                                <ul className="space-y-2 text-gray-700 dark:text-gray-300">
                                    <li>• Create quad-certification snapshots (ISO 9001 + 14001 + 45001 + 19650)</li>
                                    <li>• Record daily toolbox talks with attendee verification</li>
                                    <li>• Track safety inspections with OSHA 1926 compliance</li>
                                    <li>• Monitor subcontractor ISO certifications and insurance</li>
                                </ul>
                            </div>
                        </div>
                    )}

                    {activeTab === 'examples' && (
                        <div className="space-y-12">
                            <div>
                                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                                    Code Examples
                                </h2>
                                <p className="text-lg text-gray-700 dark:text-gray-300">
                                    Real-world examples for construction compliance.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link
                                    href="/docs/construction/bim"
                                    className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700"
                                >
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        BIM Change Tracking
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        ISO 19650 RFI and design changes
                                    </p>
                                </Link>

                                <Link
                                    href="/docs/construction/safety"
                                    className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700"
                                >
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Safety Inspections
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        OSHA 1926 compliant documentation
                                    </p>
                                </Link>

                                <Link
                                    href="/docs/construction/toolbox"
                                    className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700"
                                >
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Toolbox Talks
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Daily safety meetings with signatures
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* CTA Section */}
                <div className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="bg-gradient-to-r from-amber-600 to-orange-700 rounded-2xl p-12 text-center">
                            <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                            <p className="text-xl text-amber-100 mb-8">
                                Get your API key and record your first BIM change in under 5 minutes.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-amber-700 rounded-lg font-semibold hover:bg-amber-50 transition-colors"
                                >
                                    Get Free API Key
                                </Link>
                                <Link
                                    href="/verticals/construction/pricing"
                                    className="px-8 py-4 bg-amber-500/20 text-white rounded-lg font-semibold hover:bg-amber-500/30 transition-colors border border-white/20"
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
