'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Cpu, Code, Lock, CheckCircle, Book } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { technologyIndustryData, technologyApiEndpoints, technologySdkExamples } from './data';

export default function TechnologyDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
                {/* Hero Section */}
                <div className="relative overflow-hidden bg-gradient-to-r from-purple-600 to-pink-700 dark:from-purple-900 dark:to-pink-900">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-purple-500/20 rounded-full">
                                <Cpu className="h-5 w-5 text-purple-200" />
                                <span className="text-sm font-medium text-purple-100">Technology Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
                                The API for<br />
                                <span className="text-purple-200">SaaS Compliance</span>
                            </h1>

                            <p className="text-xl text-purple-100 mb-8 max-w-2xl mx-auto">
                                First SOC 2 evidence snapshot in 5 minutes. Not 5 weeks.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-purple-600 rounded-lg font-semibold hover:bg-purple-50 transition-colors inline-flex items-center justify-center gap-2"
                                >
                                    <Code className="h-5 w-5" />
                                    Get API Key
                                </Link>
                                <Link
                                    href="/docs/technology"
                                    className="px-8 py-4 bg-purple-500/20 text-white rounded-lg font-semibold hover:bg-purple-500/30 transition-colors inline-flex items-center justify-center gap-2 border border-white/20"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex items-center gap-6 text-sm text-purple-200">
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
                                    SOC 2 / ISO 27001
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
                <VerticalTabs activeTab={activeTab} onTabChange={setActiveTab} colorScheme="purple" />

                {/* Tab Content */}
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    {activeTab === 'overview' && (
                        <IndustryOverviewSection
                            industry={technologyIndustryData.industry}
                            industryDescription={technologyIndustryData.description}
                            regulations={technologyIndustryData.regulations}
                            challenges={technologyIndustryData.challenges}
                            marketplaceSolutions={technologyIndustryData.marketplaceSolutions}
                            ourApproach={technologyIndustryData.ourApproach}
                            icon={Cpu}
                        />
                    )}

                    {activeTab === 'api' && (
                        <ApiReferenceSection
                            vertical="Technology"
                            baseUrl="https://api.regengine.co/v1/technology"
                            endpoints={technologyApiEndpoints}
                            sdkExamples={technologySdkExamples}
                            colorScheme="purple"
                        />
                    )}

                    {activeTab === 'quickstart' && (
                        <div className="space-y-8">
                            <div>
                                <h2 className="text-3xl font-bold text-gray-900 dark:text-gray-100 mb-4">
                                    5-Minute Quickstart
                                </h2>
                                <p className="text-lg text-gray-700 dark:text-gray-300 mb-8">
                                    Start monitoring SaaS configuration drift in under 5 minutes.
                                </p>
                            </div>

                            <CodePlayground
                                title="Try It Live - Configuration Drift Detection"
                                description="Edit and run this code to detect infrastructure drift"
                                initialCode={`import { TechnologyCompliance } from '@regengine/technology-sdk';

const tech = new TechnologyCompliance('rge_your_api_key');

// Create baseline snapshot
const baseline = await tech.configSnapshots.create({
  service: 'AWS_IAM',
  config_type: 'SECURITY_POLICY',
  config_data: {
    account_id: '123456789012',
    policies: [{
      name: 'AdminRequiresMFA',
      mfa_enabled: true,
      ip_restrictions: true
    }]
  },
  control_mapping: ['SOC2_CC6.1', 'ISO27001_A.9.2.1']
});

console.log('✅ Baseline snapshot created:', baseline.snapshot_id);

// Simulate current config with drift
const drift = await tech.driftDetection.detect({
  baseline_snapshot_id: baseline.snapshot_id,
  current_config: {
    service: 'AWS_IAM',
    config_data: {
      account_id: '123456789012',
      policies: [{
        name: 'AdminRequiresMFA',
        mfa_enabled: false, // DRIFT DETECTED!
        ip_restrictions: true
      }]
    }
  }
});

console.log('\\n🚨 Drift Detection Result:');
console.log('  Has drift:', drift.has_drift);
console.log('  Severity:', drift.drift_severity);
console.log('  Changes:', drift.total_changes);`}
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
                                    Real-world examples for SOC 2 and infrastructure compliance.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link href="/docs/technology/quickstart" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Quickstart (5 minutes)
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Snapshot AWS IAM configuration
                                    </p>
                                </Link>

                                <Link href="/docs/technology/drift-detection" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Drift Detection
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Detect unauthorized configuration changes
                                    </p>
                                </Link>

                                <Link href="/docs/technology/vendor-tracking" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Vendor Certification Tracking
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Monitor SaaS vendor SOC 2 expirations
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* CTA Section */}
                <div className="bg-gray-50 dark:bg-gray-900 border-t border-gray-200 dark:border-gray-800 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="bg-gradient-to-r from-purple-600 to-pink-600 rounded-2xl p-12 text-center">
                            <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                            <p className="text-xl text-purple-100 mb-8">
                                Get early access to the Technology API and be among the first to integrate.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-purple-600 rounded-lg font-semibold hover:bg-purple-50 transition-colors"
                                >
                                    Join Waitlist
                                </Link>
                                <Link
                                    href="/verticals/technology/pricing"
                                    className="px-8 py-4 bg-purple-500/20 text-white rounded-lg font-semibold hover:bg-purple-500/30 transition-colors border border-white/20"
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
