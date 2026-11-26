'use client';

import { useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowRight, Check, ShieldCheck, X } from "lucide-react";
import { submitAssessment } from "@/app/actions/submit-assessment";
import { Container } from "@/components/layout/container";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const checklistItems = [
    {
        id: "harvest",
        title: "Harvest CTEs captured",
        description: "Harvesting records linked to the food and its initial packing records",
        regulation: "21 CFR § 1.1325(a)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1325",
    },
    {
        id: "shipping",
        title: "Shipping CTEs captured",
        description: "All outbound shipments with Traceability Lot Codes linked to each unit",
        regulation: "21 CFR § 1.1340(a)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1340",
    },
    {
        id: "receiving",
        title: "Receiving CTEs captured",
        description: "Inbound receiving events with supplier data and TLC verification",
        regulation: "21 CFR § 1.1345(a)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1345",
    },
    {
        id: "transformation",
        title: "Transformation CTEs captured",
        description: "Processing, packing, and repacking events with new TLCs assigned",
        regulation: "21 CFR § 1.1350(a)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1350",
    },
    {
        id: "kdes",
        title: "All KDEs populated",
        description: "Key Data Elements recorded for each Critical Tracking Event type",
        regulation: "21 CFR §§ 1.1325 to 1.1350",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1325",
    },
    {
        id: "tlc_linkage",
        title: "TLCs linked across events",
        description: "Traceability Lot Codes connected from harvest to distribution across your supply chain",
        regulation: "21 CFR § 1.1320",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1320",
    },
    {
        id: "response_time",
        title: "24-hour response capability",
        description: "Can provide FDA with requested traceability data within 24 hours",
        regulation: "21 CFR § 1.1455(c)(1)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455",
    },
    {
        id: "electronic",
        title: "Electronic recordkeeping",
        description: "Can provide an electronic sortable spreadsheet when required by FDA",
        regulation: "21 CFR § 1.1455(c)(3)(ii)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455",
    },
];

