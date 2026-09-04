'use client';

import { useState } from 'react';
import Link from 'next/link';
import { EXPERIMENTAL_TOOL_SLUGS, isExperimentalToolEnabled } from '@/lib/experimental-features';
import {
    ArrowRight,
    BarChart3,
    ClipboardList,
    Database,
    FileOutput,
    FlaskConical,
    Leaf,
    Map,
    ScanBarcode,
    ShieldCheck,
    Timer,
    Upload,
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
    ['self-reported-checklist', 'Self-Reported Checklist', 'You answer. We echo what you reported. Not a readiness score.', ShieldCheck, 'assess'],
    ['records-request-checklist', 'Records-Request Checklist', 'Self-reported checklist. Not a 24-hour capability test.', Timer, 'assess'],
] as const;

export function ToolsLandingClient() {
    const [activeCategory, setActiveCategory] = useState<Category>('all');
    const visibleTools = TOOLS.filter((tool) => !EXPERIMENTAL_TOOL_SLUGS.has(tool[0]) || isExperimentalToolEnabled(tool[0]));
    const filtered = activeCategory === 'all' ? visibleTools : visibleTools.filter((tool) => tool[4] === activeCategory);

    return (
        <main className="re-page min-h-screen text-[var(--re-text-secondary)]">
            <section className="re-container grid items-start gap-10 pb-10 pt-12 md:grid-cols-[0.75fr_1fr] md:pb-12 md:pt-16">
                <div>
                    <p className="re-label mb-5">Tools</p>
                    <h1 className="re-hero-title max-w-[620px]">
                        Small tools for list checks and field checks.
                    </h1>
                    <p className="re-hero-copy mt-6">
                        These pages help you look at the Food Traceability List, CTE/KDE fields, and a self-reported records-request checklist. They do not score readiness, they do not decide if you are a covered person, and they do not claim you can meet §1.1455's clock.
                    </p>
                    <p className="re-hero-copy mt-4 text-sm" style={{ color: 'var(--re-text-muted)' }}>
                        The federal Food Traceability Rule compliance date is July 20, 2028.
                    </p>
                </div>
                <div className="re-panel self-start overflow-hidden">
                    <table className="re-rule-table">
                        <tbody>
                            {[
                                ['Start', 'FTL list'],
                                ['Map', 'CTEs and KDEs'],
                                ['Check', 'Self-reported fields'],
                                ['Operate', 'Inflow and export'],
                            ].map(([label, value]) => (
                                <tr key={label}>
                                    <td className="w-1/3 font-mono text-[12px] uppercase text-[var(--re-text-muted)]">{label}</td>
                                    <td className="font-medium text-[var(--re-text-primary)]">{value}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>

            <section className="re-section pt-6">
                <div className="re-container">
                    <div className="mb-6 flex flex-wrap gap-2">
                        {CATEGORIES.map((cat) => (
                            <button
                                key={cat.id}
                                type="button"
                                onClick={() => setActiveCategory(cat.id)}
                                className={`h-9 border px-4 font-mono text-[12px] font-medium uppercase ${
                                    activeCategory === cat.id
                                        ? 'border-[var(--re-text-primary)] bg-[var(--re-text-primary)] text-[var(--re-surface-base)]'
                                        : 'border-[var(--re-surface-border)] bg-transparent text-[var(--re-text-muted)]'
                                }`}
                            >
                                {cat.label}
                            </button>
                        ))}
                    </div>

                    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
                        {filtered.map(([id, title, description, Icon, category], index) => (
                            <Link
                                key={id}
                                href={`/tools/${id}`}
                                className="re-panel group flex min-h-[210px] flex-col justify-between p-5 no-underline"
                            >
                                <div>
                                    <div className="mb-8 flex items-center justify-between border-b border-[var(--re-surface-border)] pb-3">
                                        <Icon className="h-5 w-5" style={{ color: index % 4 === 0 ? 'var(--re-info)' : index % 4 === 1 ? 'var(--re-success)' : index % 4 === 2 ? 'var(--re-warning)' : 'var(--re-danger)' }} />
                                        <span className="font-mono text-[11px] uppercase text-[var(--re-text-muted)]">{category}</span>
                                    </div>
                                    <h2 className="text-xl font-semibold text-[var(--re-text-primary)]">{title}</h2>
                                    <p className="mt-3 text-sm leading-6 text-[var(--re-text-muted)]">{description}</p>
                                </div>
                                <span className="mt-6 flex items-center justify-between font-mono text-[12px] uppercase text-[var(--re-text-primary)]">
                                    Open
                                    <ArrowRight className="h-4 w-4 transition-transform group-hover:translate-x-1" />
                                </span>
                            </Link>
                        ))}
                    </div>
                </div>
            </section>
        </main>
    );
}
