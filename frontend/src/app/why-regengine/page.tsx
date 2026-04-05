import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Check,
    X,
    Zap,
    Code2,
    DollarSign,
    Lightbulb,
    Lock,
    CheckCircle,
    AlertCircle,
    ArrowRight,
    Workflow,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export const metadata: Metadata = {
    title: 'Why RegEngine | FSMA 204 Compliance Built Different',
    description: 'API-first, transparent pricing, 48-hour speed to compliance. See how RegEngine outpaces FoodLogiQ, SafetyChain, and legacy competitors.',
    openGraph: {
        title: 'Why RegEngine | FSMA 204 Compliance Built Different',
        description: 'API-first, transparent pricing, 48-hour speed to compliance. See how RegEngine outpaces FoodLogiQ, SafetyChain, and legacy competitors.',
        url: 'https://www.regengine.co/why-regengine',
        type: 'website',
    },
};

interface ComparisonRow {
    feature: string;
    regengine: boolean | string;
    foodlogiq: boolean | string;
    safetychain: boolean | string;
    reositrak: boolean | string;
}

const COMPARISON_DATA: ComparisonRow[] = [
    {
        feature: 'REST API + Webhooks',
        regengine: true,
        foodlogiq: false,
        safetychain: false,
        reositrak: false,
    },
    {
        feature: 'Transparent, Published Pricing',
        regengine: '$425/mo',
        foodlogiq: 'Contact sales',
        safetychain: 'Contact sales',
        reositrak: 'Contact sales',
    },
    {
        feature: '48-Hour Time to Compliance',
        regengine: true,
        foodlogiq: '6+ months',
        safetychain: '4-6 months',
        reositrak: '3-6 months',
    },
    {
        feature: 'All 7 FSMA 204 CTE Types',
        regengine: 'Full coverage',
        foodlogiq: '5 covered',
        safetychain: '6 covered',
        reositrak: '6 covered',
    },
    {
        feature: 'EPCIS 2.0 Native',
        regengine: true,
        foodlogiq: 'Conversion layer',
        safetychain: 'Conversion layer',
        reositrak: 'Conversion layer',
    },
    {
        feature: 'CSV Import + Mapping',
        regengine: true,
        foodlogiq: true,
        safetychain: true,
        reositrak: true,
    },
    {
        feature: 'Works with Existing ERP/WMS',
        regengine: 'By design',
        foodlogiq: 'Limited',
        safetychain: 'Limited',
        reositrak: 'Limited',
    },
    {
        feature: 'Self-Serve Onboarding',
        regengine: true,
        foodlogiq: 'Sales-led only',
        safetychain: 'Sales-led only',
        reositrak: 'Sales-led only',
    },
    {
        feature: 'Per-CTE KDE Validation',
        regengine: true,
        foodlogiq: 'Batch only',
        safetychain: 'Batch only',
        reositrak: 'Batch only',
    },
    {
        feature: 'FDA-Ready Export',
        regengine: true,
        foodlogiq: true,
        safetychain: true,
        reositrak: true,
    },
    {
        feature: 'Recall Drill Workflows',
        regengine: true,
        foodlogiq: true,
        safetychain: true,
        reositrak: false,
    },
    {
        feature: 'No Long-Term Contracts',
        regengine: true,
        foodlogiq: false,
        safetychain: false,
        reositrak: false,
    },
];

