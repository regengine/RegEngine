'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import {
    ArrowRight,
    CheckCircle,
    Shield,
    Code2,
    Link2,
    Send,
    FileJson,
    Thermometer,
    Database,
    ShoppingCart,
    Terminal,
} from 'lucide-react';
import {
    DELIVERY_MODE_LABELS,
    INTEGRATION_TYPE_LABELS,
    STATUS_LABELS,
    getCapabilitiesByCategory,
} from '@/lib/customer-readiness';

const CATEGORY_SECTIONS = [
    {
        id: 'food_safety_iot' as const,
        title: 'Food Safety & IoT',
        description: 'Audit, inspection, and sensor records can be mapped into RegEngine without pretending every system has a native connector.',
        color: 'var(--re-brand)',
        icon: Thermometer,
    },
    {
        id: 'erp_warehouse' as const,
        title: 'ERP & Warehouse Systems',
        description: 'Most ERP integrations land as CSV or SFTP imports plus mapping review. That is the supported posture we expose publicly.',
        color: 'var(--re-info)',
        icon: Database,
    },
    {
        id: 'retailer_network' as const,
        title: 'Retailer Networks',
        description: 'Retailer support is modeled as export readiness unless a managed integration is explicitly available.',
        color: 'var(--re-brand)',
        icon: ShoppingCart,
    },
    {
        id: 'developer_api' as const,
        title: 'Developer APIs',
        description: 'Core APIs are available today, while advanced customer-specific integrations still run through scoped implementation work.',
        color: 'var(--re-info)',
        icon: Terminal,
    },
];

/* Status badge color mapping */
function statusBadgeClass(status: string): string {
    const label = STATUS_LABELS[status as keyof typeof STATUS_LABELS] || status;
    if (label === 'GA' || label === 'Live') return 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20';
    if (label === 'Pilot') return 'bg-amber-500/10 text-amber-400 border-amber-500/20';
    return 'bg-[var(--re-brand)]/10 text-[var(--re-brand)] border-[var(--re-brand)]/20';
}

const IMPLEMENTATION_REALITIES = [
    {
        title: 'Source mapping',
        body: 'Upstream fields still need to be mapped into FSMA CTE and KDE structures. RegEngine does not assume operational exports are already recall-ready.',
    },
    {
        title: 'Identity normalization',
        body: 'Lot codes, GLNs, product IDs, supplier names, and facility references need normalization before lineage and exports are reliable.',
    },
    {
        title: 'Exception handling',
        body: 'Missing KDEs, duplicate lots, ambiguous facilities, and conflicting supplier records are routed into a review queue before publication.',
    },
    {
        title: 'Integrity scope',
        body: 'SHA-256 hashing proves the integrity of records after ingest. It does not prove the original operational entry was correct.',
    },
];

const COMPLEMENTARY_ROLES = [
    {
        label: 'Your Ops Tool Handles',
        items: [
            'Daily checklists and monitoring',
            'Supplier document management',
            'CAPAs and corrective actions',
            'Task scheduling and shift handoffs',
            'Team training records',
        ],
    },
    {
        label: 'RegEngine Handles',
        items: [
            'Traceability normalization and review',
            'Cryptographic audit trail and manifest hashing',
            'GS1 EPCIS 2.0 and FDA-ready export packaging',
            'Retention-aware archive scheduling',
            'Recall drill workflow and readiness evidence',
        ],
    },
    {
        label: 'Together You Get',
        items: [
            'Operational continuity plus traceability evidence',
            'Export-ready packages without ripping out existing tools',
            'A clearer boundary between upstream records and compliance proof',
            'A customer-controlled archive posture',
            'A workflow buyers can explain to procurement and auditors',
        ],
    },
];

