'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Atom, Shield, CheckCircle, Code, Book, FileText, Download, AlertTriangle, Clock, Users } from 'lucide-react';
import { VerticalTabs, VerticalTab } from '@/components/verticals/VerticalTabs';
import { IndustryOverviewSection } from '@/components/verticals/IndustryOverviewSection';
import { ApiReferenceSection } from '@/components/verticals/ApiReferenceSection';
import { CodePlayground } from '@/components/playground/CodePlayground';
import { nuclearIndustryData, nuclearApiEndpoints, nuclearSdkExamples } from './data';

export default function NuclearDevelopersPage() {
    const [activeTab, setActiveTab] = useState<VerticalTab>('overview');

    return (
        <>
            <div className="min-h-screen bg-[#06090f] text-slate-200">
                {/* Hero Section */}
                <div className="relative overflow-hidden border-b border-slate-800 bg-[#06090f]">
                    <div className="absolute inset-0 bg-emerald-500/5" />
                    <div className="absolute top-0 right-0 -mr-40 -mt-40 w-80 h-80 bg-emerald-500/10 rounded-full blur-3xl" />
                    <div className="absolute bottom-0 left-0 -ml-40 -mb-40 w-80 h-80 bg-cyan-500/10 rounded-full blur-3xl" />

                    <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-24">
                        <div className="text-center">
                            <div className="mb-4 inline-flex items-center gap-2 px-4 py-2 bg-emerald-500/10 rounded-full border border-emerald-500/20">
                                <Atom className="h-5 w-5 text-emerald-400" />
                                <span className="text-sm font-medium text-emerald-300">Nuclear Compliance API</span>
                            </div>

                            <h1 className="text-5xl md:text-6xl font-bold text-white mb-6 tracking-tight">
                                Compliance infrastructure for the<br />
                                <span className="text-emerald-400">next generation of nuclear</span>
                            </h1>

                            <p className="text-xl text-slate-300 mb-8 max-w-2xl mx-auto leading-relaxed">
                                Tamper-evident evidence chains for SMR licensing, multi-module QA coordination,
                                and ITAAC closure tracking — delivered as an API.
                            </p>

                            <div className="flex flex-col sm:flex-row gap-4 justify-center mb-12">
                                <Link
                                    href="/api-keys"
                                    className="px-8 py-4 bg-emerald-600 text-white rounded-lg font-semibold hover:bg-emerald-500 transition-colors inline-flex items-center justify-center gap-2 shadow-lg shadow-emerald-900/20"
                                >
                                    <Code className="h-5 w-5" />
                                    Get API Key →
                                </Link>
                                <Link
                                    href="/docs/nuclear"
                                    className="px-8 py-4 bg-white/5 text-slate-200 rounded-lg font-semibold hover:bg-white/10 transition-colors inline-flex items-center justify-center gap-2 border border-white/10"
                                >
                                    <Book className="h-5 w-5" />
                                    Read the Docs
                                </Link>
                            </div>

                            <div className="inline-flex flex-wrap items-center justify-center gap-6 text-sm text-slate-400">
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4 text-emerald-400" />
                                    5-min quickstart
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4 text-emerald-400" />
                                    Part 52 Design Cert Ready
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4 text-emerald-400" />
                                    SHA-256 Hash Verification
                                </span>
                                <span className="flex items-center gap-2">
                                    <CheckCircle className="h-4 w-4 text-emerald-400" />
                                    60+ yr Retention Architecture
                                </span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* SMR-Specific Challenges */}
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    <div className="mb-8">
                        <div className="text-emerald-400 text-sm font-mono uppercase tracking-wider mb-4 flex items-center gap-2">
                            <span className="w-6 h-px bg-emerald-400" />
                            Why SMRs Have It Harder
                        </div>
                        <h2 className="text-3xl font-bold text-white mb-4">
                            Small reactors. Outsized compliance burden.
                        </h2>
                        <p className="text-lg text-slate-400 max-w-3xl">
                            Advanced reactors face every legacy compliance requirement plus first-of-a-kind
                            licensing complexity that traditional plants never encountered.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6 mb-16">
                        <div className="bg-white/5 border border-white/10 rounded-lg p-6 hover:border-emerald-500/30 hover:bg-white/[0.07] transition-all">
                            <div className="flex items-start justify-between mb-3">
                                <h3 className="text-lg font-semibold text-white">First-of-a-Kind Licensing</h3>
                                <span className="text-xs px-2 py-1 bg-red-500/20 text-red-400 rounded font-mono">HIGH</span>
                            </div>
                            <p className="text-sm text-slate-400 leading-relaxed">
                                No precedent documentation to reference. Every evidence chain is novel.
                                Design Certification under 10 CFR Part 52 requires demonstrating compliance
                                against criteria that were written for gigawatt-scale PWRs — not modular architectures.
                            </p>
                        </div>

                        <div className="bg-white/5 border border-white/10 rounded-lg p-6 hover:border-emerald-500/30 hover:bg-white/[0.07] transition-all">
                            <div className="flex items-start justify-between mb-3">
                                <h3 className="text-lg font-semibold text-white">Multi-Module QA Coordination</h3>
                                <span className="text-xs px-2 py-1 bg-red-500/20 text-red-400 rounded font-mono">HIGH</span>
                            </div>
                            <p className="text-sm text-slate-400 leading-relaxed">
                                A 12-module VOYGR-style plant creates N modules × M shared systems of documentation.
                                Each module has independent safety records, but shared balance-of-plant systems
                                create cross-reference dependencies that compound exponentially.
                            </p>
                        </div>

                        <div className="bg-white/5 border border-white/10 rounded-lg p-6 hover:border-emerald-500/30 hover:bg-white/[0.07] transition-all">
                            <div className="flex items-start justify-between mb-3">
                                <h3 className="text-lg font-semibold text-white">ITAAC Closure at Scale</h3>
                                <span className="text-xs px-2 py-1 bg-red-500/20 text-red-400 rounded font-mono">HIGH</span>
                            </div>
                            <p className="text-sm text-slate-400 leading-relaxed">
                                Hundreds of Inspections, Tests, Analyses, and Acceptance Criteria must be closed
                                before fuel load — each requiring cryptographically verifiable evidence.
                                A single unresolved ITAAC blocks your entire commissioning timeline.
                            </p>
                        </div>

                        <div className="bg-white/5 border border-white/10 rounded-lg p-6 hover:border-emerald-500/30 hover:bg-white/[0.07] transition-all">
                            <div className="flex items-start justify-between mb-3">
                                <h3 className="text-lg font-semibold text-white">Factory Fabrication QA</h3>
                                <span className="text-xs px-2 py-1 bg-amber-500/20 text-amber-400 rounded font-mono">MEDIUM</span>
                            </div>
                            <p className="text-sm text-slate-400 leading-relaxed">
                                SMR economics depend on factory-built modules shipped to site. Your supply chain
                                QA now extends to off-site manufacturing facilities — each needing its own
                                10 CFR 50 Appendix B evidence chain tied back to the Combined License.
                            </p>
                        </div>

                        <div className="bg-white/5 border border-white/10 rounded-lg p-6 hover:border-emerald-500/30 hover:bg-white/[0.07] transition-all">
                            <div className="flex items-start justify-between mb-3">
                                <h3 className="text-lg font-semibold text-white">Accelerated Timelines</h3>
                                <span className="text-xs px-2 py-1 bg-amber-500/20 text-amber-400 rounded font-mono">MEDIUM</span>
                            </div>
                            <p className="text-sm text-slate-400 leading-relaxed">
                                SMR business cases assume faster licensing than legacy plants. You can't afford
                                36-month license amendments. Every week of NRC back-and-forth on documentation
                                gaps erodes the economic advantage modular design was supposed to deliver.
                            </p>
                        </div>

                        <div className="bg-white/5 border border-white/10 rounded-lg p-6 hover:border-emerald-500/30 hover:bg-white/[0.07] transition-all">
                            <div className="flex items-start justify-between mb-3">
                                <h3 className="text-lg font-semibold text-white">Risk-Informed Classification</h3>
                                <span className="text-xs px-2 py-1 bg-cyan-500/20 text-cyan-400 rounded font-mono">NEW</span>
                            </div>
                            <p className="text-sm text-slate-400 leading-relaxed">
                                10 CFR 50.69 lets SMR vendors reduce documentation burden on non-safety-significant
                                SSCs — but only if you can prove the categorization with auditable evidence.
                                The cost savings require upfront compliance investment.
                            </p>
                        </div>
                    </div>

                    {/* ITAAC Tracker Preview */}
                    <div className="mb-16">
                        <div className="text-emerald-400 text-sm font-mono uppercase tracking-wider mb-4 flex items-center gap-2">
                            <span className="w-6 h-px bg-emerald-400" />
                            ITAAC Closure Tracking
                        </div>
                        <h2 className="text-3xl font-bold text-white mb-4">
                            Every acceptance criterion. Every module. One API.
                        </h2>
                        <p className="text-lg text-slate-400 max-w-3xl mb-8">
                            Model projection: a 6-module SMR deployment generates ~4,200 evidence records
                            during ITAAC closure. All searchable in &lt;30 seconds.
                        </p>

                        <div className="bg-white/5 border border-white/10 rounded-lg overflow-hidden">
                            <div className="bg-slate-900/50 border-b border-white/10 px-6 py-4 flex items-center justify-between">
                                <h4 className="text-sm font-mono text-slate-300">ITAAC Status — VOYGR-6 Demo Plant</h4>
                                <span className="text-xs px-2 py-1 bg-cyan-500/20 text-cyan-400 rounded font-mono">DEMO</span>
                            </div>
                            <div className="overflow-x-auto">
                                <table className="w-full">
                                    <thead>
                                        <tr className="border-b border-white/10">
                                            <th className="text-left px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">ITAAC ID</th>
                                            <th className="text-left px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">Module</th>
                                            <th className="text-left px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">System</th>
                                            <th className="text-left px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">Description</th>
                                            <th className="text-left px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">Status</th>
                                            <th className="text-left px-6 py-3 text-xs font-medium text-slate-400 uppercase tracking-wider">Evidence Hash</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr className="border-b border-white/5">
                                            <td className="px-6 py-4 text-sm font-mono text-slate-300">ITAAC-2.1.01</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">NPM-01</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">RCS</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">Reactor coolant system pressure boundary integrity test</td>
                                            <td className="px-6 py-4 text-sm">
                                                <span className="flex items-center gap-2">
                                                    <span className="w-2 h-2 bg-emerald-400 rounded-full shadow-lg shadow-emerald-400/50"></span>
                                                    <span className="text-slate-300">Closed</span>
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-xs font-mono text-slate-500">a3f8c9…d41e</td>
                                        </tr>
                                        <tr className="border-b border-white/5">
                                            <td className="px-6 py-4 text-sm font-mono text-slate-300">ITAAC-2.1.02</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">NPM-01</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">DHRS</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">Decay heat removal system functional test</td>
                                            <td className="px-6 py-4 text-sm">
                                                <span className="flex items-center gap-2">
                                                    <span className="w-2 h-2 bg-emerald-400 rounded-full shadow-lg shadow-emerald-400/50"></span>
                                                    <span className="text-slate-300">Closed</span>
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-xs font-mono text-slate-500">7b2e01…f83a</td>
                                        </tr>
                                        <tr className="border-b border-white/5">
                                            <td className="px-6 py-4 text-sm font-mono text-slate-300">ITAAC-3.4.07</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">NPM-02</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">ECCS</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">Emergency core cooling valve stroke time verification</td>
                                            <td className="px-6 py-4 text-sm">
                                                <span className="flex items-center gap-2">
                                                    <span className="w-2 h-2 bg-amber-400 rounded-full shadow-lg shadow-amber-400/50"></span>
                                                    <span className="text-slate-300">Open</span>
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-xs font-mono text-slate-500">—</td>
                                        </tr>
                                        <tr className="border-b border-white/5">
                                            <td className="px-6 py-4 text-sm font-mono text-slate-300">ITAAC-5.2.01</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">Shared</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">BOP</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">Balance-of-plant turbine island seismic qualification</td>
                                            <td className="px-6 py-4 text-sm">
                                                <span className="flex items-center gap-2">
                                                    <span className="w-2 h-2 bg-red-400 rounded-full shadow-lg shadow-red-400/50"></span>
                                                    <span className="text-slate-300">Blocked</span>
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-xs font-mono text-slate-500">—</td>
                                        </tr>
                                        <tr>
                                            <td className="px-6 py-4 text-sm font-mono text-slate-300">ITAAC-6.1.03</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">NPM-03</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">I&C</td>
                                            <td className="px-6 py-4 text-sm text-slate-400">Module protection system independence verification</td>
                                            <td className="px-6 py-4 text-sm">
                                                <span className="flex items-center gap-2">
                                                    <span className="w-2 h-2 bg-amber-400 rounded-full shadow-lg shadow-amber-400/50"></span>
                                                    <span className="text-slate-300">Open</span>
                                                </span>
                                            </td>
                                            <td className="px-6 py-4 text-xs font-mono text-slate-500">—</td>
                                        </tr>
                                    </tbody>
                                </table>
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
                            colorScheme="emerald"
                        />
                    )}

                    {activeTab === 'quickstart' && (
                        <div className="space-y-8">
                            <div>
                                <h2 className="text-3xl font-bold text-white mb-4">
                                    NRC-compliant records. 12 lines of code.
                                </h2>
                                <p className="text-lg text-slate-400 mb-8">
                                    Create your first NRC-compliant, immutable record in under 5 minutes.
                                    SDKs for Python, Node.js, and Go. Full OpenAPI spec.
                                </p>
                            </div>

                            <CodePlayground
                                title="Try It Live - ITAAC Evidence Creation"
                                description="Edit and run this code to create an immutable NRC-compliant evidence record"
                                initialCode={`import regengine

client = regengine.Client(api_key="re_live_...")

# Create immutable evidence record for ITAAC closure
evidence = client.nuclear.create_evidence(
    regulation="10-CFR-52",
    itaac_id="ITAAC-2.1.01",
    module="NPM-01",
    system="RCS",
    description="Reactor coolant system pressure boundary integrity test",
    attachments=["test_report_RCS_001.pdf"],
    metadata={
        "test_pressure_psig": 2485,
        "acceptance_criteria": "No leakage detected at 1.25x design pressure",
        "inspector": "J. Martinez, PE",
        "nrc_resident_notified": True
    }
)

# Returns immutable record with cryptographic proof
print(evidence.hash)     # sha256:a3f8c9...d41e
print(evidence.chain_id)  # Merkle root for full audit trail
print(evidence.status)    # "pending_review" → "closed"`}
                                language="python"
                                height="500px"
                            />
                        </div>
                    )}

                    {activeTab === 'examples' && (
                        <div className="space-y-12">
                            <div>
                                <h2 className="text-3xl font-bold text-white mb-4">
                                    Code Examples
                                </h2>
                                <p className="text-lg text-slate-400">
                                    Real-world examples for nuclear compliance workflows.
                                </p>
                            </div>

                            <div className="grid md:grid-cols-3 gap-6">
                                <Link href="/docs/nuclear/quickstart" className="p-6 bg-white/5 rounded-lg border border-white/10 hover:border-emerald-500/30 hover:bg-white/[0.07] transition-all">
                                    <h3 className="text-lg font-semibold text-white mb-2">
                                        Quickstart (5 minutes)
                                    </h3>
                                    <p className="text-slate-400 text-sm">
                                        Create your first NRC-compliant record
                                    </p>
                                </Link>

                                <Link href="/docs/nuclear/inspection" className="p-6 bg-white/5 rounded-lg border border-white/10 hover:border-emerald-500/30 hover:bg-white/[0.07] transition-all">
                                    <h3 className="text-lg font-semibold text-white mb-2">
                                        NRC Inspection Readiness
                                    </h3>
                                    <p className="text-slate-400 text-sm">
                                        Cryptographically prove record integrity
                                    </p>
                                </Link>

                                <Link href="/docs/nuclear/legal-hold" className="p-6 bg-white/5 rounded-lg border border-white/10 hover:border-emerald-500/30 hover:bg-white/[0.07] transition-all">
                                    <h3 className="text-lg font-semibold text-white mb-2">
                                        Legal Hold & Discovery
                                    </h3>
                                    <p className="text-slate-400 text-sm">
                                        Preserve evidence for enforcement actions
                                    </p>
                                </Link>
                            </div>
                        </div>
                    )}
                </div>

                {/* White Paper Download Section */}
                <div className="bg-emerald-500/5 border-y border-emerald-500/20 py-16">
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
                                        Nuclear Compliance White Paper
                                    </h2>
                                    <p className="text-slate-300 mb-4">
                                        <strong>Automating 10 CFR Part 21 & Appendix B QA with Tamper-Evident Documentation</strong>
                                    </p>
                                    <p className="text-slate-400 mb-4 text-sm">
                                        39-page executive white paper: how tamper-evident Part 21 evidence chains prevent forced shutdowns
                                        ($24M per 12-day event) and accelerate license amendments (36 → 14 months). Includes modeled ROI
                                        for both legacy PWR and SMR deployments.
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
                <div className="bg-[#06090f] border-t border-slate-800 py-16">
                    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
                        <div className="relative overflow-hidden bg-gradient-to-r from-emerald-600 to-cyan-600 rounded-2xl p-12 text-center">
                            <div className="absolute inset-0 bg-[url('data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjAiIGhlaWdodD0iNjAiIHZpZXdCb3g9IjAgMCA2MCA2MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48ZyBmaWxsPSJub25lIiBmaWxsLXJ1bGU9ImV2ZW5vZGQiPjxnIGZpbGw9IiNmZmYiIGZpbGwtb3BhY2l0eT0iMC4wNSI+PHBhdGggZD0iTTM2IDM0djItMnptMCAwdi0yIDJ6bTAtMnYyLTJ6Ii8+PC9nPjwvZz48L3N2Zz4=')] opacity-20"></div>
                            <div className="relative">
                                <h2 className="text-3xl font-bold text-white mb-4">Ready to build?</h2>
                                <p className="text-xl text-emerald-100 mb-8">
                                    Get your API key and create your first NRC-compliant record in under 5 minutes.
                                </p>
                                <div className="flex flex-col sm:flex-row gap-4 justify-center">
                                    <Link
                                        href="/api-keys"
                                        className="px-8 py-4 bg-white text-emerald-600 rounded-lg font-semibold hover:bg-emerald-50 transition-colors shadow-lg"
                                    >
                                        Get Free API Key →
                                    </Link>
                                    <Link
                                        href="/verticals/nuclear/pricing"
                                        className="px-8 py-4 bg-white/10 text-white rounded-lg font-semibold hover:bg-white/20 transition-colors border border-white/20"
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