const DIFFERENTIATORS = [
    {
        icon: Code2,
        title: 'API-First Architecture',
        description:
            'REST APIs, webhooks, and CSV templates. Integrate RegEngine with your existing ERP, WMS, or custom systems. No rip-and-replace required.',
        detail: 'Technical teams can be live in hours. Sales ops teams use our CSV templates. Everyone gets FSMA 204 compliance their way.',
    },
    {
        icon: DollarSign,
        title: 'Transparent Pricing',
        description:
            'No hidden sales calls. $425/mo for Design Partners. $999/mo for standard GA customers. You know the cost before you sign up.',
        detail: 'Compare directly to competitors who make you "contact sales." We believe pricing transparency builds trust and moves faster.',
    },
    {
        icon: Zap,
        title: '48-Hour Time to Compliance',
        description:
            'First FDA-ready CTE export in two days. Competitors take 3–6 months. Speed matters when your supply chain stops for recalls.',
        detail: 'No custom integrations needed. CSV upload or API payload → validation → compliance export. Lean, iterative, fast.',
    },
    {
        icon: Lock,
        title: 'Full CTE/KDE Coverage',
        description:
            'All 7 FSMA 204 CTE types. Per-CTE KDE validation (not batch). Missing CTEs are the #1 reason FDA recalls fail.',
        detail: 'Every field in every CTE type is validated individually. No surprises on FDA submission day.',
    },
    {
        icon: Workflow,
        title: 'EPCIS 2.0 Native',
        description:
            "FDA's preferred standard, baked in. No conversion layer. No data loss in transformation. Your data stays clean.",
        detail: 'Competitors bolt EPCIS on top of legacy schemas. We built EPCIS 2.0 first, then added everything else.',
    },
    {
        icon: CheckCircle,
        title: 'Built for SMBs',
        description:
            'Not enterprise-only. Small produce distributors, regional suppliers, emerging brands. Self-serve signup, no minimum spend.',
        detail: 'You don\'t need a 50-person implementation team. You need FSMA 204 compliance fast, cheaply, and without bureaucracy.',
    },
];

