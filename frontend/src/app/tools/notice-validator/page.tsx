"use client";

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardPaste, FileWarning, Info, RotateCcw, Shield, XCircle } from 'lucide-react';
import { LeadGate } from '@/components/lead-gate/LeadGate';

interface Requirement {
    id: string;
    regulation: string;
    citation: string;
    label: string;
    description: string;
    keywords: string[];
    weight: 'critical' | 'important' | 'recommended';
}

const REQUIREMENTS: Requirement[] = [
    {
        id: 'fda-request-scope',
        regulation: 'FSMA 204',
        citation: '21 CFR 1.1455',
        label: 'Traceability Lot Scope',
        description: 'Response should clearly identify the traceability lot code and affected product scope.',
        keywords: ['traceability lot code', 'tlc', 'lot code', 'product description', 'food traceability list'],
        weight: 'critical',
    },
    {
        id: 'fda-request-events',
        regulation: 'FSMA 204',
        citation: '21 CFR 1.1325-1.1350',
        label: 'Critical Tracking Events',
        description: 'Response should reference the applicable receiving, transformation, shipping, or other covered events.',
        keywords: ['receiving', 'shipping', 'transformation', 'cte', 'critical tracking event'],
        weight: 'critical',
    },
    {
        id: 'fda-request-kdes',
        regulation: 'FSMA 204',
        citation: '21 CFR 1.1325-1.1350',
        label: 'Key Data Elements',
        description: 'Response should include the KDEs needed to reconstruct lot movement and handling.',
        keywords: ['quantity', 'unit of measure', 'ship from', 'ship to', 'event date', 'kde'],
        weight: 'critical',
    },
    {
        id: 'fda-request-export',
        regulation: 'FSMA 204',
        citation: '21 CFR 1.1455(c)',
        label: 'Sortable Export Readiness',
        description: 'Response should be organized in a sortable form appropriate for FDA request mode.',
        keywords: ['csv', 'sortable spreadsheet', 'export', 'fda request', 'within 24 hours'],
        weight: 'important',
    },
    {
        id: 'fda-request-integrity',
        regulation: 'RegEngine',
        citation: 'Evidence chain',
        label: 'Record Integrity',
        description: 'Response should preserve hashes, verification status, or audit references for the submitted records.',
        keywords: ['sha256', 'chain hash', 'verification', 'audit trail', 'immutable'],
        weight: 'recommended',
    },
];

const SAMPLE_NOTICES = {
    good: `FDA Request Response

Traceability Lot Code: 00012345678901-LOT-2026-001
Product Description: Romaine Lettuce

Covered Critical Tracking Events:
- Receiving at FreshLeaf Distribution Center on 2026-03-03
- Transformation into packed case lots on 2026-03-04
- Shipping to retailer DC on 2026-03-05

Key Data Elements Included:
- Quantity: 500 cases
- Unit of Measure: cases
- Ship From: Valley Fresh Farms
- Ship To: FreshLeaf Distribution Center / Retailer DC-04
- Event Dates and facility references

Export Package:
- Sortable spreadsheet CSV attached
- Generated within 24 hours of request
- SHA256 and chain hash references included for record verification`,
    bad: `Lot response attached.

Product moved through the system last week.

Please review the records.`,
};

