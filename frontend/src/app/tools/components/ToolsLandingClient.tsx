'use client';

import { useState } from 'react';
import Link from 'next/link';
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
    ['ftl-checker', 'FTL Coverage Checker', 'Check whether a product sits on the Food Traceability List.', Leaf, 'validate'],
    ['cte-mapper', 'CTE Coverage Mapper', 'Map who owes which traceability events across a supply chain.', Map, 'validate'],
    ['kde-checker', 'KDE Completeness Checker', 'Turn role and product context into required data elements.', ClipboardList, 'validate'],
    ['tlc-validator', 'TLC Validator', 'Check traceability lot code format and uniqueness assumptions.', FlaskConical, 'validate'],
    ['readiness-assessment', 'FSMA 204 Readiness Assessment', 'Score product coverage, event capture, KDEs, and systems.', ShieldCheck, 'assess'],
    ['recall-readiness', 'Recall Readiness Score', 'Estimate whether you can answer a 24-hour records request.', Timer, 'assess'],
    ['inflow-lab', 'Inflow Lab', 'Preflight messy supplier data and review the commit gate.', Database, 'simulate'],
    ['fsma-unified', 'Cold Chain Anomaly Detector', 'Find temperature and supplier-risk anomalies in cold-chain records.', BarChart3, 'simulate'],
    ['roi-calculator', 'Regulatory ROI Calculator', 'Compare manual compliance cost with automated traceability.', BarChart3, 'assess'],
    ['data-import', 'Data Import Assistant', 'Map existing spreadsheets into FSMA-ready CTE/KDE structures.', Upload, 'operate'],
    ['scan', 'GS1 Barcode Scanner', 'Scan GS1 identifiers and fill traceability fields in the browser.', ScanBarcode, 'operate'],
    ['export', 'FDA Export Package Generator', 'Generate a regulator-ready package from verified records.', FileOutput, 'operate'],
] as const;

export function ToolsLandingClient() {
    const [activeCategory, setActiveCategory] = useState<Category>('all');
    const filtered = activeCategory === 'all' ? TOOLS : TOOLS.filter((tool) => tool[4] === activeCategory);

    return (
        <main className="re-page min-h-screen text-[var(--re-text-secondary)]">
            <section className="re-container grid gap-10 pb-10 pt-12 md:grid-cols-[0.75fr_1fr] md:pb-14 md:pt-18">
                <div>
                    <p className="re-label mb-5">Tools</p>
                    <h1 className="max-w-[620px] text-[clamp(40px,6vw,70px)] font-semibold leading-[0.98]">
                        Instruments for finding traceability gaps.
                    </h1>
                    <p className="mt-6 max-w-[560px] text-[17px] leading-7 text-[var(--re-text-muted)]">
                        Small utilities for checking product scope, data completeness, recall readiness, and evidence export before the work reaches production.
                    </p>
                </div>
                <div className="re-panel overflow-hidden">
                    <table className="re-rule-table">
                        <tbody>
                            {[
                                ['Start', 'FTL coverage'],
                                ['Map', 'CTEs and KDEs'],
                                ['Test', 'Recall readiness'],
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