export default function WhyRegEnginePage() {
    return (
        <main className="min-h-screen bg-[#0a0a0f]">
            {/* Hero Section */}
            <section className="border-b border-white/10 px-4 sm:px-6 py-16 sm:py-24">
                <div className="max-w-5xl mx-auto">
                    <div className="inline-flex items-center gap-2 mb-6">
                        <Badge variant="outline" className="bg-white/5 border-white/20 text-white">
                            Built Different
                        </Badge>
                    </div>
                    <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-white mb-6 leading-tight">
                        FSMA 204 Compliance,{' '}
                        <span className="text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-cyan-300">
                            Built for You
                        </span>
                    </h1>
                    <p className="text-lg sm:text-xl text-gray-300 mb-8 max-w-3xl leading-relaxed">
                        RegEngine is the only FSMA 204 platform with an API-first architecture, transparent pricing, and a 48-hour path to FDA-ready compliance. No 6-month implementations. No hidden costs. No vendor lock-in.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4">
                        <Button asChild size="lg" className="bg-blue-600 hover:bg-blue-700 text-white">
                            <Link href="/signup">
                                Start Free Trial
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Link>
                        </Button>
                        <Button asChild variant="outline" size="lg" className="border-white/20 text-white hover:bg-white/10">
                            <Link href="/pricing">
                                View Pricing
                            </Link>
                        </Button>
                    </div>
                </div>
            </section>

            {/* Differentiators Grid */}
            <section className="border-b border-white/10 px-4 sm:px-6 py-16 sm:py-24">
                <div className="max-w-6xl mx-auto">
                    <div className="mb-16 text-center">
                        <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
                            Six Reasons Teams Choose RegEngine
                        </h2>
                        <p className="text-gray-400 text-lg max-w-2xl mx-auto">
                            We built RegEngine for technical teams, ops managers, and founders who need compliance fast without compromise.
                        </p>
                    </div>

                    <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8">
                        {DIFFERENTIATORS.map((item, idx) => {
                            const Icon = item.icon;
                            return (
                                <div
                                    key={idx}
                                    className="group rounded-lg border border-white/10 bg-white/[0.02] p-6 hover:border-white/20 hover:bg-white/[0.05] transition-all"
                                >
                                    <div className="flex items-start gap-4">
                                        <div className="rounded-lg bg-blue-600/20 p-3 text-blue-400 group-hover:bg-blue-600/30 transition-colors">
                                            <Icon className="h-5 w-5" />
                                        </div>
                                        <div className="flex-1">
                                            <h3 className="text-lg font-semibold text-white mb-2">
                                                {item.title}
                                            </h3>
                                            <p className="text-sm text-gray-400 mb-3">
                                                {item.description}
                                            </p>
                                            <p className="text-xs text-gray-500">
                                                {item.detail}
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            </section>

            {/* Comparison Section */}
            <section className="border-b border-white/10 px-4 sm:px-6 py-16 sm:py-24">
                <div className="max-w-7xl mx-auto">
                    <div className="mb-12 text-center">
                        <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
                            Feature-by-Feature Comparison
                        </h2>
                        <p className="text-gray-400 text-lg max-w-2xl mx-auto">
                            See how RegEngine stacks up against the industry standard and legacy competitors.
                        </p>
                    </div>

                    <div className="overflow-x-auto">
                        <table className="w-full border-collapse">
                            <thead>
                                <tr className="border-b border-white/10">
                                    <th className="text-left py-4 px-4 font-semibold text-white">
                                        Feature
                                    </th>
                                    <th className="text-center py-4 px-4 font-semibold text-blue-400">
                                        RegEngine
                                    </th>
                                    <th className="text-center py-4 px-4 font-semibold text-gray-400">
                                        FoodLogiQ
                                    </th>
                                    <th className="text-center py-4 px-4 font-semibold text-gray-400">
                                        SafetyChain
                                    </th>
                                    <th className="text-center py-4 px-4 font-semibold text-gray-400">
                                        ReposiTrak
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {COMPARISON_DATA.map((row, idx) => (
                                    <tr
                                        key={idx}
                                        className="border-b border-white/5 hover:bg-white/[0.02] transition-colors"
                                    >
                                        <td className="py-4 px-4 text-white font-medium text-sm">
                                            {row.feature}
                                        </td>
                                        <td className="text-center py-4 px-4">
                                            {typeof row.regengine === 'boolean' ? (
                                                row.regengine ? (
                                                    <Check className="h-5 w-5 text-green-400 mx-auto" />
                                                ) : (
                                                    <X className="h-5 w-5 text-red-400 mx-auto" />
                                                )
                                            ) : (
                                                <span className="text-xs text-gray-300 font-medium">
                                                    {row.regengine}
                                                </span>
                                            )}
                                        </td>
                                        <td className="text-center py-4 px-4">
                                            {typeof row.foodlogiq === 'boolean' ? (
                                                row.foodlogiq ? (
                                                    <Check className="h-5 w-5 text-green-400 mx-auto" />
                                                ) : (
                                                    <X className="h-5 w-5 text-red-400 mx-auto" />
                                                )
                                            ) : (
                                                <span className="text-xs text-gray-400">
                                                    {row.foodlogiq}
                                                </span>
                                            )}
                                        </td>
                                        <td className="text-center py-4 px-4">
                                            {typeof row.safetychain === 'boolean' ? (
                                                row.safetychain ? (
                                                    <Check className="h-5 w-5 text-green-400 mx-auto" />
                                                ) : (
                                                    <X className="h-5 w-5 text-red-400 mx-auto" />
                                                )
                                            ) : (
                                                <span className="text-xs text-gray-400">
                                                    {row.safetychain}
                                                </span>
                                            )}
                                        </td>
                                        <td className="text-center py-4 px-4">
                                            {typeof row.reositrak === 'boolean' ? (
                                                row.reositrak ? (
                                                    <Check className="h-5 w-5 text-green-400 mx-auto" />
                                                ) : (
                                                    <X className="h-5 w-5 text-red-400 mx-auto" />
                                                )
                                            ) : (
                                                <span className="text-xs text-gray-400">
                                                    {row.reositrak}
                                                </span>
                                            )}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <div className="mt-8 p-4 rounded-lg border border-blue-500/20 bg-blue-500/10 flex gap-3">
                        <AlertCircle className="h-5 w-5 text-blue-400 flex-shrink-0 mt-0.5" />
                        <p className="text-sm text-blue-200">
                            <strong>Note:</strong> Comparison data is current as of April 2026 and based on public pricing, documentation, and customer interviews. Competitor features change; if you spot an error, email{' '}
                            <a
                                href="mailto:support@regengine.co"
                                className="underline hover:text-blue-100"
                            >
                                support@regengine.co
                            </a>
                            .
                        </p>
                    </div>
                </div>
            </section>

            {/* Detailed Differentiator Sections */}
            <section className="border-b border-white/10 px-4 sm:px-6 py-16 sm:py-24">
                <div className="max-w-5xl mx-auto space-y-16">
                    {/* API-First */}
                    <div className="grid md:grid-cols-2 gap-8 items-center">
                        <div>
                            <h3 className="text-2xl sm:text-3xl font-bold text-white mb-4">
                                API-First, Not UI-Only
                            </h3>
                            <p className="text-gray-300 mb-4 leading-relaxed">
                                Every feature in RegEngine has an API. REST endpoints. Webhooks for real-time events. CSV templates for ops teams. Your developers can integrate in hours, not months.
                            </p>
                            <p className="text-gray-400 text-sm mb-6">
                                Competitors built UI-first, then bolted APIs on as an afterthought. We started with APIs. Your systems stay in control.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'Full REST API for CTEs, suppliers, compliance status',
                                    'Event webhooks for recall triggers and compliance alerts',
                                    'CSV import with smart field mapping',
                                    'Native integrations with Shopify, WooCommerce (coming soon)',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-sm text-gray-300">
                                        <Check className="h-5 w-5 text-green-400 flex-shrink-0" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                        <div className="hidden md:block rounded-lg border border-white/10 bg-white/[0.02] p-6">
                            <code className="text-xs text-gray-300 font-mono leading-relaxed block">
                                {`POST /api/ctes
Content-Type: application/json

{
  "traceability_lot_code": "LOT-2026-001",
  "product": "Organic spinach",
  "supplier_gln": "5012345678909",
  "received_date": "2026-04-05",
  "location_gln": "5012345678909"
}

HTTP 201
{
  "cte_id": "cte_abc123def456",
  "status": "validated",
  "missing_kdes": []
}`}
                            </code>
                        </div>
                    </div>

                    {/* Pricing */}
                    <div className="grid md:grid-cols-2 gap-8 items-center">
                        <div className="order-2 md:order-1 hidden md:block rounded-lg border border-white/10 bg-white/[0.02] p-8">
                            <div className="space-y-4">
                                <div className="rounded-lg bg-blue-600/20 p-4 border border-blue-500/30">
                                    <p className="text-sm text-gray-400 mb-1">Base Plan</p>
                                    <p className="text-3xl font-bold text-white">$425/mo</p>
                                    <p className="text-xs text-gray-400 mt-2">For design partners • 1 facility • 500 CTEs/mo</p>
                                </div>
                                <div className="rounded-lg bg-white/5 p-4 border border-white/10">
                                    <p className="text-sm text-gray-400 mb-1">Standard Plan</p>
                                    <p className="text-3xl font-bold text-white">$999/mo</p>
                                    <p className="text-xs text-gray-400 mt-2">General availability • 2–3 facilities • Unlimited CTEs</p>
                                </div>
                                <div className="rounded-lg bg-white/5 p-4 border border-white/10">
                                    <p className="text-sm text-gray-400 mb-1">Enterprise</p>
                                    <p className="text-xl font-bold text-white">Custom pricing</p>
                                    <p className="text-xs text-gray-400 mt-2">10+ facilities • Dedicated support</p>
                                </div>
                            </div>
                        </div>
                        <div className="order-1 md:order-2">
                            <h3 className="text-2xl sm:text-3xl font-bold text-white mb-4">
                                Pricing You Can See Before You Sign
                            </h3>
                            <p className="text-gray-300 mb-4 leading-relaxed">
                                Open pricing builds trust. We list prices on our website. No "contact sales" gatekeeping. No surprise enterprise minimums.
                            </p>
                            <p className="text-gray-400 text-sm mb-6">
                                Design partners lock in 50% off forever. Standard GA customers start at $999/mo. Honest pricing for honest work.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'Month-to-month billing, no long-term contracts',
                                    'Free API access across all plans',
                                    'Volume discounts for 10+ facilities',
                                    'Founding team pricing locked in for life',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-sm text-gray-300">
                                        <Check className="h-5 w-5 text-green-400 flex-shrink-0" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>

                    {/* Speed */}
                    <div className="grid md:grid-cols-2 gap-8 items-center">
                        <div>
                            <h3 className="text-2xl sm:text-3xl font-bold text-white mb-4">
                                48 Hours to FDA-Ready Compliance
                            </h3>
                            <p className="text-gray-300 mb-4 leading-relaxed">
                                When a recall hits, every hour matters. RegEngine gets you from zero to first CTE export in 48 hours. No integration services. No custom dev. Just upload, validate, export.
                            </p>
                            <p className="text-gray-400 text-sm mb-6">
                                Competitors average 3–6 months to first export. Your supply chain can't wait that long.
                            </p>
                            <div className="space-y-3">
                                {[
                                    { step: '1', label: 'Sign up, create a facility' },
                                    { step: '2', label: 'Upload your CTEs (CSV or API)' },
                                    { step: '3', label: 'RegEngine validates all KDEs' },
                                    { step: '4', label: 'Export FDA-ready trace data' },
                                ].map((item) => (
                                    <div key={item.step} className="flex gap-4 items-start">
                                        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-blue-600/30 border border-blue-500/50 text-sm font-semibold text-blue-300">
                                            {item.step}
                                        </div>
                                        <p className="text-gray-300 pt-1">{item.label}</p>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="rounded-lg border border-white/10 bg-gradient-to-br from-blue-600/10 to-transparent p-8">
                            <div className="text-center">
                                <p className="text-sm text-gray-400 mb-2">Typical Implementation Time</p>
                                <div className="space-y-4">
                                    <div>
                                        <p className="text-2xl font-bold text-green-400 mb-1">48 hours</p>
                                        <p className="text-xs text-gray-400">RegEngine</p>
                                    </div>
                                    <div className="h-px bg-white/10" />
                                    <div>
                                        <p className="text-2xl font-bold text-gray-400 mb-1">4–6 months</p>
                                        <p className="text-xs text-gray-500">FoodLogiQ, SafetyChain</p>
                                    </div>
                                    <div>
                                        <p className="text-2xl font-bold text-gray-400 mb-1">3–6 months</p>
                                        <p className="text-xs text-gray-500">ReposiTrak, Legacy systems</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>

                    {/* CTE Coverage */}
                    <div className="grid md:grid-cols-2 gap-8 items-center">
                        <div className="order-2 md:order-1 rounded-lg border border-white/10 bg-white/[0.02] p-8">
                            <h4 className="text-sm font-semibold text-gray-300 mb-6">All 7 FSMA 204 CTE Types</h4>
                            <div className="space-y-3">
                                {[
                                    'Produce Traceability Lot Code (TLC)',
                                    'Product Produce Traceability CTE',
                                    'Harvester Traceability CTE',
                                    'Processor Traceability CTE',
                                    'Transporter Traceability CTE',
                                    'Receiver Traceability CTE',
                                    'Commodity Traceability CTE',
                                ].map((item, idx) => (
                                    <div key={idx} className="flex gap-2">
                                        <Check className="h-4 w-4 text-green-400 flex-shrink-0 mt-0.5" />
                                        <span className="text-xs text-gray-300">{item}</span>
                                    </div>
                                ))}
                            </div>
                        </div>
                        <div className="order-1 md:order-2">
                            <h3 className="text-2xl sm:text-3xl font-bold text-white mb-4">
                                Complete CTE/KDE Coverage
                            </h3>
                            <p className="text-gray-300 mb-4 leading-relaxed">
                                All 7 FSMA 204 CTE types, fully implemented. Every field validated individually (not batch). Missing CTEs are the #1 reason FDA compliance fails.
                            </p>
                            <p className="text-gray-400 text-sm mb-6">
                                FoodLogiQ and SafetyChain cover 5–6 CTEs. ReposiTrak covers 6. RegEngine covers all 7, plus per-CTE KDE validation that catches errors before FDA submission.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'Per-CTE key data element validation',
                                    'Supplier relationship mapping across all CTEs',
                                    'Location traceability from source to receiver',
                                    'FDA 204 naming conventions built in',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-sm text-gray-300">
                                        <Check className="h-5 w-5 text-green-400 flex-shrink-0" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>

                    {/* EPCIS */}
                    <div className="grid md:grid-cols-2 gap-8 items-center">
                        <div>
                            <h3 className="text-2xl sm:text-3xl font-bold text-white mb-4">
                                EPCIS 2.0 Native
                            </h3>
                            <p className="text-gray-300 mb-4 leading-relaxed">
                                FDA's preferred format. We built EPCIS 2.0 first, then added everything else. No conversion layer. No data loss. Clean exports every time.
                            </p>
                            <p className="text-gray-400 text-sm mb-6">
                                Competitors grafted EPCIS onto legacy schemas. We started fresh. Your compliance data is pristine from day one.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'EPCIS 2.0 XML + JSON serialization',
                                    'FDA traceability event format',
                                    'No third-party conversion needed',
                                    'Future-proof for FDA infrastructure upgrades',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-sm text-gray-300">
                                        <Check className="h-5 w-5 text-green-400 flex-shrink-0" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                        <div className="hidden md:block rounded-lg border border-white/10 bg-white/[0.02] p-6">
                            <code className="text-xs text-gray-300 font-mono leading-relaxed block overflow-auto">
                                {`<events>
  <EPCISEvent>
    <eventTime>2026-04-05T...</eventTime>
    <eventType>
      ObjectEvent
    </eventType>
    <epcList>
      <epc>
        urn:epc:id:sgtin:...
      </epc>
    </epcList>
    <action>OBSERVE</action>
    <bizStep>
      urn:epcglobal:cbv:bizstep:...
    </bizStep>
  </EPCISEvent>
</events>`}
                            </code>
                        </div>
                    </div>

                    {/* SMB Focus */}
                    <div className="grid md:grid-cols-2 gap-8 items-center">
                        <div className="order-2 md:order-1 rounded-lg border border-white/10 bg-white/[0.02] p-8">
                            <p className="text-sm text-gray-400 mb-4">RegEngine is built for companies like:</p>
                            <ul className="space-y-2">
                                {[
                                    'Regional produce distributors ($5M–$50M ARR)',
                                    'Specialty food brands and co-packers',
                                    'Organic/specialty retailers and wholesalers',
                                    'Small farms and grower cooperatives',
                                    'Emerging CPG brands reaching FDA compliance',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-2 text-xs text-gray-300">
                                        <Check className="h-4 w-4 text-green-400 flex-shrink-0 mt-0.5" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                        <div className="order-1 md:order-2">
                            <h3 className="text-2xl sm:text-3xl font-bold text-white mb-4">
                                Built for SMBs, Not Enterprises Only
                            </h3>
                            <p className="text-gray-300 mb-4 leading-relaxed">
                                Compliance shouldn't require a 50-person implementation team. You need FSMA 204 compliance, fast and cheap. Self-serve signup, no minimums, no sales calls.
                            </p>
                            <p className="text-gray-400 text-sm mb-6">
                                Legacy platforms built for 100+ facility enterprises. RegEngine scales from 1 facility to 1000. You start small; you grow without ripping out the platform.
                            </p>
                            <ul className="space-y-2">
                                {[
                                    'Self-serve signup, free trial included',
                                    'No implementation services required',
                                    'Scales from 1 to 10,000 facilities',
                                    'Email + Slack support for all plans',
                                ].map((item, idx) => (
                                    <li key={idx} className="flex gap-3 text-sm text-gray-300">
                                        <Check className="h-5 w-5 text-green-400 flex-shrink-0" />
                                        <span>{item}</span>
                                    </li>
                                ))}
                            </ul>
                        </div>
                    </div>
                </div>
            </section>

            {/* Honest Positioning */}
            <section className="border-b border-white/10 px-4 sm:px-6 py-16 sm:py-24">
                <div className="max-w-4xl mx-auto">
                    <div className="rounded-lg border border-white/10 bg-white/[0.02] p-8 sm:p-12">
                        <h2 className="text-3xl font-bold text-white mb-4">
                            What RegEngine Is NOT
                        </h2>
                        <p className="text-gray-300 mb-8">
                            RegEngine is a compliance layer, not a replacement for your ERP or WMS. We work alongside your existing systems, filling the traceability gaps that packaged software doesn't solve.
                        </p>
                        <div className="space-y-4">
                            {[
                                {
                                    title: 'We are NOT an ERP replacement',
                                    detail: 'Your inventory, financials, and order management stay in Shopify, NetSuite, or QuickBooks. RegEngine handles traceability.',
                                },
                                {
                                    title: 'We are NOT a supply chain analytics platform',
                                    detail: 'We focus on compliance validation and FDA-ready exports. Advanced forecasting and sourcing tools live elsewhere.',
                                },
                                {
                                    title: 'We do NOT promise 100% FDA audit success',
                                    detail: 'Compliance is a process, not a product. We validate data and generate FDA exports. Audits require auditors.',
                                },
                                {
                                    title: 'We do NOT lock you in',
                                    detail: 'Month-to-month billing. Export all your data anytime. Your data is yours.',
                                },
                            ].map((item, idx) => (
                                <div key={idx} className="flex gap-4">
                                    <div className="flex h-6 w-6 items-center justify-center rounded-full bg-amber-600/30 border border-amber-500/50 flex-shrink-0 mt-0.5">
                                        <AlertCircle className="h-3 w-3 text-amber-300" />
                                    </div>
                                    <div>
                                        <p className="font-semibold text-white">{item.title}</p>
                                        <p className="text-sm text-gray-400">{item.detail}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* Social Proof / Industry Fit */}
            <section className="border-b border-white/10 px-4 sm:px-6 py-16 sm:py-24">
                <div className="max-w-4xl mx-auto text-center">
                    <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
                        Who's RegEngine For?
                    </h2>
                    <p className="text-gray-300 text-lg mb-12 max-w-2xl mx-auto">
                        If you fit any of these categories, RegEngine is built for you.
                    </p>
                    <div className="grid sm:grid-cols-2 gap-6">
                        {[
                            {
                                emoji: '🔧',
                                title: 'Technical Buyers',
                                detail: 'Your team owns integrations. You want APIs, webhooks, and source control. RegEngine gives you that.',
                            },
                            {
                                emoji: '👔',
                                title: 'Operations Teams',
                                detail: 'You need FSMA 204 compliance done quickly. CSV upload is fast enough. No custom dev needed.',
                            },
                            {
                                emoji: '🚀',
                                title: 'Founders & SMBs',
                                detail: 'You need compliance but can\'t afford enterprise fees. $425/mo gets you live. Scale as you grow.',
                            },
                            {
                                emoji: '⚖️',
                                title: 'Compliance Officers',
                                detail: 'You need per-CTE validation and FDA-ready exports. RegEngine gives you audit trails and evidence.',
                            },
                        ].map((item, idx) => (
                            <div
                                key={idx}
                                className="rounded-lg border border-white/10 bg-white/[0.02] p-6 hover:border-white/20 hover:bg-white/[0.05] transition-all"
                            >
                                <div className="text-4xl mb-3">{item.emoji}</div>
                                <h3 className="text-lg font-semibold text-white mb-2">
                                    {item.title}
                                </h3>
                                <p className="text-sm text-gray-400">{item.detail}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA Section */}
            <section className="px-4 sm:px-6 py-16 sm:py-24">
                <div className="max-w-4xl mx-auto text-center">
                    <h2 className="text-3xl sm:text-4xl font-bold text-white mb-4">
                        Ready to Get Compliant?
                    </h2>
                    <p className="text-gray-300 text-lg mb-8 max-w-2xl mx-auto">
                        Sign up in minutes. First 30 days are free. No credit card required. No long-term contracts.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Button asChild size="lg" className="bg-blue-600 hover:bg-blue-700 text-white">
                            <Link href="/signup">
                                Start Free Trial
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Link>
                        </Button>
                        <Button asChild variant="outline" size="lg" className="border-white/20 text-white hover:bg-white/10">
                            <Link href="/contact">
                                Talk to Us
                            </Link>
                        </Button>
                        <Button asChild variant="outline" size="lg" className="border-white/20 text-white hover:bg-white/10">
                            <Link href="/pricing">
                                View Pricing
                            </Link>
                        </Button>
                    </div>
                    <p className="text-sm text-gray-500 mt-8">
                        Questions? Email{' '}
                        <a href="mailto:support@regengine.co" className="text-gray-400 hover:text-white underline">
                            support@regengine.co
                        </a>
                        {' '}or join our{' '}
                        <a href="https://slack.regengine.co" className="text-gray-400 hover:text-white underline" target="_blank" rel="noopener noreferrer">
                            community Slack
                        </a>
                        .
                    </p>
                </div>
            </section>
        </main>
    );
}
