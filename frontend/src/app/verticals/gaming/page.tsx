'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Dices, Shield, DollarSign, CheckCircle, Code, Book } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { gamingIndustryData, gamingApiEndpoints, gamingSdkExamples } from './data';

export default function GamingDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
                {/* Hero Section */}
                <div className="relative overflow-hidden bg-gradient-to-r from-amber-600 to-orange-700 dark:from-amber-900 dark:to-orange-900">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-amber-500/20 rounded-full">
                                <Dices className="h-5 w-5 text-amber-200" />
                                <span className="text-sm font-medium text-amber-100">Gaming Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
                                The API for<br />
                                <span className="text-amber-200">Gaming Compliance</span>
                            </h1>

                            <p className="text-xl text-amber-100 mb-8 max-w-2xl mx-auto">
                                First gaming commission-compliant record in 5 minutes. Not 5 weeks.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-amber-600 rounded-lg font-semibold hover:bg-amber-50 transition-colors inline-flex items-center justify-center gap-2"
                                >
                                    <Code className="h-5 w-5" />
                                    Get API Key
                                </Link>
                                <Link
                                    href="/verticals/gaming/dashboard"
                                    className="px-8 py-4 bg-amber-500/20 text-white rounded-lg font-semibold hover:bg-amber-500/30 transition-colors inline-flex items-center justify-center gap-2 border border-white/20"
                                >
                                    <CheckCircle className="h-5 w-5" />
                                    Launch Portal
                                </Link>
                                <Link
                                    href="/docs/gaming"
                                    className="px-8 py-4 bg-amber-500/20 text-white rounded-lg font-semibold hover:bg-amber-500/30 transition-colors inline-flex items-center justify-center gap-2 border border-white/20"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex items-center gap-6 text-sm text-amber-200">
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
                                    Multi-jurisdiction
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
                            industry={gamingIndustryData.industry}
                            industryDescription={gamingIndustryData.description}
                            regulations={gamingIndustryData.regulations}
                            challenges={gamingIndustryData.challenges}
                            marketplaceSolutions={gamingIndustryData.marketplaceSolutions}
                            ourApproach={gamingIndustryData.ourApproach}
                            icon={Dices}
                        />
                    )}

                    {activeTab === 'api' && (
                        <ApiReferenceSection
                            vertical="Gaming"
                            baseUrl="https://api.regengine.co/v1/gaming"
                            endpoints={gamingApiEndpoints}
                            sdkExamples={gamingSdkExamples}
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
                                    Start logging gaming transactions in under 5 minutes.
                                </p>
                            </div>

                            <CodePlayground
                                title="Try It Live - Casino Transaction Logging"
                                description="Edit and run this code to log your first casino transaction"
                                initialCode={`import { GamingCompliance } from '@regengine/gaming-sdk';

const gaming = new GamingCompliance('rge_your_api_key');

// Log slot machine payout
const log = await gaming.transactionLog.create({
  transaction_id: 'TXN-20240126-001234',
  transaction_type: 'SLOT_MACHINE_PAYOUT',
  player_id: 'P-VIP-12345',
  machine_id: 'SLOT-A-042',
  amount_cents: 250000,
  timestamp: new Date().toISOString(),
  casino_location: 'Vegas Main Floor',
  jurisdiction: 'Nevada'
});

console.log('✅ Transaction logged:', log.log_id);
console.log('🔒 Content hash:', log.content_hash);
console.log('📅 Retention until:', log.retention_until);
console.log('📄 Jurisdiction compliant:', log.jurisdiction_compliant);

// Log self-exclusion
const exclusion = await gaming.selfExclusion.create({
  player_id: 'P- 987654',
  exclusion_type: 'TEMPORARY',
  reason: 'PLAYER_REQUEST',
  effective_date: '2024-01-26',
  duration_days: 30,
  casino_locations: ['Vegas Main Floor'],
  jurisdiction: 'Nevada'
});

console.log('\\n⚠️ Self-exclusion logged:', exclusion.exclusion_id);`}
                                language="typescript"
                                height="600px"
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
                                    Real-world examples for gaming commission compliance.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link href="/docs/gaming/quickstart" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Quickstart (5 minutes)
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Log your first casino transaction
                                    </p>
                                </Link>

                                <Link href="/docs/gaming/surveillance" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Surveillance Integration
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Correlate transactions with surveillance footage
                                    </p>
                                </Link>

                                <Link href="/docs/gaming/responsible-gaming" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Responsible Gaming
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Manage self-exclusion and problem gambling
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* CTA Section */}
                <div className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="bg-gradient-to-r from-amber-600 to-orange-600 rounded-2xl p-12 text-center">
                            <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                            <p className="text-xl text-amber-100 mb-8">
                                Get early access to the Gaming API and be among the first to integrate.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-amber-600 rounded-lg font-semibold hover:bg-amber-50 transition-colors"
                                >
                                    Join Waitlist
                                </Link>
                                <Link
                                    href="/verticals/gaming/pricing"
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
