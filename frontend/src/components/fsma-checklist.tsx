'use client';

import { useState, useEffect } from "react";
import Link from "next/link";

const checklistItems = [
    {
        id: "harvest",
        title: "Harvest CTEs captured",
        description: "Growing and harvesting events with lot codes assigned at point of harvest",
        regulation: "21 CFR § 1.1325(b)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1325",
    },
    {
        id: "shipping",
        title: "Shipping CTEs captured",
        description: "All outbound shipments with Traceability Lot Codes linked to each unit",
        regulation: "21 CFR § 1.1350(b)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1350",
    },
    {
        id: "receiving",
        title: "Receiving CTEs captured",
        description: "Inbound receiving events with supplier data and TLC verification",
        regulation: "21 CFR § 1.1345(b)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1345",
    },
    {
        id: "transformation",
        title: "Transformation CTEs captured",
        description: "Processing, packing, and repacking events with new TLCs assigned",
        regulation: "21 CFR § 1.1335(b)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1335",
    },
    {
        id: "kdes",
        title: "All KDEs populated",
        description: "Key Data Elements recorded for each Critical Tracking Event type",
        regulation: "21 CFR § 1.1315",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1315",
    },
    {
        id: "tlc_linkage",
        title: "TLCs linked across events",
        description: "Traceability Lot Codes connected end-to-end across your supply chain",
        regulation: "21 CFR § 1.1320",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1320",
    },
    {
        id: "response_time",
        title: "24-hour response capability",
        description: "Can provide FDA with requested traceability data within 24 hours",
        regulation: "21 CFR § 1.1455",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455",
    },
    {
        id: "electronic",
        title: "Electronic recordkeeping",
        description: "Sortable, searchable electronic records — not paper or static spreadsheets",
        regulation: "21 CFR § 1.1455(b)(3)",
        url: "https://www.ecfr.gov/current/title-21/chapter-I/subchapter-A/part-1/subpart-S/section-1.1455",
    },
];

