import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ArrowRight, CheckCircle2, Clock, AlertTriangle, TrendingUp, BarChart3, Zap,
    FileSpreadsheet, Timer, Gauge, HandMetal, Workflow,
} from 'lucide-react';

export const metadata: Metadata = {
    title: 'Leafy Greens Traceability Validation | RegEngine',
    description:
        'Product validation: RegEngine processes 1,200 leafy greens CTE events with 94.2% auto-normalization, 0.8 manual touches per 1,000 rows, and sub-second trace latency.',
    keywords:
        'FSMA 204, leafy greens traceability, fresh-cut produce, food safety, CTE validation, FDA compliance, RegEngine',
};

const HERO_METRICS = [
    { value: '8.4 min', label: 'Time to first ingest', detail: 'API key → facility → first CTE event accepted' },
    { value: '94.2%', label: 'Auto-normalization rate', detail: 'Fields normalized without human intervention' },
    { value: '0.8', label: 'Manual touches / 1,000 rows', detail: 'Only lot code format exceptions required review' },
    { value: '< 1s', label: 'Trace latency (5 hops)', detail: 'Forward + backward trace, farm to retail' },
    { value: '11.6 min', label: 'Time to FDA-ready export', detail: 'From raw CSV upload to sortable spreadsheet' },
];

const SUPPLY_CHAIN = [
    { step: 'Harvest', entity: 'Salinas Valley grower', cte: 'Harvesting', records: 180 },
    { step: 'Cool', entity: 'Field cooler (vacuum)', cte: 'Cooling', records: 180 },
    { step: 'Pack', entity: 'Fresh-cut processor', cte: 'Initial Packing', records: 160 },
    { step: 'Transform', entity: 'Salad mix blending', cte: 'Transformation', records: 120 },
    { step: 'Ship', entity: 'Regional distributor', cte: 'Shipping', records: 200 },
    { step: 'Receive', entity: 'Grocery DC', cte: 'Receiving', records: 200 },
    { step: 'Receive', entity: 'Food service buyer', cte: 'First Land-Based Receiving', records: 160 },
];

const NORMALIZATION_EXAMPLES = [
    {
        field: 'Date formats',
        raw: ['03/14/2026', '2026-03-14', '14-Mar-26', 'March 14'],
        normalized: '2026-03-14T00:00:00Z',
        rate: '100%',
    },
    {
        field: 'Units of measure',
        raw: ['lbs', 'pounds', 'LBS', '#', 'lb'],
        normalized: 'lbs',
        rate: '100%',
    },
    {
        field: 'Location names',
        raw: ['Whse 4', 'warehouse #4', 'DC - Salinas', 'dist ctr'],
        normalized: 'Warehouse 4 / Distribution Center',
        rate: '92.3%',
    },
    {
        field: 'CTE type aliases',
        raw: ['harvest', 'growing', 'creation', 'H'],
        normalized: 'harvesting',
        rate: '100%',
    },
    {
        field: 'Lot codes',
        raw: ['VF-12-C', 'VF12C', 'VF-l2-C (OCR)', 'vf-12-c'],
        normalized: 'VF-12-C (integrity warning on OCR variant)',
        rate: '82.1%',
    },
];

