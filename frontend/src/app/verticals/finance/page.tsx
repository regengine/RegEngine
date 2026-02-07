'use client';

import { useState } from 'react';
import Link from 'next/link';
import { TrendingUp, Shield, Lock, CheckCircle, Code, Book } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { financeIndustryData, financeApiEndpoints, financeSdkExamples } from './data';

export default function FinanceDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
                {/* Hero Section */}
                <div className="relative overflow-hidden bg-gradient-to-r from-emerald-600 to-teal-700 dark:from-emerald-900 dark:to-teal-900">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-emerald-500/20 rounded-full">
                                <TrendingUp className="h-5 w-5 text-emerald-200" />
                                <span className="text-sm font-medium text-emerald-100">Finance Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
                                The API for<br />
                                <span className="text-emerald-200">Financial Compliance</span>
                            </h1>

                            <p className="text-xl text-emerald-100 mb-8 max-w-2xl mx-auto">
                                First SOC 2 evidence snapshot in 5 minutes. Not 5 weeks.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-emerald-600 rounded-lg font-semibold hover:bg-emerald-50 transition-colors inline-flex items-center justify-center gap-2"
                                >
                                    <Code className="h-5 w-5" />
                                    Get API Key
                                </Link>
                                <Link
                                    href="/docs/finance"
                                    className="px-8 py-4 bg-emerald-500/20 text-white rounded-lg font-semibold hover:bg-emerald-500/30 transition-colors inline-flex items-center justify-center gap-2 border border-white/20"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex items-center gap-6 text-sm text-emerald-200">
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
                                    SOC 2 / PCI DSS ready
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
                <VerticalTabs activeTab={activeTab} onTabChange={setActiveTab} colorScheme="emerald" />

                {/* Tab Content */}
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    {activeTab === 'overview' && (
                        <IndustryOverviewSection
                            industry={financeIndustryData.industry}
                            industryDescription={financeIndustryData.description}
                            regulations={financeIndustryData.regulations}
                            challenges={financeIndustryData.challenges}
                            marketplaceSolutions={financeIndustryData.marketplaceSolutions}
                            ourApproach={financeIndustryData.ourApproach}
                            icon={TrendingUp}
                        />
                    )}

                    {activeTab === 'api' && (
                        <ApiReferenceSection
                            vertical="Finance"
                            baseUrl="https://api.regengine.co/v1/finance"
                            endpoints={financeApiEndpoints}
                            sdkExamples={financeSdkExamples}
                            colorScheme="emerald"
                        />
                    )}

                    {activeTab === 'quickstart' && (
                        <div className="space-y-8">
                            <div>
                                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                                    5-Minute Quickstart
                                </h2>
                                <p className="text-lg text-gray-700 dark:text-gray-300 mb-8">
                                    Start recording SOC 2 evidence snapshots in under 5 minutes.
                                </p>
                            </div>

                            <CodePlayground
                                title="Try It Live - SOC 2 Evidence Collection"
                                description="Edit and run this code to create your first evidence snapshot"
                                initialCode={`import { FinanceCompliance } from '@regengine/finance-sdk';

const finance = new FinanceCompliance('rge_your_api_key');

// Snapshot AWS IAM MFA policy
const snapshot = await finance.evidenceSnapshots.create({
  control_id: 'CC1.2',
  control_name: 'MFA Required for Admin Access',
  evidence_type: 'AWS_IAM_POLICY',
  evidence_data: {
    policy_name: 'AdminRequiresMFA',
    policy_arn: 'arn:aws:iam::123456789012:policy/AdminMFA',
    mfa_required: true,
    enabled: true
  },
  audit_period: '2024-Q1'
});

console.log('✅ Evidence snapshot created:', snapshot.snapshot_id);
console.log('🔒 Content hash:', snapshot.content_hash);
console.log('📋 Audit ready:', snapshot.audit_ready);

// Verify snapshot integrity
const verification = await finance.evidenceSnapshots.verify(snapshot.snapshot_id);
console.log('\\n🔐 Verification Result:');
console.log('  Valid:', verification.is_valid);
console.log('  Chain valid:', verification.chain_valid);
console.log('  Tampered:', verification.tampered);`}
                                language="typescript"
                                height="550px"
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
                                    Real-world examples for SOC 2 and financial compliance automation.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link href="/docs/finance/quickstart" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Quickstart (5 minutes)
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Collect your first SOC 2 evidence snapshot
                                    </p>
                                </Link>

                                <Link href="/docs/finance/vendor-risk" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Vendor Risk Monitoring
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Track vendor SOC 2 certifications and expirations
                                    </p>
                                </Link>

                                <Link href="/docs/finance/audit-export" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Audit Report Export
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Generate audit-ready reports for your auditor
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* CTA Section */}
                <div className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="bg-gradient-to-r from-emerald-600 to-teal-600 rounded-2xl p-12 text-center">
                            <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                            <p className="text-xl text-emerald-100 mb-8">
                                Get early access to the Finance API and be among the first to integrate.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-emerald-600 rounded-lg font-semibold hover:bg-emerald-50 transition-colors"
                                >
                                    Join Waitlist
                                </Link>
                                <Link
                                    href="/verticals/finance/pricing"
                                    className="px-8 py-4 bg-emerald-500/20 text-white rounded-lg font-semibold hover:bg-emerald-500/30 transition-colors border border-white/20"
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
