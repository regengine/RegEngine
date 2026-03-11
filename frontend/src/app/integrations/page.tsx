'use client';

import { motion } from 'framer-motion';
import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';
import {
    ArrowRight,
    Webhook,
    Database,
    ShoppingCart,
    Code2,
    Shield,
    Zap,
    FileJson,
    Link2,
    Send,
} from 'lucide-react';

const INTEGRATION_CATEGORIES = [
    {
        title: 'Food Safety & IoT',
        description: 'Pull audit, inspection, and sensor data from your food safety platforms.',
        icon: Shield,
        color: 'var(--re-brand)',
        partners: [
            { name: 'SafetyCulture', role: 'Inspections & audit sync', status: 'live' as const },
            { name: 'FoodReady', role: 'HACCP & temp monitoring', status: 'live' as const },
            { name: 'FoodDocs', role: 'AI monitoring tasks', status: 'live' as const },
            { name: 'Tive Trackers', role: 'GPS + cold chain tracking', status: 'live' as const },
            { name: 'Sensitech TempTale', role: 'IoT sensor data', status: 'live' as const },
        ],
    },
    {
        title: 'ERP & Warehouse Systems',
        description: 'Import traceability data via CSV/SFTP from any ERP that exports tabular data.',
        icon: Database,
        color: 'var(--re-info)',
        partners: [
            { name: 'CSV / SFTP Import', role: 'Universal ERP connector', status: 'live' as const },
            { name: 'SAP S/4HANA', role: 'Via CSV/EDI export', status: 'csv' as const },
            { name: 'Oracle NetSuite', role: 'Via CSV/SFTP export', status: 'csv' as const },
            { name: 'Fishbowl', role: 'Via CSV export', status: 'csv' as const },
            { name: 'QuickBooks', role: 'Via CSV export', status: 'csv' as const },
        ],
    },
    {
        title: 'Retailer Networks',
        description: 'Push EPCIS-formatted traceability data to retailer compliance portals via export.',
        icon: ShoppingCart,
        color: 'var(--re-brand)',
        partners: [
            { name: 'Walmart', role: 'GDSN / ASN — EPCIS export', status: 'export' as const },
            { name: 'Kroger', role: '84.51° supplier exchange', status: 'export' as const },
            { name: 'Whole Foods', role: 'Amazon supplier portal', status: 'export' as const },
            { name: 'Costco', role: 'Supplier food safety portal', status: 'export' as const },
        ],
    },
    {
        title: 'Developer APIs',
        description: 'Build custom integrations using our API-first architecture.',
        icon: Code2,
        color: 'var(--re-info)',
        partners: [
            { name: 'REST API', role: 'Full traceability CRUD', status: 'live' as const },
            { name: 'Webhooks', role: 'Real-time event push', status: 'live' as const },
            { name: 'GS1 EPCIS 2.0', role: 'JSON-LD ingest & export', status: 'live' as const },
            { name: 'CSV Import', role: 'Bulk data migration', status: 'live' as const },
            { name: 'EDI 856', role: 'ASN inbound processing', status: 'live' as const },
        ],
    },
];

const COMPLEMENTARY_ROLES = [
    {
        label: 'Your Ops Tool Handles',
        items: [
            'Daily checklists & monitoring',
            'Supplier document management',
            'CAPAs & corrective actions',
            'Task scheduling & shift handoffs',
            'Employee training records',
        ],
    },
    {
        label: 'RegEngine Handles',
        items: [
            'Cryptographic audit trail (SHA-256)',
            'GS1 EPCIS 2.0 data exchange',
            '24-hour FDA export readiness',
            'FTL coverage & exemption analysis',
            'Tamper-evident lot genealogy',
        ],
    },
    {
        label: 'Together You Get',
        items: [
            'Full FSMA 204 compliance coverage',
            'Operational efficiency + data integrity',
            'Retailer-ready traceability exports',
            'Audit-proof records with zero extra work',
            'Math-based trust, not just process trust',
        ],
    },
];