function CheckIcon() {
    return (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
            <path
                d="M4 9.5L7.5 13L14 5"
                stroke="white"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
}

function AlertIcon() {
    return (
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path
                d="M10 6V10M10 14H10.01"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
            />
            <circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="1.5" />
        </svg>
    );
}

function ShieldIcon() {
    return (
        <svg width="22" height="22" viewBox="0 0 24 24" fill="none">
            <path
                d="M12 2L4 6V12C4 16.4 7.4 20.5 12 22C16.6 20.5 20 16.4 20 12V6L12 2Z"
                stroke="currentColor"
                strokeWidth="1.5"
                fill="none"
            />
            <path
                d="M8.5 12L11 14.5L16 9"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
            />
        </svg>
    );
}

export default function FSMAChecklist() {
    const [checked, setChecked] = useState<Record<string, boolean>>({});
    const [showResults, setShowResults] = useState(false);
    const [email, setEmail] = useState("");
    const [company, setCompany] = useState("");
    const [submitted, setSubmitted] = useState(false);
    const [animateIn, setAnimateIn] = useState(false);

    useEffect(() => {
        setAnimateIn(true);
    }, []);

    const checkedCount = Object.values(checked).filter(Boolean).length;
    const total = checklistItems.length;
    const allChecked = checkedCount === total;
    const uncheckedItems = checklistItems.filter((item) => !checked[item.id]);

    const toggle = (id: string) => {
        setChecked((prev) => ({ ...prev, [id]: !prev[id] }));
        setShowResults(false);
        setSubmitted(false);
    };

    const handleSubmit = () => {
        if (email && company) {
            localStorage.setItem('fsma_gap_analysis_lead', JSON.stringify({
                email,
                company,
                gaps: uncheckedItems.map(i => i.title),
                date: new Date().toISOString()
            }));
            setSubmitted(true);
        }
    };

    const scoreColor =
        checkedCount <= 3
            ? "#dc2626"
            : checkedCount <= 5
                ? "#d97706"
                : checkedCount <= 7
                    ? "#2563eb"
                    : "#059669";

    return (
        <div className="bg-[#0a0e17] text-[#e2e8f0] py-16 px-4">
            <div className="max-w-[720px] mx-auto">
                {/* Title */}
                <div
                    className="mb-12 transition-all duration-500"
                    style={{
                        opacity: animateIn ? 1 : 0,
                        transform: animateIn ? "translateY(0)" : "translateY(12px)",
                    }}
                >
                    <h2 className="text-3xl font-bold text-[#f8fafc] mb-3">
                        Are You Retailer-Ready?
                    </h2>
                    <p className="text-base text-[#64748b]">
                        Check off each FSMA 204 requirement your company currently meets.
                        Be honest — gaps are fixable, surprises during an FDA audit aren't.
                    </p>
                </div>

                {/* Score Bar */}
                <div className="bg-white/[0.03] border border-white/[0.06] rounded-xl p-5 mb-8 flex items-center justify-between">
                    <div>
                        <div className="text-sm text-[#64748b] mb-2 font-medium">
                            Compliance Score
                        </div>
                        <div className="flex items-baseline gap-1">
                            <span
                                className="text-4xl font-bold font-mono transition-colors duration-300"
                                style={{ color: scoreColor }}
                            >
                                {checkedCount}
                            </span>
                            <span className="text-lg text-[#475569] font-mono">/{total}</span>
                        </div>
                    </div>
                    <div className="flex gap-1 items-center">
                        {checklistItems.map((item) => (
                            <div
                                key={item.id}
                                className="w-7 h-1.5 rounded-sm transition-all duration-300"
                                style={{
                                    background: checked[item.id] ? scoreColor : "rgba(255,255,255,0.06)",
                                }}
                            />
                        ))}
                    </div>
                </div>

                {/* Checklist */}
                <div className="flex flex-col gap-2 mb-8">
                    {checklistItems.map((item, index) => {
                        const isChecked = checked[item.id];
                        return (
                            <button
                                key={item.id}
                                onClick={() => toggle(item.id)}
                                className="flex items-start gap-4 p-[18px] rounded-lg cursor-pointer text-left w-full transition-all duration-200"
                                style={{
                                    background: isChecked ? "rgba(5, 150, 105, 0.06)" : "rgba(255,255,255,0.02)",
                                    border: `1px solid ${isChecked ? "rgba(5, 150, 105, 0.25)" : "rgba(255,255,255,0.06)"}`,
                                    opacity: animateIn ? 1 : 0,
                                    transform: animateIn ? "translateY(0)" : "translateY(8px)",
                                    transitionDelay: `${index * 50}ms`,
                                }}
                            >
                                {/* Checkbox */}
                                <div
                                    className="w-6 h-6 rounded-md flex items-center justify-center flex-shrink-0 mt-[1px] transition-all duration-200"
                                    style={{
                                        border: isChecked ? "none" : "2px solid rgba(255,255,255,0.15)",
                                        background: isChecked ? "#059669" : "transparent",
                                    }}
                                >
                                    {isChecked && <CheckIcon />}
                                </div>

                                {/* Content */}
                                <div className="flex-1">
                                    <div
                                        className="text-[15px] font-semibold mb-1 transition-colors duration-200"
                                        style={{
                                            color: isChecked ? "#059669" : "#e2e8f0",
                                            textDecoration: isChecked ? "line-through" : "none",
                                            textDecorationColor: "rgba(5,150,105,0.3)",
                                        }}
                                    >
                                        {item.title}
                                    </div>
                                    <div className="text-sm text-[#64748b] leading-relaxed">
                                        {item.description}
                                    </div>
                                </div>

                                {/* CFR Reference */}
                                <a
                                    href={item.url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    onClick={(e) => e.stopPropagation()}
                                    className="text-[11px] font-mono text-[#60a5fa] whitespace-nowrap mt-[3px] hover:underline"
                                >
                                    {item.regulation}
                                </a>
                            </button>
                        );
                    })}
                </div>

                {/* Check Results Button */}
                {!showResults && (
                    <button
                        onClick={() => setShowResults(true)}
                        disabled={checkedCount === 0}
                        className="w-full p-4 rounded-lg text-[15px] font-semibold transition-all duration-300"
                        style={{
                            background: checkedCount === 0 ? "rgba(255,255,255,0.04)" : scoreColor,
                            color: checkedCount === 0 ? "#64748b" : "#fff",
                            border: checkedCount === 0 ? "1px solid rgba(255,255,255,0.08)" : "none",
                            opacity: checkedCount === 0 ? 0.5 : 1,
                            cursor: checkedCount === 0 ? "default" : "pointer",
                        }}
                    >
                        {checkedCount === 0
                            ? "Check at least one item to see your results"
                            : `See My Results →`}
                    </button>
                )}

                {/* Results */}
                {showResults && (
                    <div className="animate-in fade-in slide-in-from-bottom-3 duration-400">
                        {allChecked ? (
                            /* All 8 Checked */
                            <div className="bg-[rgba(5,150,105,0.08)] border border-[rgba(5,150,105,0.2)] rounded-xl p-8 text-center">
                                <div className="text-[#059669] mb-4">
                                    <ShieldIcon />
                                </div>
                                <h3 className="text-[22px] font-bold text-[#059669] mb-2">
                                    You're Retailer-Ready
                                </h3>
                                <p className="text-sm text-[#64748b] mb-6 leading-relaxed">
                                    All 8 FSMA 204 requirements met. Want to automate your compliance
                                    monitoring and get alerts when regulations change?
                                </p>
                                <Link
                                    href="/ftl-checker"
                                    className="inline-block py-3 px-7 bg-[#059669] text-white rounded-lg text-sm font-semibold hover:brightness-105 transition-all"
                                >
                                    Try the FTL Checker →
                                </Link>
                            </div>
                        ) : (
                            /* Gaps Found */
                            <div>
                                <div
                                    className="rounded-xl p-6 mb-5"
                                    style={{
                                        background:
                                            checkedCount <= 3
                                                ? "rgba(220,38,38,0.08)"
                                                : checkedCount <= 5
                                                    ? "rgba(217,119,6,0.08)"
                                                    : "rgba(37,99,235,0.08)",
                                        border: `1px solid ${checkedCount <= 3
                                            ? "rgba(220,38,38,0.2)"
                                            : checkedCount <= 5
                                                ? "rgba(217,119,6,0.2)"
                                                : "rgba(37,99,235,0.2)"
                                            }`,
                                    }}
                                >
                                    <div
                                        className="flex items-center gap-2.5 mb-3"
                                        style={{ color: scoreColor }}
                                    >
                                        <AlertIcon />
                                        <span className="text-base font-bold">
                                            {total - checkedCount} Gap{total - checkedCount > 1 ? "s" : ""} Found
                                        </span>
                                    </div>
                                    <p className="text-sm text-[#94a3b8] mb-4 leading-relaxed">
                                        {checkedCount <= 3
                                            ? "Your traceability infrastructure needs significant work before you're retailer-ready. The good news: these are solvable problems."
                                            : checkedCount <= 5
                                                ? "You've got a foundation, but critical gaps remain. Major retailers are actively evaluating suppliers on these exact requirements."
                                                : "You're close. A few targeted fixes will get you to full compliance."}
                                    </p>

                                    {/* Gap List */}
                                    <div className="flex flex-col gap-2">
                                        {uncheckedItems.map((item) => (
                                            <div
                                                key={item.id}
                                                className="flex items-center gap-2.5 py-2.5 px-3.5 bg-black/20 rounded-lg text-sm"
                                            >
                                                <span style={{ color: scoreColor }}>✗</span>
                                                <span className="text-[#cbd5e1]">{item.title}</span>
                                                <a
                                                    href={item.url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="ml-auto font-mono text-[10px] text-[#60a5fa] hover:underline"
                                                >
                                                    {item.regulation}
                                                </a>
                                            </div>
                                        ))}
                                    </div>
                                </div>

                                {/* Consultation CTA */}
                                {!submitted ? (
                                    <div className="bg-white/[0.03] border border-white/[0.08] rounded-xl p-7">
                                        <h3 className="text-lg font-bold text-[#f8fafc] mb-1.5">
                                            Free Gap Analysis
                                        </h3>
                                        <p className="text-sm text-[#64748b] mb-5 leading-relaxed">
                                            I'll personally review your {total - checkedCount} gap
                                            {total - checkedCount > 1 ? "s" : ""} and send you a
                                            prioritized remediation plan within 24 hours.
                                        </p>
                                        <div className="flex flex-col gap-2.5">
                                            <input
                                                type="text"
                                                placeholder="Company name"
                                                value={company}
                                                onChange={(e) => setCompany(e.target.value)}
                                                className="p-3 bg-black/30 border border-white/[0.08] rounded-lg text-[#e2e8f0] text-sm outline-none placeholder:text-[#475569]"
                                            />
                                            <input
                                                type="email"
                                                placeholder="Work email"
                                                value={email}
                                                onChange={(e) => setEmail(e.target.value)}
                                                className="p-3 bg-black/30 border border-white/[0.08] rounded-lg text-[#e2e8f0] text-sm outline-none placeholder:text-[#475569]"
                                            />
                                            <button
                                                onClick={handleSubmit}
                                                disabled={!email || !company}
                                                className="p-3.5 rounded-lg text-[15px] font-semibold transition-all duration-200"
                                                style={{
                                                    background: email && company ? "#2563eb" : "rgba(255,255,255,0.04)",
                                                    color: email && company ? "#fff" : "#475569",
                                                    cursor: email && company ? "pointer" : "default",
                                                }}
                                            >
                                                Get Free Gap Analysis →
                                            </button>
                                        </div>
                                        <p className="text-xs text-[#475569] mt-3">
                                            No commitment. No sales pitch. Just a technical review from the founder.
                                        </p>
                                    </div>
                                ) : (
                                    <div className="bg-[rgba(37,99,235,0.08)] border border-[rgba(37,99,235,0.2)] rounded-xl p-7 text-center">
                                        <h3 className="text-lg font-bold text-[#60a5fa] mb-2">
                                            Gap analysis on its way
                                        </h3>
                                        <p className="text-sm text-[#94a3b8] leading-relaxed">
                                            I'll review your {total - checkedCount} gap
                                            {total - checkedCount > 1 ? "s" : ""} and send a prioritized
                                            remediation plan to {email} within 24 hours.
                                        </p>
                                    </div>
                                )}
                            </div>
                        )}

                        {/* Reset */}
                        <button
                            onClick={() => {
                                setChecked({});
                                setShowResults(false);
                                setSubmitted(false);
                                setEmail("");
                                setCompany("");
                            }}
                            className="block mx-auto mt-5 py-2.5 px-5 bg-transparent border border-white/[0.08] rounded-lg text-[#64748b] text-sm cursor-pointer hover:border-white/20 transition-all"
                        >
                            Start Over
                        </button>
                    </div>
                )}
            </div>
        </div>
    );
}
