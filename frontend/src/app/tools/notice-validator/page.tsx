"use client";

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { AlertTriangle, ArrowRight, CheckCircle2, ClipboardPaste, FileWarning, Info, RotateCcw, XCircle } from 'lucide-react';
import { LeadGate } from '@/components/lead-gate/LeadGate';
import { EmailGate } from '@/components/tools/EmailGate';
import { Container } from '@/components/layout/container';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardContent } from '@/components/ui/card';
import { fieldControlClasses } from '@/components/ui/input';
import { cn } from '@/lib/utils';

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

    // Gap severity is a tone on the summary tile, never a grade: the tile always
    // spells out "N of M elements detected · N gap-indicated".
    const summaryTone = (gaps?: number): 'neutral' | 'info' | 'warning' | 'danger' => {
        if (gaps === 0) return 'neutral';
        if (gaps && gaps <= 1) return 'info';
        if (gaps && gaps <= 2) return 'warning';
        return 'danger';
    };

    const summary = (disclaimer: string) => results && (
        <Callout tone={summaryTone(results.gaps)} role="status" title="Keyword self-check summary">
            <p className="mt-1 text-heading text-re-text-primary">{results.detected} of {results.total} elements detected · {results.gaps} gap-indicated</p>
            <p className="mt-2 text-small text-re-text-tertiary">{disclaimer}</p>
        </Callout>
    );

    return (
        <EmailGate toolName="notice-validator">
        <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
            <Container width="tool">
                <div className="border-b border-re-border-subtle pb-5">
                    <p className="mb-2 text-label text-re-text-muted">FSMA Response Self-Check</p>
                    <h1 className="text-title text-re-text-primary">
                        Spot keyword gaps in a draft FSMA 204 response before your team or counsel reviews it
                    </h1>
                    <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">
                        Paste a draft response, export summary, or internal request memo. This is a heuristic keyword self-check, not an FDA validator. It looks for keywords associated with FSMA 204 elements; presence of a keyword does not mean the underlying record content is sufficient. Have counsel and your QA lead review any response before submission to FDA.
                    </p>
                </div>

                <div className="mt-6 flex flex-wrap gap-2">
                    <Button
                        type="button"
                        variant="secondary"
                        onClick={() => { setNoticeText(SAMPLE_NOTICES.good); setHasAnalyzed(false); }}
                        leadingIcon={<ClipboardPaste aria-hidden="true" strokeWidth={1.75} />}
                    >
                        Load strong sample
                    </Button>
                    <Button
                        type="button"
                        variant="secondary"
                        onClick={() => { setNoticeText(SAMPLE_NOTICES.bad); setHasAnalyzed(false); }}
                        leadingIcon={<FileWarning aria-hidden="true" strokeWidth={1.75} />}
                    >
                        Load weak sample
                    </Button>
                    <Button
                        type="button"
                        variant="ghost"
                        onClick={() => { setNoticeText(''); setHasAnalyzed(false); }}
                        leadingIcon={<RotateCcw aria-hidden="true" strokeWidth={1.75} />}
                    >
                        Reset
                    </Button>
                </div>

                <div className="mt-6 grid gap-6 md:grid-cols-2">
                    <div>
                        <label htmlFor="notice-text" className="sr-only">
                            Paste an FDA request response or traceability export summary here...
                        </label>
                        <textarea
                            id="notice-text"
                            value={noticeText}
                            onChange={(e) => setNoticeText(e.target.value)}
                            placeholder="Paste an FDA request response or traceability export summary here..."
                            className={cn(fieldControlClasses, 'h-auto min-h-[340px] py-3 font-mono text-[0.8125rem]')}
                        />
                        <div className="mt-4 flex flex-wrap gap-3">
                            <Button
                                type="button"
                                size="lg"
                                onClick={() => setHasAnalyzed(Boolean(noticeText.trim()))}
                                disabled={!noticeText.trim()}
                                trailingIcon={<ArrowRight aria-hidden="true" strokeWidth={1.75} />}
                            >
                                Run keyword self-check
                            </Button>
                            <Button asChild variant="secondary" size="lg">
                                <Link href="/docs/fsma-204">
                                    FSMA Guide
                                </Link>
                            </Button>
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
                                teaser={summary('Heuristic keyword check on a draft. Not a compliance determination.')}
                            >
                                {summary('Heuristic keyword check on a draft. Not a compliance determination — have counsel and your QA lead review before any FDA submission.')}

                                {results.checks.map((check) => (
                                    <article key={check.id}>
                                        <Card>
                                            <CardContent>
                                                <div className="flex items-start gap-3">
                                                    {check.found ? (
                                                        <CheckCircle2 aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} />
                                                    ) : (
                                                        <XCircle aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0 text-re-warning" strokeWidth={1.75} />
                                                    )}
                                                    <div className="min-w-0">
                                                        <p className="text-subheading text-re-text-primary">{check.found ? 'Detected: ' : 'Gap indicated: '}{check.label}</p>
                                                        <p className="mt-1 font-mono text-[0.8125rem] text-re-text-tertiary">{check.regulation} · {check.citation}</p>
                                                        <p className="mt-2 text-ui text-re-text-secondary">{check.description}</p>
                                                    </div>
                                                </div>
                                            </CardContent>
                                        </Card>
                                    </article>
                                ))}
                            </LeadGate>
                        ) : (
                            <>
                                <Callout tone="info" role="note" icon={Info} title="What this checks">
                                    Lot scope, CTE references, KDE coverage, sortable export signals, and traceability record integrity markers.
                                </Callout>
                                <Callout tone="warning" role="note" icon={AlertTriangle} title="Scope note">
                                    Heuristic keyword self-check on a draft response. Does not validate FDA compliance, evidentiary integrity, or your 24-hour obligation under §1.1455(c). Have counsel and your QA lead review any response before submission to FDA.
                                </Callout>
                            </>
                        )}
                    </div>
                </div>

                <div className="mt-8 flex flex-wrap gap-3">
                    <Button asChild variant="secondary" size="lg">
                        <Link href="/tools/kde-checker">
                            KDE Checker
                        </Link>
                    </Button>
                    <Button asChild variant="secondary" size="lg">
                        <Link href="/tools/cte-mapper">
                            CTE Mapper
                        </Link>
                    </Button>
                    <Button asChild variant="secondary" size="lg">
                        <Link href="/trace">
                            Trace Explorer
                        </Link>
                    </Button>
                </div>
            </Container>
        </div>
        </EmailGate>
    );
}
