'use client';

import { motion } from 'framer-motion';
import {
    ArrowLeft,
    Egg,
    Fish,
    Leaf,
    Milk,
    Shield,
    UtensilsCrossed,
} from 'lucide-react';
import Link from 'next/link';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

const FRAMEWORKS = [
    {
        id: 'fresh-produce',
        title: 'Fresh Produce',
        icon: Leaf,
        description: 'Leafy greens, herbs, melons, and fresh-cut produce workflows',
        details: 'Maps receiving, cooling, transformation, and shipping CTEs with KDE coverage patterns commonly requested by grocery buyers.',
        jsonSnippet: `{
  "profile": "fresh_produce",
  "ftl_categories": ["Leafy Greens", "Melons"],
  "required_ctes": ["RECEIVING", "TRANSFORMING", "SHIPPING"],
  "kde_focus": ["grower_lot", "harvest_date", "cooling_location"]
}`,
    },
    {
        id: 'seafood',
        title: 'Seafood',
        icon: Fish,
        description: 'Finfish and shellfish chain-of-custody controls',
        details: 'Tracks vessel/source references, cold-chain transitions, and lot transformations so recalls can be traced from supplier to shelf fast.',
        jsonSnippet: `{
  "profile": "seafood",
  "ftl_categories": ["Fresh Finfish", "Crustaceans"],
  "required_ctes": ["HARVESTING", "RECEIVING", "SHIPPING"],
  "kde_focus": ["source_vessel", "landing_date", "temperature_log"]
}`,
    },
    {
        id: 'dairy',
        title: 'Dairy',
        icon: Milk,
        description: 'Milk, cheese, and cultured product traceability profiles',
        details: 'Captures co-mingling and rework events with deterministic lineage so auditors can verify exactly which lots entered finished product batches.',
        jsonSnippet: `{
  "profile": "dairy",
  "ftl_categories": ["Soft Cheeses", "Fluid Dairy"],
  "required_ctes": ["RECEIVING", "TRANSFORMING", "PACKING", "SHIPPING"],
  "kde_focus": ["supplier_lot", "production_line", "hold_release_status"]
}`,
    },
    {
        id: 'deli-prepared',
        title: 'Deli & Prepared',
        icon: UtensilsCrossed,
        description: 'Ready-to-eat and mixed-ingredient operational profiles',
        details: 'Manages transformation-heavy workflows where a single output lot draws from many upstream inputs and must still support rapid backward tracing.',
        jsonSnippet: `{
  "profile": "deli_prepared",
  "ftl_categories": ["Ready-to-Eat Deli Salads"],
  "required_ctes": ["RECEIVING", "TRANSFORMING", "SHIPPING"],
  "kde_focus": ["input_lot_map", "recipe_revision", "pack_timestamp"]
}`,
    },
    {
        id: 'shell-eggs',
        title: 'Shell Eggs',
        icon: Egg,
        description: 'Pack-date, facility, and distributor continuity controls',
        details: 'Supports egg-specific lot and date coding expectations while preserving supplier-facility relationships needed for retailer and FDA record pulls.',
        jsonSnippet: `{
  "profile": "shell_eggs",
  "ftl_categories": ["Shell Eggs"],
  "required_ctes": ["RECEIVING", "PACKING", "SHIPPING"],
  "kde_focus": ["pack_date", "facility_registration", "distributor_reference"]
}`,
    },
];

function CodeBlock({ code }: { code: string }) {
    return (
        <pre className="bg-[var(--re-surface-base)] text-[var(--re-text-secondary)] p-4 rounded-lg overflow-x-auto text-xs font-mono border border-[var(--re-surface-border)]">
            <code>{code}</code>
        </pre>
    );
}

