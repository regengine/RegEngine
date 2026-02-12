'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Shield, Zap, Activity, CheckCircle, Code, Book, FileText, Download } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { energyIndustryData, energyApiEndpoints, energySdkExamples } from './data';

// ... (imports remain same)

export default function EnergyDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>
            <div className="min-h-screen bg-[#06090f] text-slate-200">
                {/* Hero Section */}
                <div className="relative overflow-hidden border-b border-slate-800 bg-[#06090f]">
                    <div className="absolute inset-0 bg-emerald-500/5" />
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24 relative z-10">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-emerald-500/10 rounded-full border border-emerald-500/20">
                                <Zap className="h-5 w-5 text-emerald-400" />
                                <span className="text-sm font-medium text-emerald-300">Energy Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6 tracking-tight">
                                The API for<br />
                                <span className="text-emerald-400">Energy Grid Compliance</span>
                            </h1>

                            <p className="text-xl text-slate-400 mb-8 max-w-2xl mx-auto">
                                First CIP-013 compliance snapshot in 5 minutes. Not 5 weeks.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-8">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-500 transition-colors inline-flex items-center justify-center gap-2 shadow-lg shadow-emerald-900/20"
                                >
                                    <Code className="h-5 w-5" />
                                    Get API Key
                                </Link>
                                <Link
                                    href="/docs/energy"
                                    className="px-8 py-4 bg-white/5 text-white rounded-lg font-semibold hover:bg-white/10 transition-colors inline-flex items-center justify-center gap-2 border border-white/10"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex items-center gap-6 text-sm text-slate-400">
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4 text-emerald-500" />
                                    5-min quickstart
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4 text-emerald-500" />
                                    SDKs for Node, Python, Go
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4 text-emerald-500" />
                                    SHA-256 audit trail
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Tabs Navigation */}
                <VerticalTabs activeTab={activeTab} onTabChange={setActiveTab} colorScheme="emerald" />

                {/* Tab Content */}
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    {activeTab === 'overview' && (
                        <IndustryOverviewSection
                            industry={energyIndustryData.industry}
                            industryDescription={energyIndustryData.description}
                            regulations={energyIndustryData.regulations}
                            challenges={energyIndustryData.challenges}
                            marketplaceSolutions={energyIndustryData.marketplaceSolutions}
                            ourApproach={energyIndustryData.ourApproach}
                            icon={Zap}
                        />
                    )}

                    {activeTab === 'api' && (
                        <ApiReferenceSection
                            vertical="Energy"
                            baseUrl="https://api.regengine.co/v1/energy"
                            endpoints={energyApiEndpoints}
                            sdkExamples={energySdkExamples}
                            colorScheme="emerald"
                        />
                    )}

                    {activeTab === 'quickstart' && (
                        <div className="space-y-8">
                            <div>
                                <h2 className="text-3xl font-bold text-white mb-4">
                                    5-Minute Quickstart
                                </h2>
                                <p className="text-lg text-slate-400 mb-8">
                                    Get started with the Energy API in under 5 minutes. This guide walks you through
                                    creating your first compliance snapshot.
                                </p>
                            </div>

                            {/* Step 1 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-white">
                                    Step 1: Get Your API Key
                                </h3>
                                <p className="text-slate-400">
                                    Visit the{' '}
                                    <Link href="/api-keys" className="text-emerald-400 hover:text-emerald-300 hover:underline">
                                        API Keys page
                                    </Link>{' '}
                                    to generate your free API key.
                                </p>
                            </div>

                            {/* Step 2 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-white">
                                    Step 2: Install the SDK
                                </h3>
                                <div className="bg-[#0c1017] border border-slate-800 rounded-lg p-4">
                                    <code className="text-sm text-emerald-400 font-mono">
                                        $ npm install @regengine/energy-sdk
                                    </code>
                                </div>
                            </div>

                            {/* Step 3 */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-white">
                                    Step 3: Create Your First Snapshot
                                </h3>
                                <CodePlayground
                                    title="Try It Live"
                                    description="Edit and run this code to create a snapshot"
                                    initialCode={`import { EnergyCompliance } from '@regengine/energy-sdk';

const energy = new EnergyCompliance('rge_your_api_key_here');

// Create an immutable compliance snapshot
const snapshot = await energy.snapshots.create({
  substationId: 'ALPHA-001',
  facilityName: 'Alpha Substation',
  systemStatus: 'NOMINAL',
  assets: [
    {
      id: 'T1',
      type: 'TRANSFORMER',
      firmwareVersion: '2.4.1',
      lastVerified: new Date().toISOString()
    }
  ],
  espConfig: {
    firewallVersion: '2.4.1',
    idsEnabled: true,
    patchLevel: 'current'
  },
  regulatory: {
    standard: 'NERC-CIP-013-1',
    auditReady: true
  }
});

console.log('✅ Snapshot created:', snapshot.id);
console.log('🔒 Cryptographic hash:', snapshot.contentHash);
console.log('⛓️  Chain status:', snapshot.chainStatus);`}
                                    language="typescript"
                                    height="500px"
                                />
                            </div>

                            {/* Next Steps */}
                            <div className="space-y-4">
                                <h3 className="text-2xl font-semibold text-white">
                                    Next Steps
                                </h3>
                                <ul className="space-y-2 text-slate-400">
                                    <li>• Verify snapshot integrity with cryptographic verification</li>
                                    <li>• Set up incident response triggers</li>
                                    <li>• Integrate with your existing monitoring tools</li>
                                    <li>• Explore the full API reference</li>
                                </ul>
                            </div>
                        </div>
                    )}

                    {activeTab === 'examples' && (
                        <div className="space-y-12">
                            <div>
                                <h2 className="text-3xl font-bold text-white mb-4">
                                    Code Examples
                                </h2>
                                <p className="text-lg text-slate-400">
                                    Real-world examples to help you integrate the Energy API into your workflow.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link
                                    href="/docs/energy/quickstart"
                                    className="p-6 bg-[#0c1017] rounded-lg border border-slate-800 hover:border-emerald-500/50 transition-colors group"
                                >
                                    <h3 className="text-lg font-semibold text-white group-hover:text-emerald-400 transition-colors mb-2">
                                        Quickstart (5 minutes)
                                    </h3>
                                    <p className="text-slate-400 text-sm">
                                        Send your first compliance snapshot
                                    </p>
                                </Link>

                                <Link
                                    href="/docs/energy/verification"
                                    className="p-6 bg-[#0c1017] rounded-lg border border-slate-800 hover:border-emerald-500/50 transition-colors group"
                                >
                                    <h3 className="text-lg font-semibold text-white group-hover:text-emerald-400 transition-colors mb-2">
                                        Verify Chain Integrity
                                    </h3>
                                    <p className="text-slate-400 text-sm">
                                        Cryptographically verify snapshot chains
                                    </p>
                                </Link>

                                <Link
                                    href="/docs/energy/incident"
                                    className="p-6 bg-[#0c1017] rounded-lg border border-slate-800 hover:border-emerald-500/50 transition-colors group"
                                >
                                    <h3 className="text-lg font-semibold text-white group-hover:text-emerald-400 transition-colors mb-2">
                                        Incident Response
                                    </h3>
                                    <p className="text-slate-400 text-sm">
                                        Trigger snapshots from security events
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* White Paper Download Section */}
                <div className="py-16 border-y border-slate-800 bg-[#0c1017]/50">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="max-w-4xl mx-auto">
                            <div className="flex items-start gap-6">
                                <div className="flex-shrink-0">
                                    <div className="w-16 h-16 bg-emerald-500/10 rounded-lg flex items-center justify-center border border-emerald-500/20">
                                        <FileText className="h-8 w-8 text-emerald-400" />
                                    </div>
                                </div>
                                <div className="flex-1">
                                    <h2 className="text-2xl font-bold text-white mb-3">
                                        Energy Sector Compliance White Paper
                                    </h2>
                                    <p className="text-slate-300 mb-4">
                                        <strong>Automating NERC CIP Compliance with Tamper-Evident Evidence Chains</strong>
                                    </p>
                                    <p className="text-slate-400 mb-4 text-sm">
                                        38-page executive white paper quantifying how tamper-evident BES Cyber System monitoring prevents $1M/day FERC penalties and accelerates transmission approvals (18 months → 4 months). Includes 7.5 GW utility achieving 250%+ ROI with $12M+ penalties avoided.
                                    </p>
                                    <div className="flex flex-wrap gap-3">
                                        <Link
                                            href="/resources/whitepapers"
                                            className="inline-flex items-center gap-2 px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-semibold transition-colors shadow-lg shadow-emerald-900/20"
                                        >
                                            <Download className="h-4 w-4" />
                                            Download White Paper
                                        </Link>
                                        <Link
                                            href="/resources/whitepapers"
                                            className="inline-flex items-center gap-2 px-6 py-3 bg-white/5 hover:bg-white/10 text-slate-200 rounded-lg font-semibold transition-colors border border-white/10"
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
                <div className="bg-[#06090f] py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="bg-gradient-to-r from-emerald-900/40 to-emerald-800/20 border border-emerald-500/20 rounded-2xl p-12 text-center relative overflow-hidden">
                            <div className="absolute inset-0 bg-[url('/grid.svg')] opacity-10" />
                            <div className="relative z-10">
                                <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                                <p className="text-xl text-slate-300 mb-8">
                                    Get your API key and record your first snapshot in under 5 minutes.
                                </p>
                                <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                    <Link
                                        href="/api-keys"
                                        className="px-8 py-4 bg-white text-emerald-900 rounded-lg font-semibold hover:bg-slate-100 transition-colors shadow-[0_0_20px_rgba(255,255,255,0.3)]"
                                    >
                                        Get Free API Key
                                    </Link>
                                    <Link
                                        href="/verticals/energy/pricing"
                                        className="px-8 py-4 bg-emerald-500/10 text-emerald-400 rounded-lg font-semibold hover:bg-emerald-500/20 transition-colors border border-emerald-500/30"
                                    >
                                        View Pricing
                                    </Link>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </>
    );
}