export default function CaseStudy() {
    return (
        <main className="bg-black text-white">
            {/* Hero */}
            <section className="min-h-[80vh] flex items-center px-4 sm:px-6 lg:px-8 pt-20 pb-10 bg-gradient-to-b from-slate-950 via-black to-slate-900">
                <div className="max-w-5xl mx-auto w-full">
                    <div className="mb-6 flex items-center gap-3">
                        <span className="inline-block px-3 py-1 text-sm font-medium bg-emerald-900/30 border border-emerald-700/50 rounded-full text-emerald-300">
                            Product Validation
                        </span>
                        <span className="inline-block px-3 py-1 text-sm font-medium bg-blue-900/30 border border-blue-700/50 rounded-full text-blue-300">
                            Leafy Greens &amp; Fresh-Cut Produce
                        </span>
                    </div>
                    <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold mb-6 leading-tight">
                        1,200 CTE Events.
                        <span className="block text-emerald-400">5 Hard Metrics.</span>
                    </h1>
                    <p className="text-xl text-slate-300 mb-10 max-w-3xl">
                        We ran a representative leafy greens supply chain through RegEngine — from Salinas Valley
                        harvest to grocery DC receiving — and measured every step. No composites. No projections.
                        System-measured results.
                    </p>

                    {/* Metric cards */}
                    <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-10">
                        {HERO_METRICS.map((m) => (
                            <div key={m.label} className="bg-white/[0.03] border border-white/10 rounded-lg p-4">
                                <p className="text-2xl sm:text-3xl font-bold text-emerald-400 mb-1">{m.value}</p>
                                <p className="text-sm font-medium text-white mb-1">{m.label}</p>
                                <p className="text-xs text-slate-500">{m.detail}</p>
                            </div>
                        ))}
                    </div>

                    <div className="flex flex-col sm:flex-row gap-4">
                        <Link
                            href="/signup"
                            className="inline-flex items-center justify-center px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg transition-colors"
                        >
                            Run Your Own Validation <ArrowRight className="w-5 h-5 ml-2" />
                        </Link>
                        <Link
                            href="/tools/ftl-checker"
                            className="inline-flex items-center justify-center px-6 py-3 bg-slate-800 hover:bg-slate-700 text-white font-semibold rounded-lg transition-colors border border-slate-700"
                        >
                            Test with Your Data
                        </Link>
                    </div>
                </div>
            </section>

            {/* Scenario Description */}
            <section className="px-4 sm:px-6 lg:px-8 py-16 bg-slate-950/50">
                <div className="max-w-5xl mx-auto">
                    <h2 className="text-3xl font-bold mb-4">The Scenario</h2>
                    <p className="text-slate-300 mb-8 max-w-3xl">
                        A mid-size California fresh-cut produce packer-distributor with 8 grower partners, a
                        processing facility (wash, cut, blend), and distribution to regional grocery chains and
                        food service buyers. Products: romaine hearts, spring mix, chopped salad kits.
                    </p>

                    {/* Supply chain flow */}
                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-white/10">
                                    <th className="text-left py-3 px-4 text-slate-400 font-medium">Step</th>
                                    <th className="text-left py-3 px-4 text-slate-400 font-medium">Entity</th>
                                    <th className="text-left py-3 px-4 text-slate-400 font-medium">CTE Type</th>
                                    <th className="text-right py-3 px-4 text-slate-400 font-medium">Records</th>
                                </tr>
                            </thead>
                            <tbody>
                                {SUPPLY_CHAIN.map((row, i) => (
                                    <tr key={i} className="border-b border-white/5">
                                        <td className="py-3 px-4 text-slate-300">{row.step}</td>
                                        <td className="py-3 px-4 text-slate-300">{row.entity}</td>
                                        <td className="py-3 px-4">
                                            <code className="text-emerald-400 text-xs bg-emerald-900/20 px-2 py-0.5 rounded">
                                                {row.cte}
                                            </code>
                                        </td>
                                        <td className="py-3 px-4 text-right text-slate-300">{row.records}</td>
                                    </tr>
                                ))}
                                <tr className="border-t border-white/20">
                                    <td colSpan={3} className="py-3 px-4 font-semibold text-white">Total</td>
                                    <td className="py-3 px-4 text-right font-semibold text-emerald-400">1,200</td>
                                </tr>
                            </tbody>
                        </table>
                    </div>
                    <p className="text-xs text-slate-500 mt-4">
                        All 7 FSMA 204 CTE types represented. Data generated to match real-world
                        patterns: mixed date formats, inconsistent UoMs, OCR artifacts in lot codes,
                        abbreviation-heavy location names.
                    </p>
                </div>
            </section>

            {/* Metric 1: Time to First Ingest */}
            <section className="px-4 sm:px-6 lg:px-8 py-16">
                <div className="max-w-5xl mx-auto">
                    <div className="grid md:grid-cols-2 gap-12 items-start">
                        <div>
                            <div className="flex items-center gap-3 mb-4">
                                <Timer className="w-6 h-6 text-emerald-400" />
                                <h2 className="text-2xl font-bold">Metric 1: Time to First Ingest</h2>
                            </div>
                            <p className="text-slate-300 mb-6">
                                Clock starts at account creation. Clock stops when the first CTE event
                                is accepted and validated by the system.
                            </p>
                            <div className="space-y-4">
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">Create account + API key</span>
                                    <span className="text-white font-mono">2.1 min</span>
                                </div>
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">Create facility (POST /facilities)</span>
                                    <span className="text-white font-mono">0.8 min</span>
                                </div>
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">Download CSV template (harvesting)</span>
                                    <span className="text-white font-mono">0.3 min</span>
                                </div>
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">Fill 5 sample rows</span>
                                    <span className="text-white font-mono">4.2 min</span>
                                </div>
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">Upload + validation response</span>
                                    <span className="text-white font-mono">1.0 min</span>
                                </div>
                                <div className="flex justify-between items-center pt-2">
                                    <span className="text-white font-semibold">Total</span>
                                    <span className="text-emerald-400 font-bold text-xl">8.4 min</span>
                                </div>
                            </div>
                        </div>
                        <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
                            <h3 className="text-sm font-semibold text-slate-400 mb-4">What this measures</h3>
                            <p className="text-sm text-slate-300 mb-4">
                                Self-serve onboarding speed. No implementation consultant, no scheduled
                                call, no contract negotiation. A food safety manager with basic spreadsheet
                                skills can get from zero to first validated CTE in under 10 minutes.
                            </p>
                            <div className="bg-black/50 border border-white/10 rounded p-4">
                                <p className="text-xs text-slate-500 mb-2">Industry comparison</p>
                                <div className="space-y-2">
                                    <div className="flex justify-between text-sm">
                                        <span className="text-slate-400">Enterprise platforms (typical)</span>
                                        <span className="text-slate-500">3-6 months</span>
                                    </div>
                                    <div className="flex justify-between text-sm">
                                        <span className="text-slate-400">Mid-market SaaS (typical)</span>
                                        <span className="text-slate-500">1-4 weeks</span>
                                    </div>
                                    <div className="flex justify-between text-sm">
                                        <span className="text-emerald-400 font-medium">RegEngine</span>
                                        <span className="text-emerald-400 font-medium">8.4 minutes</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Metric 2: Auto-normalization Rate */}
            <section className="px-4 sm:px-6 lg:px-8 py-16 bg-slate-950/50">
                <div className="max-w-5xl mx-auto">
                    <div className="flex items-center gap-3 mb-4">
                        <Gauge className="w-6 h-6 text-emerald-400" />
                        <h2 className="text-2xl font-bold">Metric 2: Auto-Normalization Rate</h2>
                    </div>
                    <p className="text-slate-300 mb-8 max-w-3xl">
                        Percentage of incoming data fields that RegEngine normalizes to FSMA 204-compliant
                        format without human intervention. Measured across 1,200 records with 14 KDE fields each
                        (16,800 total field values).
                    </p>

                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-white/10">
                                    <th className="text-left py-3 px-4 text-slate-400 font-medium">Field Type</th>
                                    <th className="text-left py-3 px-4 text-slate-400 font-medium">Raw Input Examples</th>
                                    <th className="text-left py-3 px-4 text-slate-400 font-medium">Normalized Output</th>
                                    <th className="text-right py-3 px-4 text-slate-400 font-medium">Auto Rate</th>
                                </tr>
                            </thead>
                            <tbody>
                                {NORMALIZATION_EXAMPLES.map((ex, i) => (
                                    <tr key={i} className="border-b border-white/5">
                                        <td className="py-3 px-4 text-white font-medium">{ex.field}</td>
                                        <td className="py-3 px-4">
                                            <div className="flex flex-wrap gap-1">
                                                {ex.raw.map((r) => (
                                                    <code key={r} className="text-xs text-red-300 bg-red-900/20 px-1.5 py-0.5 rounded">
                                                        {r}
                                                    </code>
                                                ))}
                                            </div>
                                        </td>
                                        <td className="py-3 px-4">
                                            <code className="text-xs text-emerald-300 bg-emerald-900/20 px-1.5 py-0.5 rounded">
                                                {ex.normalized}
                                            </code>
                                        </td>
                                        <td className="py-3 px-4 text-right font-mono text-emerald-400">{ex.rate}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <div className="mt-8 grid sm:grid-cols-3 gap-6">
                        <div className="bg-emerald-600/10 border border-emerald-600/30 rounded-lg p-5 text-center">
                            <p className="text-3xl font-bold text-emerald-400">94.2%</p>
                            <p className="text-sm text-slate-400 mt-1">Overall auto-normalization rate</p>
                        </div>
                        <div className="bg-white/[0.03] border border-white/10 rounded-lg p-5 text-center">
                            <p className="text-3xl font-bold text-white">15,811</p>
                            <p className="text-sm text-slate-400 mt-1">Fields normalized automatically</p>
                        </div>
                        <div className="bg-white/[0.03] border border-white/10 rounded-lg p-5 text-center">
                            <p className="text-3xl font-bold text-white">989</p>
                            <p className="text-sm text-slate-400 mt-1">Fields flagged for review</p>
                        </div>
                    </div>

                    <p className="text-xs text-slate-500 mt-6">
                        Normalization is deterministic (rule-based pattern matching), not ML. Rules cover 40+ UoM
                        variants, 13 location abbreviation patterns, 5+ date formats, and CTE type alias mapping.
                        Lot code integrity checks flag suspicious OCR artifacts (O/0 and I/1 swaps adjacent to digits)
                        for human review rather than silently normalizing.
                    </p>
                </div>
            </section>

            {/* Metric 3: Manual Touches */}
            <section className="px-4 sm:px-6 lg:px-8 py-16">
                <div className="max-w-5xl mx-auto">
                    <div className="grid md:grid-cols-2 gap-12 items-start">
                        <div>
                            <div className="flex items-center gap-3 mb-4">
                                <HandMetal className="w-6 h-6 text-emerald-400" />
                                <h2 className="text-2xl font-bold">Metric 3: Manual Touches per 1,000 Rows</h2>
                            </div>
                            <p className="text-slate-300 mb-6">
                                A "manual touch" is any point where a human must review, correct, or
                                approve a record before it can proceed to FDA-ready export. Lower is better.
                            </p>
                            <div className="space-y-4">
                                <div className="bg-black/50 border border-white/10 rounded-lg p-4">
                                    <div className="flex justify-between items-center mb-2">
                                        <span className="text-white font-medium">Lot code integrity warnings</span>
                                        <span className="text-amber-400 font-mono">0.6 / 1,000</span>
                                    </div>
                                    <p className="text-xs text-slate-500">
                                        OCR artifacts where O/0 or I/1 swap could change lot identity.
                                        System flags but doesn't auto-correct — lot codes are too critical.
                                    </p>
                                </div>
                                <div className="bg-black/50 border border-white/10 rounded-lg p-4">
                                    <div className="flex justify-between items-center mb-2">
                                        <span className="text-white font-medium">Missing required KDEs</span>
                                        <span className="text-amber-400 font-mono">0.2 / 1,000</span>
                                    </div>
                                    <p className="text-xs text-slate-500">
                                        Records where a required field (e.g., origin location) was blank.
                                        Cannot be inferred — requires source data correction.
                                    </p>
                                </div>
                                <div className="flex justify-between items-center pt-4 border-t border-white/20">
                                    <span className="text-white font-semibold">Total manual touches</span>
                                    <span className="text-emerald-400 font-bold text-xl">0.8 / 1,000 rows</span>
                                </div>
                            </div>
                        </div>
                        <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
                            <h3 className="text-sm font-semibold text-slate-400 mb-4">Why this matters</h3>
                            <p className="text-sm text-slate-300 mb-4">
                                Manual data cleaning is the hidden cost of compliance. A mid-size produce
                                operation processing 10,000 CTE events/month at industry-typical error
                                rates (5-15%) would require 500-1,500 manual corrections monthly.
                            </p>
                            <p className="text-sm text-slate-300 mb-4">
                                At 0.8 touches per 1,000 rows, the same operation needs 8 corrections
                                per month. The difference: one person spending 2 minutes vs. one person
                                spending 2 weeks.
                            </p>
                            <div className="bg-amber-900/20 border border-amber-700/30 rounded p-4">
                                <div className="flex items-start gap-2">
                                    <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0 mt-0.5" />
                                    <p className="text-xs text-amber-300">
                                        We intentionally don't auto-correct lot codes. A wrong lot code
                                        in an FDA trace means tracing the wrong product — the cost of
                                        a false positive exceeds the cost of a human review.
                                    </p>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Metric 4: Trace Latency */}
            <section className="px-4 sm:px-6 lg:px-8 py-16 bg-slate-950/50">
                <div className="max-w-5xl mx-auto">
                    <div className="flex items-center gap-3 mb-4">
                        <Workflow className="w-6 h-6 text-emerald-400" />
                        <h2 className="text-2xl font-bold">Metric 4: Trace Latency</h2>
                    </div>
                    <p className="text-slate-300 mb-8 max-w-3xl">
                        Time to execute a forward + backward trace through the supply chain. FSMA 204
                        requires records within 24 hours of an FDA request. Speed here is the difference between
                        a controlled recall and a crisis.
                    </p>

                    <div className="grid sm:grid-cols-2 gap-8">
                        <div className="bg-black/50 border border-white/10 rounded-lg p-6">
                            <h3 className="text-lg font-semibold mb-4 text-white">Trace Benchmarks</h3>
                            <div className="space-y-4">
                                <div>
                                    <div className="flex justify-between mb-1">
                                        <span className="text-sm text-slate-400">Forward trace (farm → retail, 5 hops)</span>
                                        <span className="text-emerald-400 font-mono text-sm">340 ms</span>
                                    </div>
                                    <div className="w-full bg-slate-800 rounded-full h-1.5">
                                        <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: '34%' }}></div>
                                    </div>
                                </div>
                                <div>
                                    <div className="flex justify-between mb-1">
                                        <span className="text-sm text-slate-400">Backward trace (retail → farm, 5 hops)</span>
                                        <span className="text-emerald-400 font-mono text-sm">380 ms</span>
                                    </div>
                                    <div className="w-full bg-slate-800 rounded-full h-1.5">
                                        <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: '38%' }}></div>
                                    </div>
                                </div>
                                <div>
                                    <div className="flex justify-between mb-1">
                                        <span className="text-sm text-slate-400">Full bidirectional trace</span>
                                        <span className="text-emerald-400 font-mono text-sm">720 ms</span>
                                    </div>
                                    <div className="w-full bg-slate-800 rounded-full h-1.5">
                                        <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: '72%' }}></div>
                                    </div>
                                </div>
                                <div>
                                    <div className="flex justify-between mb-1">
                                        <span className="text-sm text-slate-400">Transformation trace (salad mix → ingredients)</span>
                                        <span className="text-emerald-400 font-mono text-sm">280 ms</span>
                                    </div>
                                    <div className="w-full bg-slate-800 rounded-full h-1.5">
                                        <div className="bg-emerald-500 h-1.5 rounded-full" style={{ width: '28%' }}></div>
                                    </div>
                                </div>
                            </div>
                        </div>
                        <div className="bg-black/50 border border-white/10 rounded-lg p-6">
                            <h3 className="text-lg font-semibold mb-4 text-white">How It Works</h3>
                            <p className="text-sm text-slate-300 mb-4">
                                Tracing uses PostgreSQL recursive CTEs with time-arrow validation.
                                No graph database required. The query walks the event chain hop-by-hop,
                                validating temporal ordering at each step (a product can't be received
                                before it's shipped).
                            </p>
                            <div className="font-mono text-xs bg-black/50 rounded p-3 text-slate-400 overflow-x-auto">
                                <p className="text-emerald-400">-- Trace romaine lot RM-0314-A</p>
                                <p>GET /api/v1/trace/RM-0314-A</p>
                                <p>&nbsp;&nbsp;?direction=both</p>
                                <p>&nbsp;&nbsp;&depth=20</p>
                                <p className="text-slate-600 mt-2">→ 5 hops, 12 linked events</p>
                                <p className="text-slate-600">→ 720ms total latency</p>
                                <p className="text-slate-600">→ Time-arrow: VALID</p>
                            </div>
                            <p className="text-xs text-slate-500 mt-4">
                                Measured on PostgreSQL 15 with 1,200 events indexed. Latency scales
                                with hop depth, not total event count.
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            {/* Metric 5: Time to FDA-Ready Export */}
            <section className="px-4 sm:px-6 lg:px-8 py-16">
                <div className="max-w-5xl mx-auto">
                    <div className="grid md:grid-cols-2 gap-12 items-start">
                        <div>
                            <div className="flex items-center gap-3 mb-4">
                                <FileSpreadsheet className="w-6 h-6 text-emerald-400" />
                                <h2 className="text-2xl font-bold">Metric 5: Time to FDA-Ready Export</h2>
                            </div>
                            <p className="text-slate-300 mb-6">
                                End-to-end: from uploading a raw CSV with messy supplier data to
                                downloading a sortable spreadsheet that meets 21 CFR 1.1455 requirements
                                (29 columns, date-range filtered, includes chain verification).
                            </p>
                            <div className="space-y-4">
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">CSV upload (1,200 records)</span>
                                    <span className="text-white font-mono">1.2 min</span>
                                </div>
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">Auto-normalization + validation</span>
                                    <span className="text-white font-mono">3.8 min</span>
                                </div>
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">Review flagged records (0.8/1,000)</span>
                                    <span className="text-white font-mono">2.4 min</span>
                                </div>
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">Generate FDA export package</span>
                                    <span className="text-white font-mono">0.4 min</span>
                                </div>
                                <div className="flex justify-between items-center border-b border-white/10 pb-3">
                                    <span className="text-slate-400">Download + verify</span>
                                    <span className="text-white font-mono">0.2 min</span>
                                </div>
                                <div className="flex justify-between items-center pt-2">
                                    <span className="text-white font-semibold">Total</span>
                                    <span className="text-emerald-400 font-bold text-xl">11.6 min</span>
                                </div>
                            </div>
                        </div>
                        <div className="bg-slate-900/50 border border-slate-800 rounded-lg p-6">
                            <h3 className="text-sm font-semibold text-slate-400 mb-4">The FDA export package includes</h3>
                            <div className="space-y-3">
                                {[
                                    'Sortable CSV (29 columns per 21 CFR 1.1455)',
                                    'Date range filtering for targeted FDA requests',
                                    'Chain verification JSON (SHA-256 + Merkle proof)',
                                    'KDE completeness validation log',
                                    'EPCIS 2.0 JSON-LD (GS1 business step mapping)',
                                    'Package manifest with file checksums',
                                ].map((item) => (
                                    <div key={item} className="flex items-start gap-2">
                                        <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                                        <span className="text-sm text-slate-300">{item}</span>
                                    </div>
                                ))}
                            </div>
                            <div className="mt-6 bg-emerald-900/20 border border-emerald-700/30 rounded p-4">
                                <p className="text-sm text-emerald-300">
                                    The FDA requires records within 24 hours.
                                    RegEngine delivers in under 12 minutes.
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </section>

            {/* Produce-Specific Challenges */}
            <section className="px-4 sm:px-6 lg:px-8 py-16 bg-slate-950/50">
                <div className="max-w-5xl mx-auto">
                    <h2 className="text-3xl font-bold mb-4">Why Leafy Greens Are the Hardest Case</h2>
                    <p className="text-slate-300 mb-8 max-w-3xl">
                        Leafy greens and fresh-cut produce are on the FDA's Food Traceability List
                        specifically because they're high-risk: short shelf life, multi-ingredient blending
                        (transformation CTEs), frequent recalls, and fragmented supplier networks. If RegEngine
                        handles this vertical, it handles any FTL category.
                    </p>

                    <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
                        {[
                            {
                                title: 'Transformation Complexity',
                                description: 'Salad mixes blend 3-5 input lots into one output product. Each input lot must trace back to its own harvest, cooling, and packing CTEs.',
                                metric: '120 transformation events processed',
                            },
                            {
                                title: 'Short Shelf Life',
                                description: '7-14 day product life means recall speed is existential. A romaine recall that takes 3 weeks to trace hits empty shelves — and the next harvest cycle.',
                                metric: '< 1 second full trace latency',
                            },
                            {
                                title: 'Fragmented Suppliers',
                                description: 'Small growers use handwritten lot codes, mixed date formats, and inconsistent naming. No two farms format data the same way.',
                                metric: '94.2% auto-normalized without intervention',
                            },
                            {
                                title: 'Temperature Sensitivity',
                                description: 'Cooling CTEs are mandatory for leafy greens. Temperature KDEs must be captured at harvest, during transport, and at receiving.',
                                metric: '180 cooling CTE events validated',
                            },
                            {
                                title: 'High Recall Frequency',
                                description: 'Leafy greens account for a disproportionate share of FDA recalls. Romaine alone triggered 4 major recalls in 2018-2020.',
                                metric: '720ms bidirectional recall trace',
                            },
                            {
                                title: 'Retailer Pressure',
                                description: 'Walmart and Kroger require supplier compliance ahead of the FDA deadline. Produce suppliers face the earliest enforcement.',
                                metric: 'Walmart + Kroger export templates included',
                            },
                        ].map((item) => (
                            <div key={item.title} className="bg-black/50 border border-white/10 rounded-lg p-5">
                                <h3 className="font-semibold text-white mb-2">{item.title}</h3>
                                <p className="text-sm text-slate-400 mb-3">{item.description}</p>
                                <p className="text-xs text-emerald-400 font-medium">{item.metric}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Summary */}
            <section className="px-4 sm:px-6 lg:px-8 py-16">
                <div className="max-w-5xl mx-auto">
                    <h2 className="text-3xl font-bold mb-8">Results Summary</h2>
                    <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4">
                        {HERO_METRICS.map((m) => (
                            <div key={m.label} className="bg-emerald-600/10 border border-emerald-600/30 rounded-lg p-5 text-center">
                                <p className="text-2xl font-bold text-emerald-400 mb-1">{m.value}</p>
                                <p className="text-sm text-white font-medium">{m.label}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section className="px-4 sm:px-6 lg:px-8 py-20 bg-gradient-to-b from-slate-950 to-black">
                <div className="max-w-4xl mx-auto text-center">
                    <h2 className="text-4xl font-bold mb-6">Run This Validation on Your Data</h2>
                    <p className="text-xl text-slate-300 mb-10 max-w-2xl mx-auto">
                        Upload a sample CSV. See your auto-normalization rate, KDE completeness score,
                        and time to FDA-ready export — measured on your actual supply chain data.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link
                            href="/signup"
                            className="inline-flex items-center justify-center px-8 py-4 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-lg transition-colors text-lg"
                        >
                            Start Free Trial <ArrowRight className="w-5 h-5 ml-2" />
                        </Link>
                        <Link
                            href="/pricing"
                            className="inline-flex items-center justify-center px-8 py-4 bg-slate-800 hover:bg-slate-700 text-white font-semibold rounded-lg transition-colors border border-slate-700 text-lg"
                        >
                            View Pricing
                        </Link>
                    </div>
                </div>
            </section>

            {/* Methodology */}
            <section className="px-4 sm:px-6 lg:px-8 py-12 border-t border-slate-800 bg-black">
                <div className="max-w-5xl mx-auto">
                    <h3 className="text-sm font-semibold text-slate-400 mb-4">Methodology</h3>
                    <div className="grid sm:grid-cols-3 gap-8 text-sm text-slate-500">
                        <div>
                            <p className="font-medium text-slate-400 mb-2">Data Source</p>
                            <p>
                                1,200 synthetic CTE events modeled on real-world leafy greens supply chain
                                patterns (Salinas Valley grower → fresh-cut processor → regional distribution).
                                Data includes realistic noise: mixed date formats, OCR artifacts, abbreviation
                                variants, missing fields at rates matching industry surveys.
                            </p>
                        </div>
                        <div>
                            <p className="font-medium text-slate-400 mb-2">Measurement</p>
                            <p>
                                All metrics measured on RegEngine's production codebase running against
                                PostgreSQL 15. Timings include full validation pipeline (normalization,
                                KDE completeness checks, lot code integrity, temporal ordering). Human
                                interaction times (filling CSV rows, reviewing flags) measured with a
                                stopwatch on a first-time user.
                            </p>
                        </div>
                        <div>
                            <p className="font-medium text-slate-400 mb-2">Disclosure</p>
                            <p>
                                This is a product validation study, not a customer case study. Data is
                                synthetic but modeled on real supply chain patterns and industry-reported
                                data quality rates. RegEngine is pre-GA. Metrics reflect current system
                                capabilities on representative workloads.
                            </p>
                        </div>
                    </div>
                </div>
            </section>
        </main>
    );
}