export default function NoticeValidatorPage() {
    const [noticeText, setNoticeText] = useState('');
    const [hasAnalyzed, setHasAnalyzed] = useState(false);

    const results = useMemo(() => {
        if (!hasAnalyzed || !noticeText.trim()) return null;

        const lower = noticeText.toLowerCase();
        const checks = REQUIREMENTS.map((req) => ({
            ...req,
            found: req.keywords.some((kw) => lower.includes(kw.toLowerCase())),
        }));

        const score = Math.round((checks.filter((c) => c.found).length / checks.length) * 100);
        let grade: 'A' | 'B' | 'C' | 'D' | 'F' = 'F';
        if (score >= 90) grade = 'A';
        else if (score >= 75) grade = 'B';
        else if (score >= 60) grade = 'C';
        else if (score >= 40) grade = 'D';

        return { checks, score, grade };
    }, [hasAnalyzed, noticeText]);

    const gradeColor = (grade?: string) => {
        if (grade === 'A') return 'text-emerald-500 border-emerald-500/40 bg-emerald-500/10';
        if (grade === 'B') return 'text-sky-500 border-sky-500/40 bg-sky-500/10';
        if (grade === 'C') return 'text-amber-500 border-amber-500/40 bg-amber-500/10';
        return 'text-rose-500 border-rose-500/40 bg-rose-500/10';
    };

    return (
        <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            <section className="max-w-[1100px] mx-auto px-6 py-20">
                <div className="max-w-[760px]">
                    <p className="text-xs uppercase tracking-[0.12em] text-[var(--re-brand)] mb-3">FSMA Request Validator</p>
                    <h1 className="text-[clamp(32px,4vw,48px)] font-bold text-[var(--re-text-primary)] leading-tight">
                        Check whether an FDA request response includes the core FSMA 204 record elements
                    </h1>
                    <p className="mt-4 text-lg text-[var(--re-text-muted)] leading-relaxed">
                        Paste a draft response, export summary, or internal request memo. This validator looks for the essential traceability signals expected in an FSMA 204 response workflow.
                    </p>
                </div>

                <div className="mt-8 flex flex-wrap gap-3">
                    <button onClick={() => { setNoticeText(SAMPLE_NOTICES.good); setHasAnalyzed(false); }} className="inline-flex items-center gap-2 rounded-xl border border-[var(--re-surface-border)] px-4 py-2 text-sm font-medium text-[var(--re-text-primary)]">
                        <ClipboardPaste className="h-4 w-4" />
                        Load strong sample
                    </button>
                    <button onClick={() => { setNoticeText(SAMPLE_NOTICES.bad); setHasAnalyzed(false); }} className="inline-flex items-center gap-2 rounded-xl border border-[var(--re-surface-border)] px-4 py-2 text-sm font-medium text-[var(--re-text-primary)]">
                        <FileWarning className="h-4 w-4" />
                        Load weak sample
                    </button>
                    <button onClick={() => { setNoticeText(''); setHasAnalyzed(false); }} className="inline-flex items-center gap-2 rounded-xl border border-[var(--re-surface-border)] px-4 py-2 text-sm font-medium text-[var(--re-text-primary)]">
                        <RotateCcw className="h-4 w-4" />
                        Reset
                    </button>
                </div>

                <div className="mt-6 grid gap-6 lg:grid-cols-[1.2fr_0.8fr]">
                    <div>
                        <textarea
                            value={noticeText}
                            onChange={(e) => setNoticeText(e.target.value)}
                            placeholder="Paste an FDA request response or traceability export summary here..."
                            className="min-h-[340px] w-full rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5 text-sm text-[var(--re-text-primary)] outline-none"
                        />
                        <div className="mt-4 flex flex-wrap gap-3">
                            <button
                                onClick={() => setHasAnalyzed(Boolean(noticeText.trim()))}
                                disabled={!noticeText.trim()}
                                className="inline-flex items-center justify-center h-11 px-6 rounded-xl bg-[var(--re-brand)] text-white font-semibold disabled:opacity-40"
                            >
                                Analyze Response
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </button>
                            <Link href="/docs/fsma-204" className="inline-flex items-center justify-center h-11 px-6 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-primary)] font-semibold">
                                FSMA Guide
                            </Link>
                        </div>
                    </div>

                    <div className="space-y-4">
                        {results ? (
                            <LeadGate
                                source="notice-validator"
                                headline="Unlock Your Full Validation Report"
                                subheadline="See every requirement check with pass/fail details and FSMA 204 citations."
                                ctaText="Get Full Report"
                                toolContext={{ quizGrade: results.grade, quizScore: results.score }}
                                teaser={
                                    <div className={`rounded-2xl border p-6 ${gradeColor(results.grade)}`}>
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <p className="text-sm font-medium">Coverage grade</p>
                                                <p className="mt-1 text-4xl font-bold">{results.grade}</p>
                                            </div>
                                            <div className="text-right">
                                                <p className="text-sm font-medium">Match score</p>
                                                <p className="mt-1 text-2xl font-bold">{results.score}%</p>
                                            </div>
                                        </div>
                                    </div>
                                }
                            >
                                <div className={`rounded-2xl border p-6 ${gradeColor(results.grade)}`}>
                                    <div className="flex items-center justify-between">
                                        <div>
                                            <p className="text-sm font-medium">Coverage grade</p>
                                            <p className="mt-1 text-4xl font-bold">{results.grade}</p>
                                        </div>
                                        <div className="text-right">
                                            <p className="text-sm font-medium">Match score</p>
                                            <p className="mt-1 text-2xl font-bold">{results.score}%</p>
                                        </div>
                                    </div>
                                </div>

                                {results.checks.map((check) => (
                                    <article key={check.id} className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                                        <div className="flex items-start gap-3">
                                            {check.found ? (
                                                <CheckCircle2 className="h-5 w-5 text-emerald-500 mt-0.5" />
                                            ) : (
                                                <XCircle className="h-5 w-5 text-rose-500 mt-0.5" />
                                            )}
                                            <div>
                                                <p className="font-semibold text-[var(--re-text-primary)]">{check.label}</p>
                                                <p className="text-xs text-[var(--re-text-muted)] mt-1">{check.regulation} · {check.citation}</p>
                                                <p className="text-sm text-[var(--re-text-muted)] mt-2">{check.description}</p>
                                            </div>
                                        </div>
                                    </article>
                                ))}
                            </LeadGate>
                        ) : (
                            <>
                                <div className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-6">
                                    <div className="flex items-start gap-3">
                                        <Info className="h-5 w-5 text-[var(--re-brand)] mt-0.5" />
                                        <div>
                                            <p className="font-semibold text-[var(--re-text-primary)]">What this checks</p>
                                            <p className="mt-2 text-sm text-[var(--re-text-muted)]">
                                                Lot scope, CTE references, KDE coverage, sortable export signals, and traceability record integrity markers.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                                <div className="rounded-2xl border border-[rgba(245,158,11,0.24)] bg-[rgba(245,158,11,0.08)] p-6">
                                    <div className="flex items-start gap-3">
                                        <AlertTriangle className="h-5 w-5 text-amber-500 mt-0.5" />
                                        <div>
                                            <p className="font-semibold text-[var(--re-text-primary)]">Scope note</p>
                                            <p className="mt-2 text-sm text-[var(--re-text-muted)]">
                                                This is a heuristic checker for draft responses, not legal advice or a substitute for your full FDA export workflow.
                                            </p>
                                        </div>
                                    </div>
                                </div>
                            </>
                        )}
                    </div>
                </div>

                <div className="mt-8 flex flex-wrap gap-3">
                    <Link href="/tools/kde-checker" className="inline-flex items-center justify-center h-11 px-6 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-primary)] font-semibold">
                        KDE Checker
                    </Link>
                    <Link href="/tools/cte-mapper" className="inline-flex items-center justify-center h-11 px-6 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-primary)] font-semibold">
                        CTE Mapper
                    </Link>
                    <Link href="/trace" className="inline-flex items-center justify-center h-11 px-6 rounded-xl border border-[var(--re-surface-border)] text-[var(--re-text-primary)] font-semibold">
                        Trace Explorer
                    </Link>
                </div>
            </section>
        </main>
    );
}