export default function FSMAChecklist() {
    const [checked, setChecked] = useState<Record<string, boolean>>({});
    const [showResults, setShowResults] = useState(false);
    const [email, setEmail] = useState("");
    const [company, setCompany] = useState("");
    const [submitted, setSubmitted] = useState(false);
    const [submissionError, setSubmissionError] = useState<string | null>(null);

    const checkedCount = Object.values(checked).filter(Boolean).length;
    const total = checklistItems.length;
    const allChecked = checkedCount === total;
    const uncheckedItems = checklistItems.filter((item) => !checked[item.id]);

    const toggle = (id: string) => {
        setChecked((prev) => ({ ...prev, [id]: !prev[id] }));
        setShowResults(false);
        setSubmitted(false);
        setSubmissionError(null);
    };

    const handleSubmit = async () => {
        if (email && company) {
            setSubmissionError(null);
            const submittedAt = new Date().toISOString();
            const result = await submitAssessment({
                name: "FSMA checklist lead",
                email,
                company,
                role: "Retailer readiness checklist",
                source: "fsma-checklist",
                quizScore: checkedCount,
                quizGrade: `${checkedCount}/${total}`,
                quizAnswers: {
                    checked,
                    gaps: uncheckedItems.map(i => i.title),
                },
            });

            if (!result.success) {
                try {
                    localStorage.setItem('fsma_gap_analysis_retry', JSON.stringify({
                        pending: true,
                        lastAttemptAt: submittedAt,
                        source: "fsma-checklist",
                    }));
                } catch {}
                setSubmissionError(result.error || "We could not send your gap analysis request. Your details are still on this page; please try again.");
                return;
            }

            try {
                localStorage.setItem('fsma_gap_analysis_submitted', '1');
                localStorage.removeItem('fsma_gap_analysis_retry');
            } catch {}
            setSubmitted(true);
        }
    };

    // Band colour for the readiness meter. The number itself stays ink - the
    // meter is a supporting mark, and "N/8" carries the meaning on its own.
    const scoreBarClass =
        checkedCount <= 3
            ? "bg-re-danger"
            : checkedCount <= 5
                ? "bg-re-warning"
                : checkedCount <= 7
                    ? "bg-re-info"
                    : "bg-re-success";

    const bandRailClass =
        checkedCount <= 3
            ? "border-l-re-danger"
            : checkedCount <= 5
                ? "border-l-re-warning"
                : "border-l-re-info";

    const bandIconClass =
        checkedCount <= 3
            ? "text-re-danger"
            : checkedCount <= 5
                ? "text-re-warning"
                : "text-re-info";

    return (
        <section className="border-t border-re-border-subtle bg-re-surface-base py-16 sm:py-20">
            <Container width="prose">
                {/* Title */}
                <div className="mb-10 space-y-3">
                    <h2 className="font-display text-heading-lg text-re-text-primary">
                        Supplier FSMA 204 gap checklist
                    </h2>
                    <p className="text-body text-re-text-secondary">
                        Check off each FSMA 204 requirement your company currently meets.
                        This is a self-reported gap list, not a readiness score or a retailer approval.
                    </p>
                </div>

                {/* Score Bar */}
                <Card padding="compact" className="mb-8">
                    <div className="flex items-center justify-between gap-4">
                        <div>
                            <p className="text-label text-re-text-muted">
                                Coverage and completeness checklist
                            </p>
                            <div className="mt-2 flex items-baseline gap-1">
                                <span className="font-mono text-title tabular-nums text-re-text-primary">
                                    {checkedCount}
                                </span>
                                <span className="font-mono text-ui text-re-text-tertiary">/{total}</span>
                            </div>
                        </div>
                        <div className="flex flex-wrap items-center justify-end gap-1" aria-hidden="true">
                            {checklistItems.map((item) => (
                                <span
                                    key={item.id}
                                    className={cn(
                                        "h-1.5 w-5 rounded-sm transition-colors duration-180 motion-reduce:transition-none sm:w-7",
                                        checked[item.id] ? scoreBarClass : "bg-re-surface-inset"
                                    )}
                                />
                            ))}
                        </div>
                    </div>
                </Card>

                {/* Checklist */}
                <ul className="mb-8 flex flex-col gap-2">
                    {checklistItems.map((item) => {
                        const isChecked = Boolean(checked[item.id]);
                        return (
                            <li
                                key={item.id}
                                className={cn(
                                    "flex items-start gap-3 rounded-lg border px-4 py-3 transition-colors duration-120 motion-reduce:transition-none",
                                    isChecked
                                        ? "border-re-border-strong bg-re-surface-inset"
                                        : "border-re-border bg-re-surface-card"
                                )}
                            >
                                <button
                                    type="button"
                                    onClick={() => toggle(item.id)}
                                    aria-pressed={isChecked}
                                    className="flex min-h-12 flex-1 items-start gap-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-surface-card"
                                >
                                    {/* Check indicator */}
                                    <span
                                        aria-hidden="true"
                                        className={cn(
                                            "mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-md border transition-colors duration-120 motion-reduce:transition-none",
                                            isChecked
                                                ? "border-transparent bg-re-brand text-re-brand-foreground"
                                                : "border-re-border-strong"
                                        )}
                                    >
                                        {isChecked && <Check className="h-4 w-4" strokeWidth={1.75} />}
                                    </span>

                                    {/* Content */}
                                    <span className="min-w-0 flex-1">
                                        <span
                                            className={cn(
                                                "block text-subheading",
                                                isChecked
                                                    ? "text-re-text-tertiary line-through"
                                                    : "text-re-text-primary"
                                            )}
                                        >
                                            {item.title}
                                        </span>
                                        <span className="mt-1 block text-small text-re-text-tertiary">
                                            {item.description}
                                        </span>
                                    </span>
                                </button>

                                {/* CFR Reference */}
                                <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="mt-1 hidden whitespace-nowrap font-mono text-label text-re-brand underline-offset-[3px] hover:underline sm:inline"
                                >
                                    {item.regulation}
                                </a>
                            </li>
                        );
                    })}
                </ul>

                {/* Check Results Button */}
                {!showResults && (
                    <Button
                        size="lg"
                        className="w-full"
                        onClick={() => setShowResults(true)}
                        disabled={checkedCount === 0}
                    >
                        {checkedCount === 0
                            ? "Check at least one item to see your results"
                            : `See My Results`}
                        {checkedCount > 0 && (
                            <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        )}
                    </Button>
                )}

                {/* Results */}
                {showResults && (
                    <div>
                        {allChecked ? (
                            /* All Checked */
                            <Card padding="spacious" className="text-center">
                                <ShieldCheck
                                    className="mx-auto mb-4 h-6 w-6 text-re-success"
                                    strokeWidth={1.75}
                                    aria-hidden="true"
                                />
                                <h3 className="mb-2 text-heading text-re-text-primary">
                                    All listed items checked
                                </h3>
                                <p className="mx-auto mb-6 max-w-[48ch] text-ui text-re-text-secondary">
                                    You marked every item on this self-reported checklist. That is a gap
                                    summary, not retailer approval, FDA certification, or a readiness score.
                                </p>
                                <Button asChild>
                                    <Link href="/tools/ftl-checker">
                                        Try the FTL Checker
                                        <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                    </Link>
                                </Button>
                            </Card>
                        ) : (
                            /* Gaps Found */
                            <div>
                                <div
                                    className={cn(
                                        "mb-5 rounded-md border border-l-[3px] border-re-border bg-re-surface-card px-4 py-4",
                                        bandRailClass
                                    )}
                                >
                                    <div className="mb-3 flex items-center gap-2.5">
                                        <AlertCircle
                                            className={cn("h-5 w-5 shrink-0", bandIconClass)}
                                            strokeWidth={1.75}
                                            aria-hidden="true"
                                        />
                                        <span className="text-subheading text-re-text-primary">
                                            {total - checkedCount} Gap{total - checkedCount > 1 ? "s" : ""} Found
                                        </span>
                                    </div>
                                    <p className="mb-4 text-ui text-re-text-secondary">
                                        {checkedCount <= 3
                                            ? "Several checklist items remain unchecked. Treat these as gap candidates to review against your buyer and FDA obligations."
                                            : checkedCount <= 5
                                                ? "Some foundation items are checked, and critical gaps remain. Review the unchecked items against retailer and FDA expectations."
                                                : "Most listed items are checked. Review the remaining gaps against your buyer requirements before treating the list as complete."}
                                    </p>

                                    {/* Gap List */}
                                    <ul className="flex flex-col gap-2">
                                        {uncheckedItems.map((item) => (
                                            <li
                                                key={item.id}
                                                className="flex items-center gap-2.5 rounded-md bg-re-surface-inset px-3 py-2.5 text-ui"
                                            >
                                                <X
                                                    className={cn("h-4 w-4 shrink-0", bandIconClass)}
                                                    strokeWidth={1.75}
                                                    aria-hidden="true"
                                                />
                                                <span className="min-w-0 text-re-text-secondary">{item.title}</span>
                                                <a
                                                    href={item.url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="ml-auto whitespace-nowrap font-mono text-label text-re-brand underline-offset-[3px] hover:underline"
                                                >
                                                    {item.regulation}
                                                </a>
                                            </li>
                                        ))}
                                    </ul>
                                </div>

                                {/* Consultation CTA */}
                                {!submitted ? (
                                    <Card padding="spacious">
                                        <h3 className="mb-1.5 text-heading text-re-text-primary">
                                            Free Gap Analysis
                                        </h3>
                                        <p className="mb-5 text-ui text-re-text-secondary">
                                            I&apos;ll personally review your {total - checkedCount} gap
                                            {total - checkedCount > 1 ? "s" : ""} and send you a
                                            prioritized remediation plan within 24 hours.
                                        </p>
                                        <div className="flex flex-col gap-2.5">
                                            <div>
                                                <label htmlFor="gap-analysis-company" className="sr-only">
                                                    Company name
                                                </label>
                                                <Input
                                                    id="gap-analysis-company"
                                                    size="lg"
                                                    type="text"
                                                    placeholder="Company name"
                                                    value={company}
                                                    onChange={(e) => setCompany(e.target.value)}
                                                />
                                            </div>
                                            <div>
                                                <label htmlFor="gap-analysis-email" className="sr-only">
                                                    Work email
                                                </label>
                                                <Input
                                                    id="gap-analysis-email"
                                                    size="lg"
                                                    type="email"
                                                    placeholder="Work email"
                                                    value={email}
                                                    onChange={(e) => setEmail(e.target.value)}
                                                />
                                            </div>
                                            <Button
                                                size="lg"
                                                onClick={handleSubmit}
                                                disabled={!email || !company}
                                            >
                                                Get Free Gap Analysis
                                                <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                                            </Button>
                                            {submissionError && (
                                                <p role="alert" className="mt-1 text-small text-re-danger">
                                                    {submissionError}
                                                </p>
                                            )}
                                        </div>
                                        <p className="mt-3 text-small text-re-text-tertiary">
                                            No commitment. No sales pitch. Just a technical review from the founder.
                                        </p>
                                    </Card>
                                ) : (
                                    <Card padding="spacious" className="text-center">
                                        <h3 className="mb-2 text-heading text-re-text-primary">
                                            Gap analysis on its way
                                        </h3>
                                        <p className="text-ui text-re-text-secondary">
                                            I&apos;ll review your {total - checkedCount} gap
                                            {total - checkedCount > 1 ? "s" : ""} and send a prioritized
                                            remediation plan to {email} within 24 hours.
                                        </p>
                                    </Card>
                                )}
                            </div>
                        )}

                        {/* Reset */}
                        <div className="mt-5 flex justify-center">
                            <Button
                                variant="secondary"
                                onClick={() => {
                                    setChecked({});
                                    setShowResults(false);
                                    setSubmitted(false);
                                    setEmail("");
                                    setCompany("");
                                }}
                            >
                                Start Over
                            </Button>
                        </div>
                    </div>
                )}
            </Container>
        </section>
    );
}