export default function IntegrationsPage() {
    return (
        <div className="min-h-screen bg-background">
            <section className="relative overflow-hidden border-b border-[var(--re-border-default)]">
                <div className="absolute inset-0 bg-gradient-to-br from-[var(--re-brand)]/5 to-transparent" />
                <div className="relative max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
                    <Breadcrumbs items={[{ label: 'Integrations' }]} />
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        className="text-center py-16 space-y-6"
                    >
                        <Badge className="bg-[var(--re-brand)] rounded-xl py-1 px-4">
                            <Link2 className="mr-2 h-4 w-4 inline" />
                            Traceability Data Layer
                        </Badge>
                        <h1 className="text-4xl md:text-6xl font-bold tracking-tight">
                            The compliance evidence layer
                            <br />
                            <span className="text-[var(--re-brand)]">for your existing stack</span>
                        </h1>
                        <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
                            RegEngine does not replace your food safety software. It ingests traceability data, normalizes it for FSMA workflows, and prepares export packages your team can defend.
                        </p>
                        <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
                            <Link href="/alpha">
                                <Button size="lg" className="bg-[var(--re-brand)] text-white font-semibold px-8 h-12 rounded-xl shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5">
                                    Request a Custom Integration
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Button>
                            </Link>
                            <Link href="/tools">
                                <Button size="lg" variant="outline" className="h-12 px-8 rounded-xl font-semibold">
                                    Explore Free Tools
                                </Button>
                            </Link>
                        </div>
                    </motion.div>
                </div>
            </section>

            <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
                <h2 className="text-2xl font-bold text-center mb-12">How it actually works</h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                    {[
                        {
                            step: '1',
                            title: 'Your operations systems',
                            desc: 'Capture inspections, suppliers, shipments, sensor logs, and ERP records in the systems you already run.',
                            icon: Shield,
                        },
                        {
                            step: '2',
                            title: 'RegEngine normalization',
                            desc: 'Map source fields, resolve exceptions, attach integrity metadata, and build lot genealogy with explicit review points.',
                            icon: Code2,
                        },
                        {
                            step: '3',
                            title: 'FDA and retailer response',
                            desc: 'Export regulator- and retailer-ready packages with manifests, timestamps, and traceability evidence.',
                            icon: Send,
                        },
                    ].map((s, i) => (
                        <motion.div
                            key={s.step}
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: i * 0.1 }}
                            className="text-center space-y-4"
                        >
                            <div className="mx-auto w-16 h-16 rounded-2xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] flex items-center justify-center">
                                <s.icon className="h-8 w-8 text-[var(--re-brand)]" />
                            </div>
                            <div className="text-xs font-bold text-[var(--re-brand)] uppercase tracking-widest">Step {s.step}</div>
                            <h3 className="text-lg font-bold">{s.title}</h3>
                            <p className="text-sm text-muted-foreground">{s.desc}</p>
                        </motion.div>
                    ))}
                </div>
            </section>

            <section className="border-y border-[var(--re-border-default)] bg-[var(--re-surface-card)]">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
                    <h2 className="text-2xl font-bold text-center mb-4">Integration registry</h2>
                    <p className="text-center text-muted-foreground mb-12 max-w-3xl mx-auto">
                        Delivery mode and product status are explicit. We do not use a blanket “Live” badge for everything.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {CATEGORY_SECTIONS.map((category, i) => (
                            <motion.div
                                key={category.id}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.1 }}
                            >
                                <Card className="h-full border-[var(--re-border-default)] bg-background shadow-sm">
                                    <CardHeader>
                                        <div className="flex items-center gap-3 mb-1">
                                            <div className="w-9 h-9 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)] flex items-center justify-center flex-shrink-0">
                                                <category.icon className="h-4.5 w-4.5 text-[var(--re-brand)]" />
                                            </div>
                                            <CardTitle className="text-lg">{category.title}</CardTitle>
                                        </div>
                                        <CardDescription>{category.description}</CardDescription>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="space-y-3">
                                            {getCapabilitiesByCategory(category.id).map((item) => (
                                                <div
                                                    key={item.id}
                                                    className="rounded-xl border border-[var(--re-border-default)] bg-[var(--re-surface-elevated)] p-3"
                                                >
                                                    <div className="flex flex-wrap items-center gap-2">
                                                        <span className="font-medium text-sm">{item.name}</span>
                                                        <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full border ${statusBadgeClass(item.status)}`}>
                                                            {STATUS_LABELS[item.status]}
                                                        </span>
                                                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">
                                                            {DELIVERY_MODE_LABELS[item.delivery_mode]}
                                                        </span>
                                                        <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-purple-500/10 text-purple-400 border border-purple-500/20">
                                                            {INTEGRATION_TYPE_LABELS[item.integration_type]}
                                                        </span>
                                                    </div>
                                                    <p className="text-xs text-muted-foreground mt-2">{item.customer_copy}</p>
                                                </div>
                                            ))}
                                        </div>
                                    </CardContent>
                                </Card>
                            </motion.div>
                        ))}
                    </div>
                </div>
            </section>

            <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
                <h2 className="text-2xl font-bold text-center mb-4">Implementation realities</h2>
                <p className="text-center text-muted-foreground mb-12 max-w-2xl mx-auto">
                    These are the operational constraints buyers should understand before calling any integration “done.”
                </p>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                    {IMPLEMENTATION_REALITIES.map((item) => (
                        <Card key={item.title} className="border-[var(--re-border-default)] shadow-sm">
                            <CardHeader>
                                <CardTitle className="text-base">{item.title}</CardTitle>
                            </CardHeader>
                            <CardContent>
                                <p className="text-sm text-muted-foreground">{item.body}</p>
                            </CardContent>
                        </Card>
                    ))}
                </div>
            </section>

            {/* Alpha callout */}
            <section className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8 pb-8">
                <div className="rounded-2xl border-2 border-[var(--re-brand)]/20 bg-[var(--re-brand)]/5 p-6 sm:p-8 text-center">
                    <p className="text-sm font-medium text-[var(--re-brand)] mb-2">Most Founding Design Partners start here</p>
                    <p className="text-muted-foreground text-sm mb-5 max-w-lg mx-auto">
                        Week 1: CSV/SFTP import with mapping review. Week 2–4: native API pilot scoped to your stack. No multi-year contract, no rip-and-replace.
                    </p>
                    <Link href="/alpha">
                        <Button className="bg-[var(--re-brand)] text-white font-semibold px-6 h-11 rounded-xl shadow-md hover:shadow-lg transition-all hover:-translate-y-0.5">
                            Become a Founding Design Partner
                            <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                    </Link>
                </div>
            </section>

            <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
                <h2 className="text-2xl font-bold text-center mb-4">Why RegEngine + your ops tool</h2>
                <p className="text-center text-muted-foreground mb-12 max-w-2xl mx-auto">
                    Your operational system still runs the day-to-day process. RegEngine turns those records into reviewable, exportable compliance evidence.
                </p>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                    {COMPLEMENTARY_ROLES.map((role, i) => (
                        <motion.div
                            key={role.label}
                            initial={{ opacity: 0, y: 20 }}
                            whileInView={{ opacity: 1, y: 0 }}
                            viewport={{ once: true }}
                            transition={{ delay: i * 0.1 }}
                        >
                            <Card className={`h-full border-[var(--re-border-default)] ${i === 2 ? 'ring-2 ring-[var(--re-brand)]' : ''}`}>
                                <CardHeader>
                                    <CardTitle className="text-base">{role.label}</CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <ul className="space-y-3">
                                        {role.items.map((item) => (
                                            <li key={item} className="flex items-start gap-2 text-sm">
                                                <CheckCircle className={`h-4 w-4 mt-0.5 flex-shrink-0 ${i === 2 ? 'text-[var(--re-brand)]' : 'text-muted-foreground'}`} />
                                                {item}
                                            </li>
                                        ))}
                                    </ul>
                                </CardContent>
                            </Card>
                        </motion.div>
                    ))}
                </div>
            </section>

            <section className="border-t border-[var(--re-border-default)]">
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center space-y-8">
                    <div className="inline-flex h-16 w-16 items-center justify-center rounded-3xl bg-[var(--re-brand)] text-white shadow-2xl mx-auto">
                        <FileJson className="h-8 w-8" />
                    </div>
                    <h2 className="text-3xl font-bold">Validate the delivery model before you buy</h2>
                    <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                        Start with the free tools, review the trust center, and then scope the right integration posture for your stack.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link href="/tools">
                            <Button size="lg" className="bg-[var(--re-brand)] text-white px-8 h-14 text-lg font-bold rounded-2xl">
                                Explore Free Tools
                                <ArrowRight className="ml-2 h-5 w-5" />
                            </Button>
                        </Link>
                        <Link href="/trust">
                            <Button size="lg" variant="outline" className="h-14 px-8 text-lg font-bold rounded-2xl">
                                Review Trust Center
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