export default function IntegrationsPage() {
    return (
        <div className="min-h-screen bg-background">
            {/* Hero */}
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
                            API-First Architecture
                        </Badge>
                        <h1 className="text-4xl md:text-6xl font-bold tracking-tight">
                            The Traceability Data Layer
                            <br />
                            <span className="text-[var(--re-brand)]">
                                for Your Stack
                            </span>
                        </h1>
                        <p className="text-xl text-muted-foreground max-w-3xl mx-auto">
                            RegEngine doesn&apos;t replace your food safety
                            software — it proves your traceability data to the
                            FDA and major retailers.
                        </p>
                    </motion.div>
                </div>
            </section>

            {/* How It Works */}
            <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
                <h2 className="text-2xl font-bold text-center mb-12">
                    How It Works
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
                    {[
                        {
                            step: '1',
                            title: 'Your Operations Tool',
                            desc: 'Manage daily checklists, suppliers, CAPAs, and workflows.',
                            icon: Shield,
                        },
                        {
                            step: '2',
                            title: 'RegEngine API',
                            desc: 'Cryptographic hashing, lot genealogy, and EPCIS export.',
                            icon: Zap,
                        },
                        {
                            step: '3',
                            title: 'FDA & Retailers',
                            desc: '24-hour compliant exports in GS1 EPCIS 2.0 format.',
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
                            <div className="text-xs font-bold text-[var(--re-brand)] uppercase tracking-widest">
                                Step {s.step}
                            </div>
                            <h3 className="text-lg font-bold">{s.title}</h3>
                            <p className="text-sm text-muted-foreground">
                                {s.desc}
                            </p>
                            {i < 2 && (
                                <div className="hidden md:block absolute right-0 top-1/2 -translate-y-1/2">
                                    <ArrowRight className="h-6 w-6 text-muted-foreground/30" />
                                </div>
                            )}
                        </motion.div>
                    ))}
                </div>
            </section>

            {/* Integration Categories */}
            <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-border-default)]">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
                    <h2 className="text-2xl font-bold text-center mb-4">
                        Integration Partners
                    </h2>
                    <p className="text-center text-muted-foreground mb-12 max-w-2xl mx-auto">
                        RegEngine works alongside the tools your team already
                        uses, adding cryptographic traceability without
                        disrupting existing workflows.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                        {INTEGRATION_CATEGORIES.map((cat, i) => (
                            <motion.div
                                key={cat.title}
                                initial={{ opacity: 0, y: 20 }}
                                whileInView={{ opacity: 1, y: 0 }}
                                viewport={{ once: true }}
                                transition={{ delay: i * 0.1 }}
                            >
                                <Card className="h-full border-[var(--re-border-default)] bg-background">
                                    <CardHeader>
                                        <div className="flex items-center gap-3">
                                            <div
                                                className="p-2 rounded-xl"
                                                style={{
                                                    background: `color-mix(in srgb, ${cat.color} 10%, transparent)`,
                                                }}
                                            >
                                                <cat.icon
                                                    className="h-6 w-6"
                                                    style={{
                                                        color: cat.color,
                                                    }}
                                                />
                                            </div>
                                            <div>
                                                <CardTitle className="text-lg">
                                                    {cat.title}
                                                </CardTitle>
                                                <CardDescription className="mt-1">
                                                    {cat.description}
                                                </CardDescription>
                                            </div>
                                        </div>
                                    </CardHeader>
                                    <CardContent>
                                        <div className="space-y-3">
                                            {cat.partners.map((p) => (
                                                <div
                                                    key={p.name}
                                                    className="flex items-center justify-between p-3 rounded-xl bg-[var(--re-surface-elevated)] border border-[var(--re-border-default)]"
                                                >
                                                    <div className="flex items-center gap-2">
                                                        <span className="font-medium text-sm">
                                                            {p.name}
                                                        </span>
                                                        {p.status === 'live' && (
                                                            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">Live</span>
                                                        )}
                                                        {p.status === 'csv' && (
                                                            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20">CSV</span>
                                                        )}
                                                        {p.status === 'export' && (
                                                            <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-amber-500/10 text-amber-400 border border-amber-500/20">Export</span>
                                                        )}
                                                    </div>
                                                    <span className="text-xs text-muted-foreground">
                                                        {p.role}
                                                    </span>
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

            {/* Complementary Roles */}
            <section className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-20">
                <h2 className="text-2xl font-bold text-center mb-4">
                    Why RegEngine + Your Ops Tool
                </h2>
                <p className="text-center text-muted-foreground mb-12 max-w-2xl mx-auto">
                    Your operations tool runs day-to-day food safety. RegEngine
                    proves it to regulators and retailers.
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
                            <Card
                                className={`h-full border-[var(--re-border-default)] ${i === 2 ? 'ring-2 ring-[var(--re-brand)]' : ''}`}
                            >
                                <CardHeader>
                                    <CardTitle className="text-base">
                                        {role.label}
                                    </CardTitle>
                                </CardHeader>
                                <CardContent>
                                    <ul className="space-y-3">
                                        {role.items.map((item) => (
                                            <li
                                                key={item}
                                                className="flex items-start gap-2 text-sm"
                                            >
                                                <CheckCircle2
                                                    className={`h-4 w-4 mt-0.5 flex-shrink-0 ${i === 2 ? 'text-[var(--re-brand)]' : 'text-muted-foreground'}`}
                                                />
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

            {/* CTA */}
            <section className="border-t border-[var(--re-border-default)]">
                <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-20 text-center space-y-8">
                    <div className="inline-flex h-16 w-16 items-center justify-center rounded-3xl bg-[var(--re-brand)] text-white shadow-2xl mx-auto">
                        <FileJson className="h-8 w-8" />
                    </div>
                    <h2 className="text-3xl font-bold">
                        Ready to Add Traceability?
                    </h2>
                    <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                        Start with our free tools, then connect your existing
                        stack via API. No rip-and-replace required.
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 justify-center">
                        <Link href="/tools">
                            <Button
                                size="lg"
                                className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white px-8 h-14 text-lg font-bold rounded-2xl"
                            >
                                Explore Free Tools
                                <ArrowRight className="ml-2 h-5 w-5" />
                            </Button>
                        </Link>
                        <Link href="/developers">
                            <Button
                                size="lg"
                                variant="outline"
                                className="h-14 px-8 text-lg font-bold rounded-2xl"
                            >
                                View API Docs
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
