"use client";

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardPaste, FileWarning, Info, RotateCcw, Shield, XCircle } from 'lucide-react';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { EmailGate } from '@/components/tools/EmailGate';

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
        citation: '21 CFR 1.1320',
        label: 'Traceability Lot Code mention',
        description: 'Draft should clearly identify the traceability lot code and affected product scope. TLC assignment lives in §1.1320; KDEs live in the per-event sections (§§1.1325-1.1350).',
        keywords: ['traceability lot code', 'tlc', 'lot code', 'product description', 'food traceability list'],
        weight: 'critical',
    },
    {
        id: 'fda-request-events',
        regulation: 'FSMA 204',
        citation: '21 CFR §§1.1325, 1.1330, 1.1335, 1.1340, 1.1345, 1.1350',
        label: 'Critical Tracking Events mention',
        description: 'Draft should name the applicable CTE(s). Per-event sections: harvesting/cooling §1.1325; initial packing §1.1330; first land-based receiving (seafood from a fishing vessel) §1.1335; shipping §1.1340; receiving §1.1345 (subject to the §1.1305(j) restaurant/RFE exemption); transformation §1.1350.',
        keywords: ['receiving', 'shipping', 'transformation', 'cte', 'critical tracking event'],
        weight: 'critical',
    },
    {
        id: 'fda-request-kdes',
        regulation: 'FSMA 204',
        citation: '21 CFR §§1.1325, 1.1330, 1.1335, 1.1340, 1.1345, 1.1350',
        label: 'Key Data Elements mention',
        description: 'Draft should mention the KDEs needed to reconstruct lot movement. Required KDEs are defined per CTE in the §§1.1325-1.1350 sections; this self-check only looks for keyword presence.',
        keywords: ['quantity', 'unit of measure', 'ship from', 'ship to', 'event date', 'kde'],
        weight: 'critical',
    },
    {
        id: 'fda-request-export',
        regulation: 'FSMA 204',
        citation: '21 CFR §1.1455(c)',
        label: 'Sortable spreadsheet mention',
        description: '§1.1455(c) requires you to provide a sortable electronic spreadsheet to FDA as soon as possible, and not later than 24 hours after request. This check looks for sortable-export language in the draft — it does not measure whether your operational 24-hour clock will be met.',
        keywords: ['csv', 'sortable spreadsheet', 'export', 'fda request', 'within 24 hours'],
        weight: 'important',
    },
    {
        id: 'fda-request-integrity',
        regulation: 'RegEngine',
        citation: 'Integrity-marker mention',
        label: 'Integrity-marker mention',
        description: 'Checks whether the draft mentions hashes or audit references. This is a text check only — it does not verify any cryptographic chain.',
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
- Sortable spreadsheet prepared per §1.1455(c) 24-hour availability requirement
- SHA256 and chain hash references included for record verification`,
    bad: `Lot response attached.

Product moved through the system last week.

Please review the records.`,
};

// Note: the "good" sample above is illustrative only — passing this self-check on a draft
// does not mean the draft satisfies §1.1455(c); the rule requires actual record content,
// not keyword presence.

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

        const detected = checks.filter((c) => c.found).length;
        const total = checks.length;
        const gaps = total - detected;

        return { checks, detected, total, gaps };
    }, [hasAnalyzed, noticeText]);

    const summaryColor = (gaps?: number) => {
        if (gaps === 0) return 'text-re-brand border-re-brand/40 bg-re-brand-muted';
        if (gaps && gaps <= 1) return 'text-sky-500 border-sky-500/40 bg-sky-500/10';
        if (gaps && gaps <= 2) return 'text-re-warning border-re-warning/40 bg-re-warning-muted0/10';
        return 'text-rose-500 border-rose-500/40 bg-rose-500/10';
    };

    return (
        <EmailGate toolName="notice-validator">
        <main className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            <section className="max-w-[1100px] mx-auto px-6 py-20">
                <div className="max-w-[760px]">
                    <p className="text-xs uppercase tracking-[0.12em] text-[var(--re-brand)] mb-3">FSMA Response Self-Check</p>
                    <h1 className="text-[clamp(32px,4vw,48px)] font-bold text-[var(--re-text-primary)] leading-tight">
                        Spot keyword gaps in a draft FSMA 204 response before your team or counsel reviews it
                    </h1>
                    <p className="mt-4 text-lg text-[var(--re-text-muted)] leading-relaxed">
                        Paste a draft response, export summary, or internal request memo. This is a heuristic keyword self-check, not an FDA validator. It looks for keywords associated with FSMA 204 elements; presence of a keyword does not mean the underlying record content is sufficient. Have counsel and your QA lead review any response before submission to FDA.
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
                                Run keyword self-check
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
                                headline="See your full self-check breakdown"
                                subheadline="See which elements are detected and which are gap-indicated, with the per-CTE citations to review with counsel. This is a keyword self-check, not a compliance determination."
                                ctaText="See breakdown"
                                toolContext={{ quizGrade: undefined, quizScore: results.detected }}
                                teaser={
                                    <div className={`rounded-2xl border p-6 ${summaryColor(results.gaps)}`}>
                                        <p className="text-sm font-medium">Keyword self-check summary</p>
                                        <p className="mt-1 text-2xl font-bold">{results.detected} of {results.total} elements detected · {results.gaps} gap-indicated</p>
                                        <p className="mt-2 text-xs opacity-80">Heuristic keyword check on a draft. Not a compliance determination.</p>
                                    </div>
                                }
                            >
                                <div className={`rounded-2xl border p-6 ${summaryColor(results.gaps)}`}>
                                    <p className="text-sm font-medium">Keyword self-check summary</p>
                                    <p className="mt-1 text-2xl font-bold">{results.detected} of {results.total} elements detected · {results.gaps} gap-indicated</p>
                                    <p className="mt-2 text-xs opacity-80">Heuristic keyword check on a draft. Not a compliance determination — have counsel and your QA lead review before any FDA submission.</p>
                                </div>

                                {results.checks.map((check) => (
                                    <article key={check.id} className="rounded-2xl border border-[var(--re-surface-border)] bg-[var(--re-surface-card)] p-5">
                                        <div className="flex items-start gap-3">
                                            {check.found ? (
                                                <CheckCircle2 className="h-5 w-5 text-re-brand mt-0.5" />
                                            ) : (
                                                <XCircle className="h-5 w-5 text-rose-500 mt-0.5" />
                                            )}
                                            <div>
                                                <p className="font-semibold text-[var(--re-text-primary)]">{check.found ? 'Detected: ' : 'Gap indicated: '}{check.label}</p>
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
                                        <AlertTriangle className="h-5 w-5 text-re-warning mt-0.5" />
                                        <div>
                                            <p className="font-semibold text-[var(--re-text-primary)]">Scope note</p>
                                            <p className="mt-2 text-sm text-[var(--re-text-muted)]">
                                                Heuristic keyword self-check on a draft response. Does not validate FDA compliance, evidentiary integrity, or your 24-hour obligation under §1.1455(c). Have counsel and your QA lead review any response before submission to FDA.
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
        </EmailGate>
    );
}
