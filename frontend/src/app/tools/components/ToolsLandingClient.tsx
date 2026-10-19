'use client';

import { useState } from 'react';
import Link from 'next/link';
import { EXPERIMENTAL_TOOL_SLUGS, isExperimentalToolEnabled } from '@/lib/experimental-features';
import { Container } from '@/components/layout/container';
import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import {
    ArrowRight,
    ClipboardList,
    FlaskConical,
    Leaf,
    Map,
    ShieldCheck,
    Timer,
} from 'lucide-react';

type Category = 'all' | 'assess' | 'validate' | 'simulate' | 'operate';

const CATEGORIES: { id: Category; label: string }[] = [
    { id: 'all', label: 'All' },
    { id: 'assess', label: 'Assess' },
    { id: 'validate', label: 'Validate' },
    { id: 'simulate', label: 'Simulate' },
    { id: 'operate', label: 'Operate' },
];

const TOOLS = [
    ['ftl-checker', 'FTL List Checker', 'Look at the Food Traceability List. This page does not decide if you are a covered person.', Leaf, 'validate'],
    ['cte-mapper', 'CTE Mapper', 'Map the 7 Critical Tracking Events across a supply chain.', Map, 'validate'],
    ['kde-checker', 'KDE Field Checklist', 'Check whether CTE/KDE fields are present for each FTL product and CTE type.', ClipboardList, 'validate'],
    ['tlc-validator', 'TLC Format Check', 'Check traceability lot code format and uniqueness assumptions.', FlaskConical, 'validate'],
    ['self-reported-checklist', 'Self Reported Checklist', 'You answer. It echoes what you reported. Not a readiness score.', ShieldCheck, 'assess'],
    ['records-request-checklist', 'Records Request Checklist', 'Self reported checklist. Not a 24 hour capability test.', Timer, 'assess'],
] as const;

/** The hero aside: a hairline ledger, not a bordered data table (SPEC §6). */
const ROUTE_ROWS: [string, string][] = [
    ['Start', 'FTL list'],
    ['Map', 'CTEs and KDEs'],
    ['Check', 'Self reported fields'],
    ['Operate', 'Inflow and export'],
];

export function ToolsLandingClient() {
    const [activeCategory, setActiveCategory] = useState<Category>('all');
    const visibleTools = TOOLS.filter((tool) => !EXPERIMENTAL_TOOL_SLUGS.has(tool[0]) || isExperimentalToolEnabled(tool[0]));
    const filtered = activeCategory === 'all' ? visibleTools : visibleTools.filter((tool) => tool[4] === activeCategory);

    return (
        <div className="bg-re-surface-base">
            <Container
                as="section"
                width="marketing"
                className="grid items-start gap-10 pb-10 pt-12 md:grid-cols-[0.75fr_1fr] md:pb-12 md:pt-16"
            >
                <div>
                    <p className="mb-5 font-mono uppercase text-label text-re-text-muted">Tools</p>
                    <h1 className="max-w-[20ch] font-display text-display text-re-text-primary">
                        Free tools for FSMA 204 list checks and field checks.
                    </h1>
                    <p className="mt-6 max-w-[68ch] text-body text-re-text-secondary">
                        These pages help you look at the Food Traceability List, Critical Tracking Event (CTE) and Key Data Element (KDE) fields, and a self reported records request checklist. They do not score readiness, they do not decide if you are a covered person, and they do not claim you can meet §1.1455's clock.
                    </p>
                    <p className="mt-4 max-w-[68ch] text-small text-re-text-muted">
                        FDA won't enforce before July 20, 2028.
                    </p>
                </div>
                <Card className="self-start overflow-hidden">
                    <dl className="divide-y divide-re-border-subtle">
                        {ROUTE_ROWS.map(([label, value]) => (
                            <div key={label} className="flex items-baseline gap-4 px-4 py-2.5">
                                <dt className="w-1/3 shrink-0 font-mono uppercase text-label text-re-text-muted">{label}</dt>
                                <dd className="min-w-0 text-ui font-medium text-re-text-primary">{value}</dd>
                            </div>
                        ))}
                    </dl>
                </Card>
            </Container>

            <Container as="section" width="marketing" className="pb-16 pt-6 sm:pb-20">
                <div className="mb-6 flex flex-wrap gap-2">
                    {CATEGORIES.map((cat) => (
                        <button
                            key={cat.id}
                            type="button"
                            aria-pressed={activeCategory === cat.id}
                            onClick={() => setActiveCategory(cat.id)}
                            className={cn(
                                'inline-flex h-9 items-center rounded-md border px-4 font-mono uppercase text-label transition-colors duration-120 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-base motion-reduce:transition-none',
                                activeCategory === cat.id
                                    ? 'border-re-border-strong bg-re-surface-inset text-re-text-primary'
                                    : 'border-re-border bg-re-surface-card text-re-text-muted hover:bg-re-surface-inset hover:text-re-text-primary'
                            )}
                        >
                            {cat.label}
                        </button>
                    ))}
                </div>

                <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                    {filtered.map(([id, title, description, Icon, category]) => (
                        <Link
                            key={id}
                            href={`/tools/${id}`}
                            className="group flex min-h-[210px] flex-col justify-between rounded-lg border border-re-border bg-re-surface-card p-5 no-underline transition-colors duration-120 hover:border-re-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-base motion-reduce:transition-none"
                        >
                            <div>
                                <div className="mb-8 flex items-center justify-between border-b border-re-border-subtle pb-3">
                                    <Icon className="h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                    <span className="font-mono uppercase text-label text-re-text-muted">{category}</span>
                                </div>
                                <h2 className="text-heading text-re-text-primary">{title}</h2>
                                <p className="mt-3 text-ui text-re-text-secondary">{description}</p>
                            </div>
                            <span className="mt-6 flex items-center justify-between font-mono uppercase text-label text-re-text-primary">
                                Open
                                <ArrowRight
                                    className="h-4 w-4 transition-transform duration-120 group-hover:translate-x-1 motion-reduce:transition-none"
                                    strokeWidth={1.75}
                                    aria-hidden="true"
                                />
                            </span>
                        </Link>
                    ))}
                </div>
            </Container>
        </div>
    );
}