export default function ComplianceVerticalsPage() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)] overflow-x-hidden">
            <div className="fixed inset-0 pointer-events-none z-[1] opacity-[0.015]" style={{ backgroundImage: "url(\"data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E\")" }} />

            <section className="relative z-[2] max-w-[1120px] mx-auto pt-[96px] pb-[72px] px-6">
                <div className="absolute top-[-80px] left-1/2 -translate-x-1/2 w-[640px] h-[420px] bg-[radial-gradient(ellipse,rgba(16,185,129,0.08)_0%,transparent_72%)] pointer-events-none" />

                <Link href="/developers" className="inline-flex items-center text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] mb-8 transition-colors">
                    <ArrowLeft className="h-4 w-4 mr-2" />
                    Back to Developers
                </Link>

                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
                    <div className="inline-flex items-center gap-1.5 bg-[var(--re-brand-muted)] border border-[var(--re-brand)] rounded-full py-1 px-3 text-xs text-[var(--re-brand)] font-semibold mb-6 w-fit">
                        <span className="w-1.5 h-1.5 rounded-full bg-[var(--re-brand)] animate-pulse" />
                        FSMA 204 Profiles
                    </div>
                    <h1 className="text-[clamp(36px,5vw,52px)] font-bold text-[var(--re-text-primary)] leading-[1.08] mb-4 tracking-[-0.02em]">
                        Food-First Compliance
                        <br />
                        Vertical Profiles
                    </h1>
                    <p className="text-lg text-[var(--re-text-muted)] max-w-[780px]">
                        Pre-built FSMA 204 profile templates for the food categories most frequently
                        requested in retailer onboarding and recall drills.
                    </p>
                </motion.div>
            </section>

            <section className="relative z-[2] max-w-[1120px] mx-auto px-6 pb-[88px]">
                <div className="grid gap-8">
                    {FRAMEWORKS.map((framework, index) => (
                        <motion.div
                            key={framework.id}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: index * 0.08 }}
                        >
                            <Card className="bg-[var(--re-surface-card)] border-[var(--re-surface-border)] overflow-hidden">
                                <div className="grid md:grid-cols-2">
                                    <div className="p-6 md:p-8 flex flex-col justify-center">
                                        <div className="flex items-center gap-3 mb-4">
                                            <div className="p-2 bg-[var(--re-brand-muted)] rounded-lg">
                                                <framework.icon className="h-6 w-6 text-[var(--re-brand)]" />
                                            </div>
                                            <h2 className="text-2xl font-bold text-[var(--re-text-primary)]">{framework.title}</h2>
                                        </div>

                                        <Badge className="mb-4 bg-[var(--re-brand-muted)] text-[var(--re-brand)] border-[var(--re-brand-muted)] w-fit">
                                            {framework.description}
                                        </Badge>

                                        <p className="text-[var(--re-text-muted)] mb-6">
                                            {framework.details}
                                        </p>

                                        <div className="flex gap-4 flex-wrap">
                                            <Button asChild variant="outline" className="border-[var(--re-surface-border)] hover:bg-[var(--re-surface-base)] text-[var(--re-text-primary)]">
                                                <Link href="/docs/fsma-204">View FSMA Controls</Link>
                                            </Button>
                                            <Button asChild className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white">
                                                <Link href="/onboarding/supplier-flow">Start Guided Setup</Link>
                                            </Button>
                                        </div>
                                    </div>

                                    <div className="bg-[var(--re-surface-base)] p-6 md:p-8 border-l border-[var(--re-surface-border)]">
                                        <div className="flex items-center justify-between mb-4">
                                            <span className="text-xs font-semibold text-[var(--re-text-muted)] uppercase tracking-wider">
                                                Example Seed Data
                                            </span>
                                            <Badge variant="outline" className="text-xs border-[var(--re-surface-border)] text-[var(--re-text-muted)]">
                                                JSON
                                            </Badge>
                                        </div>
                                        <CodeBlock code={framework.jsonSnippet} />
                                    </div>
                                </div>
                            </Card>
                        </motion.div>
                    ))}
                </div>
            </section>

            <section className="relative z-[2] border-t border-[var(--re-surface-border)] py-[72px] px-6 text-center bg-[var(--re-surface-card)]">
                <Shield className="h-12 w-12 text-[var(--re-brand)] mx-auto mb-4" />
                <h3 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">Built for FDA and Retailer Readiness</h3>
                <p className="text-[var(--re-text-muted)] max-w-[720px] mx-auto">
                    Each profile maps to practical CTE and KDE coverage so teams can move from supplier
                    data chaos to auditable FSMA 204 responses.
                </p>
            </section>
        </div>
    );
}
