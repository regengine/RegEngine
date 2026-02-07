'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Car, CheckCircle, Code, Book } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { automotiveIndustryData, automotiveApiEndpoints, automotiveSdkExamples } from './data';

export default function AutomotiveDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
                {/* Hero Section */}
                <div className="relative overflow-hidden bg-gradient-to-r from-red-600 to-orange-600 dark:from-red-900 dark:to-orange-900">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-red-500/20 rounded-full">
                                <Car className="h-5 w-5 text-red-200" />
                                <span className="text-sm font-medium text-red-100">Automotive Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
                                The API for<br />
                                <span className="text-red-200">IATF 16949 \u0026 PPAP</span>
                            </h1>

                            <p className="text-xl text-red-100 mb-8 max-w-2xl mx-auto">
                                Cryptographic PPAP packages. Immutable layered process audits. OEM-ready.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-red-600 rounded-lg font-semibold hover:bg-red-50 transition-colors inline-flex items-center justify-center gap-2"
                                >
                                    <Code className="h-5 w-5" />
                                    Get API Key
                                </Link>
                                <Link
                                    href="/docs/automotive"
                                    className="px-8 py-4 bg-red-500/20 text-white rounded-lg font-semibold hover:bg-red-500/30 transition-colors inline-flex items-center justify-center gap-2 border border-white/20"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex items-center gap-6 text-sm text-red-200">
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    18-element PPAP
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    LPA timestamps
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    Multi-OEM support
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
                <VerticalTabs activeTab={activeTab} onTabChange={setActiveTab} colorScheme="red" />

                {/* Tab Content */}
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    {activeTab === 'overview' && (
                        <IndustryOverviewSection
                            industry={automotiveIndustryData.industry}
                            industryDescription={automotiveIndustryData.description}
                            regulations={automotiveIndustryData.regulations}
                            challenges={automotiveIndustryData.challenges}
                            marketplaceSolutions={automotiveIndustryData.marketplaceSolutions}
                            ourApproach={automotiveIndustryData.ourApproach}
                            icon={Car}
                        />
                    )}

                    {activeTab === 'api' && (
                        <ApiReferenceSection
                            vertical="Automotive"
                            baseUrl="https://api.regengine.co/v1/automotive"
                            endpoints={automotiveApiEndpoints}
                            sdkExamples={automotiveSdkExamples}
                            colorScheme="red"
                        />
                    )}

                    {activeTab === 'quickstart' && (
                        <div className="space-y-8">
                            <div>
                                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                                    5-Minute Quickstart
                                </h2>
                                <p className="text-lg text-gray-700 dark:text-gray-300 mb-8">
                                    Create your first PPAP package with cryptographic verification.
                                </p>
                            </div>

                            {/* Step 1 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
                                    Step 1: Get Your API Key
                                </h3>
                                <p className="text-gray-700 dark:text-gray-300">
                                    Visit the{' '}
                                    <Link href="/api-keys" className="text-red-600 dark:text-red-400 hover:underline">
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
                                        $ npm install @regengine/automotive-sdk
                                    </code>
                                </div>
                            </div>

                            {/* Step 3 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
                                    Step 3: Create PPAP Package
                                </h3>
                                <CodePlayground
                                    title="Try It Live"
                                    description="Create an immutable PPAP submission"
                                    initialCode={`import { AutomotiveCompliance } from '@regengine/automotive-sdk';

const auto = new AutomotiveCompliance('rge_your_api_key_here');

// Create immutable PPAP package (18 elements)
const ppap = await auto.ppap.create({
  part_number: 'GM-12345-REV-C',
  supplier_code: 'ABC123',
  oem: 'GM',
  submission_level: 3,
  elements: {
    control_plan: {
      revision: 'D',
      characteristics: ['Wall thickness', 'Surface finish']
    },
    dimensional_results: {
      measurement_system: 'CMM',
      cpk: 1.67
    },
    process_fmea: {
      rpn_threshold: 100,
      high_risk_items: 0
    },
    // ... all 18 PPAP elements
  }
});

console.log('✅ PPAP sealed:', ppap.ppap_id);
console.log('🔒 Hash:', ppap.contentHash);
console.log('📋 OEM portal ready:', ppap.oem_portal_ready);`}
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
                                    <li>• Record layered process audits (LPA) with timestamped verification</li>
                                    <li>• Track 8D reports for customer complaints</li>
                                    <li>• Monitor IATF 16949 surveillance readiness in real-time</li>
                                    <li>• Create immutable control plans with revision tracking</li>
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
                                    Real-world examples for IATF 16949 compliance.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link
                                    href="/docs/automotive/ppap"
                                    className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700"
                                >
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        PPAP Submission
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        18-element production part approval
                                    </p>
                                </Link>

                                <Link
                                    href="/docs/automotive/lpa"
                                    className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700"
                                >
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Layered Process Audits
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Shop floor LPA with timestamps
                                    </p>
                                </Link>

                                <Link
                                    href="/docs/automotive/8d"
                                    className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700"
                                >
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        8D Problem Solving
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Customer complaint response tracking
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* CTA Section */}
                <div className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="bg-gradient-to-r from-red-600 to-orange-600 rounded-2xl p-12 text-center">
                            <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                            <p className="text-xl text-red-100 mb-8">
                                Get your API key and submit your first PPAP in under 5 minutes.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-red-600 rounded-lg font-semibold hover:bg-red-50 transition-colors"
                                >
                                    Get Free API Key
                                </Link>
                                <Link
                                    href="/verticals/automotive/pricing"
                                    className="px-8 py-4 bg-red-500/20 text-white rounded-lg font-semibold hover:bg-red-500/30 transition-colors border border-white/20"
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
