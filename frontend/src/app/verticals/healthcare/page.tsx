'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Activity, Shield, Heart, CheckCircle, Code, Book, FileText, Download } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { healthcareIndustryData, healthcareApiEndpoints, healthcareSdkExamples } from './data';

export default function HealthcareDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>            <div className="min-h-screen bg-gradient-to-b from-gray-50 to-white dark:from-gray-900 dark:to-gray-800">
                {/* Hero Section */}
                <div className="relative overflow-hidden bg-gradient-to-r from-red-600 to-pink-700 dark:from-red-900 dark:to-pink-900">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-red-500/20 rounded-full">
                                <Heart className="h-5 w-5 text-red-200" />
                                <span className="text-sm font-medium text-red-100">Healthcare Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6">
                                The API for<br />
                                <span className="text-red-200">Healthcare Compliance</span>
                            </h1>

                            <p className="text-xl text-red-100 mb-8 max-w-2xl mx-auto">
                                First HIPAA-compliant access log in 5 minutes. Not 5 weeks.
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
                                    href="/docs/healthcare"
                                    className="px-8 py-4 bg-red-500/20 text-white rounded-lg font-semibold hover:bg-red-500/30 transition-colors inline-flex items-center justify-center gap-2 border border-white/20"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex items-center gap-6 text-sm text-red-200">
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
                                    HIPAA compliant
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
                            industry={healthcareIndustryData.industry}
                            industryDescription={healthcareIndustryData.description}
                            regulations={healthcareIndustryData.regulations}
                            challenges={healthcareIndustryData.challenges}
                            marketplaceSolutions={healthcareIndustryData.marketplaceSolutions}
                            ourApproach={healthcareIndustryData.ourApproach}
                            icon={Heart}
                        />
                    )}

                    {activeTab === 'api' && (
                        <ApiReferenceSection
                            vertical="Healthcare"
                            baseUrl="https://api.regengine.co/v1/healthcare"
                            endpoints={healthcareApiEndpoints}
                            sdkExamples={healthcareSdkExamples}
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
                                    Start logging ePHI access with behavioral risk monitoring in under 5 minutes.
                                </p>
                            </div>

                            <CodePlayground
                                title="Try It Live - Healthcare Access Logging"
                                description="Edit and run this code to log ePHI access with risk scoring"
                                initialCode={`import { HealthcareCompliance } from '@regengine/healthcare-sdk';

const healthcare = new HealthcareCompliance('rge_your_api_key');

// Log ePHI access event
const accessLog = await healthcare.accessLog.create({
  userId: 'dr_house_1234',
  userRole: 'MD',
  action: 'VIEW',
  patientId: 'P-VIP-001',
  recordType: 'MEDICAL_RECORD',
  timestamp: new Date().toISOString(),
  facilityId: 'ER-DEPT-01'
});

console.log('✅ Access logged:', accessLog.logId);
console.log('🚨 Risk score:', accessLog.riskScore);
console.log('⚠️  Flagged:', accessLog.flagged);
if (accessLog.flagged) {
  console.log('📋 Reason:', accessLog.reason);
}

// Get real-time risk heatmap
const heatmap = await healthcare.riskHeatmap.get();
console.log('\\n📊 Department Risk:');
heatmap.departments.forEach(dept => {
  console.log(\`  \${dept.name}: \${dept.riskScore}% (\${dept.status})\`);
});`}
                                language="typescript"
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
                                    Real-world examples for HIPAA compliance and behavioral monitoring.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link href="/docs/healthcare/quickstart" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Quickstart (5 minutes)
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Log your first ePHI access event
                                    </p>
                                </Link>

                                <Link href="/docs/healthcare/risk-monitor" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        Clinical Risk Monitor
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Real-time behavioral anomaly detection
                                    </p>
                                </Link>

                                <Link href="/docs/healthcare/audit-export" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                                    <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                        OCR Audit Export
                                    </h3>
                                    <p className="text-gray-600 dark:text-gray-400 text-sm">
                                        Export 6+ years of audit trails
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* White Paper Download Section */}
                <div className="bg-red-50 dark:bg-red-900/10 border-y border-red-100 dark:border-red-900/30 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-4xl mx-auto">
                            <div className="flex items-start gap-6">
                                <div className="flex-shrink-0">
                                    <div className="w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-lg flex items-center justify-center">
                                        <FileText className="h-8 w-8 text-red-600 dark:text-red-400" />
                                    </div>
                                </div>
                                <div className="flex-1">
                                    <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 mb-3">
                                        Healthcare Compliance White Paper
                                    </h2>
                                    <p className="text-gray-700 dark:text-gray-300 mb-4">
                                        <strong>Automating HIPAA/HITECH Compliance with Tamper-Evident Audit Trails</strong>
                                    </p>
                                    <p className="text-gray-600 dark:text-gray-400 mb-4 text-sm">
                                        37-page executive white paper on preventing breaches with continuous PHI access monitoring ($4M+ penalties avoided per breach). Includes 500-bed health system achieving 175%+ ROI with 67% faster payer contracting (5.2 months → 1.8 months).
                                    </p>
                                    <div className="flex flex-wrap gap-3">
                                        <Link
                                            href="/resources/whitepapers"
                                            className="inline-flex items-center gap-2 px-6 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg font-semibold transition-colors"
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
                        <div className="bg-gradient-to-r from-red-600 to-pink-600 rounded-2xl p-12 text-center">
                            <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                            <p className="text-xl text-red-100 mb-8">
                                Get your API key and start logging ePHI access in under 5 minutes.
                            </p>
                            <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-white text-red-600 rounded-lg font-semibold hover:bg-red-50 transition-colors"
                                >
                                    Get Free API Key
                                </Link>
                                <Link
                                    href="/verticals/healthcare/pricing"
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
