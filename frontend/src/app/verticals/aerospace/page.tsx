'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Plane, CheckCircle, Code, Book } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { aerospaceIndustryData, aerospaceApiEndpoints, aerospaceSdkExamples } from './data';

export default function AerospaceDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
                {/* Hero Section */}
                <div className="relative overflow-hidden bg-gradient-to-r from-sky-600 to-blue-700 dark:from-sky-900 dark:to-blue-950">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-sky-500/20 rounded-full">
                                <Plane className="h-5 w-5 text-sky-200" />
                                <span className="text-sm font-medium text-sky-100">Aerospace Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
                                The API for<br />
                                <span className="text-sky-200">AS9100 \u0026 FAI Compliance</span>
                            </h1>

                            <p className="text-xl text-sky-100 mb-8 max-w-2xl mx-auto">
                                Cryptographic first article inspections. Immutable configuration baselines.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-sky-600 rounded-lg font-semibold hover:bg-sky-50 transition-colors inline-flex items-center justify-center gap-2"
                                >
                                    <Code className="h-5 w-5" />
                                    Get API Key
                                </Link>
                                <Link
                                    href="/docs/aerospace"
                                    className="px-8 py-4 bg-sky-500/20 text-white rounded-lg font-semibold hover:bg-sky-500/30 transition-colors inline-flex items-center justify-center gap-2 border border-white/20"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex items-center gap-6 text-sm text-sky-200">
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    AS9102 FAI reports
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    NADCAP evidence
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4" />
                                    Config management
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
                <VerticalTabs activeTab={activeTab} onTabChange={setActiveTab} colorScheme="sky" />

                {/* Tab Content */}
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    {activeTab === 'overview' && (
                        <IndustryOverviewSection
                            industry={aerospaceIndustryData.industry}
                            industryDescription={aerospaceIndustryData.description}
                            regulations={aerospaceIndustryData.regulations}
                            challenges={aerospaceIndustryData.challenges}
                            marketplaceSolutions={aerospaceIndustryData.marketplaceSolutions}
                            ourApproach={aerospaceIndustryData.ourApproach}
                            icon={Plane}
                        />
                    )}

                    {activeTab === 'api' && (
                        <ApiReferenceSection
                            vertical="Aerospace"
                            baseUrl="https://api.regengine.co/v1/aerospace"
                            endpoints={aerospaceApiEndpoints}
                            sdkExamples={aerospaceSdkExamples}
                            colorScheme="blue"
                        />
                    )}

                    {activeTab === 'quickstart' && (
                        <div className="space-y-8">
                            <div>
                                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                                    5-Minute Quickstart
                                </h2>
                                <p className="text-lg text-gray-700 dark:text-gray-300 mb-8">
                                    Create your first AS9102 FAI report with cryptographic verification.
                                </p>
                            </div>

                            {/* Step 1 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
                                    Step 1: Get Your API Key
                                </h3>
                                <p className="text-gray-700 dark:text-gray-300">
                                    Visit the{' '}
                                    <Link href="/api-keys" className="text-sky-600 dark:text-sky-400 hover:underline">
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
                                        $ npm install @regengine/aerospace-sdk
                                    </code>
                                </div>
                            </div>

                            {/* Step 3 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-gray-900 dark:text-gray-100">
                                    Step 3: Create FAI Report
                                </h3>
                                <CodePlayground
                                    title="Try It Live"
                                    description="Create an immutable First Article Inspection"
                                    initialCode={`import { AerospaceCompliance } from '@regengine/aerospace-sdk';

const aero = new AerospaceCompliance('rge_your_api_key_here');

// Create AS9102 FAI report
const fai = await aero.fai.create({
  part_number: 'BA-45678-REV-F',
  customer: 'Boeing',
  configuration: 'REV-F-CONFIG-01',
  form1_data: {
    part_name: 'Wing Spar Bracket',
    drawing_number: 'BA-45678',
    revision: 'F'
  },
  form3_measurements: [
    {
      characteristic_number: 1,
      characteristic: 'Overall Length',
      specification: '100.0 ± 0.2 mm',
      actual_measurement: 100.05,
      deviation: 0.05,
      measuring_equipment: 'CMM-001'
    }
  ],
  inspector: 'FAI Inspector - R. Martinez',
  inspection_date: new Date().toISOString()
});

console.log('✅ FAI sealed:', fai.fai_id);
console.log('🔒 Content hash:', fai.contentHash);
console.log('📋 AS9102 compliant:', fai.as9102_compliant);`}
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
                                    <li>• Create immutable configuration baselines with SHA-256 fingerprints</li>
                                    <li>• Record NADCAP special process evidence (heat treat, welding, NDT)</li>
                                    <li>• Verify supplier material certifications with blockchain anchoring</li>
                                    <li>• Monitor AS9100D surveillance readiness in real-time</li>
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
                                    Real-world examples for AS9100 compliance.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link
                                    href="/docs/aerospace/fai"
                                    className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700"
                                >
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        First Article Inspection
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        AS9102 Form 1/3 generation
                                    </p>
                                </Link>

                                <Link
                                    href="/docs/aerospace/config"
                                    className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700"
                                >
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Configuration Management
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Immutable revision tracking
                                    </p>
                                </Link>

                                <Link
                                    href="/docs/aerospace/nadcap"
                                    className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700"
                                >
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        NADCAP Evidence
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Special process verification
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* CTA Section */}
                <div className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="bg-gradient-to-r from-sky-600 to-blue-700 rounded-2xl p-12 text-center">
                            <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                            <p className="text-xl text-sky-100 mb-8">
                                Get your API key and create your first FAI report in under 5 minutes.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-sky-600 rounded-lg font-semibold hover:bg-sky-50 transition-colors"
                                >
                                    Get Free API Key
                                </Link>
                                <Link
                                    href="/verticals/aerospace/pricing"
                                    className="px-8 py-4 bg-sky-500/20 text-white rounded-lg font-semibold hover:bg-sky-500/30 transition-colors border border-white/20"
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
