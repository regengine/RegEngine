"use client";

import { useState, useCallback, useMemo } from 'react';
import Link from 'next/link';
import {
    Shield,
    FileWarning,
    CheckCircle2,
    XCircle,
    AlertTriangle,
    ArrowRight,
    RotateCcw,
    ClipboardPaste,
    Info,
    Scale,
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────────
   REQUIREMENT DEFINITIONS
   ───────────────────────────────────────────────────────────── */

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
    // ECOA Requirements
    {
        id: 'ecoa-statement',
        regulation: 'ECOA',
        citation: '12 CFR 1002.9(a)(1)',
        label: 'Statement of Action Taken',
        description: 'Notice must include a clear statement that the application was denied or credit terms changed.',
        keywords: ['denied', 'denial', 'adverse action', 'not approved', 'unable to approve', 'declined', 'reject', 'cannot extend credit', 'credit was not granted', 'application was not approved'],
        weight: 'critical',
    },
    {
        id: 'ecoa-reasons',
        regulation: 'ECOA',
        citation: '12 CFR 1002.9(b)(2)',
        label: 'Specific Reason(s) for Denial',
        description: 'Must include specific reasons for the adverse action or disclose the right to request reasons within 60 days.',
        keywords: ['reason', 'because', 'due to', 'based on', 'factor', 'insufficient', 'too high', 'too low', 'lack of', 'limited', 'excessive', 'inadequate', 'unable to verify', 'right to request', 'statement of reasons', 'within 60 days'],
        weight: 'critical',
    },
    {
        id: 'ecoa-creditor-info',
        regulation: 'ECOA',
        citation: '12 CFR 1002.9(a)(1)',
        label: 'Creditor Name & Address',
        description: 'Notice must identify the creditor with name and address.',
        keywords: ['inc', 'llc', 'corp', 'bank', 'credit union', 'financial', 'lending', 'street', 'avenue', 'blvd', 'suite', 'floor', 'address', 'p.o. box', 'po box'],
        weight: 'critical',
    },
    {
        id: 'ecoa-prohibited',
        regulation: 'ECOA',
        citation: '12 CFR 1002.9(b)(1)',
        label: 'ECOA Anti-Discrimination Notice',
        description: 'Must include notice of ECOA protections — that federal law prohibits discrimination on the basis of race, color, religion, national origin, sex, marital status, or age.',
        keywords: ['equal credit opportunity', 'ecoa', 'federal law prohibits', 'discrimination', 'race', 'color', 'religion', 'national origin', 'sex', 'marital status', 'age', 'public assistance', 'good faith'],
        weight: 'critical',
    },
    {
        id: 'ecoa-cfpb',
        regulation: 'ECOA',
        citation: '12 CFR 1002.9(a)(1)',
        label: 'CFPB / Regulator Contact',
        description: 'Notice should provide contact information for the Consumer Financial Protection Bureau or applicable regulator.',
        keywords: ['cfpb', 'consumer financial protection', 'bureau', 'complaint', 'consumerfinance.gov', 'regulator', 'federal reserve', 'occ', 'fdic', 'ncua', '1-855', '855-411-2372'],
        weight: 'important',
    },
    // FCRA Requirements
    {
        id: 'fcra-cra',
        regulation: 'FCRA',
        citation: '15 U.S.C. § 1681m(a)',
        label: 'Credit Reporting Agency (CRA) Identification',
        description: 'If based on a consumer report, must identify the CRA that furnished the report, including name, address, and phone number.',
        keywords: ['experian', 'equifax', 'transunion', 'credit bureau', 'reporting agency', 'consumer reporting', 'credit report', 'furnished', 'cra'],
        weight: 'critical',
    },
    {
        id: 'fcra-cra-disclaimer',
        regulation: 'FCRA',
        citation: '15 U.S.C. § 1681m(a)',
        label: 'CRA Non-Decision Disclaimer',
        description: 'Must state that the CRA did not make the decision and is unable to provide specific reasons for the action.',
        keywords: ['did not make', 'unable to provide', 'not involved', 'did not participate', 'cannot explain', 'CRA did not', 'agency did not', 'bureau did not'],
        weight: 'important',
    },
    {
        id: 'fcra-dispute',
        regulation: 'FCRA',
        citation: '15 U.S.C. § 1681m(a)(3)',
        label: 'Right to Dispute & Free Report',
        description: 'Must inform the consumer of their right to obtain a free copy of their report within 60 days and to dispute the accuracy of information.',
        keywords: ['free copy', 'free report', 'dispute', 'accuracy', 'inaccuracy', 'right to obtain', '60 days', 'sixty days', 'challenge', 'contest'],
        weight: 'critical',
    },
    {
        id: 'fcra-score',
        regulation: 'FCRA',
        citation: '15 U.S.C. § 1681g(f)',
        label: 'Credit Score Disclosure',
        description: 'If a credit score was used, must disclose the score, range, key factors, and date the score was generated.',
        keywords: ['credit score', 'score of', 'score:', 'fico', 'vantage', 'score range', 'key factor', 'score was', 'scored', 'scoring model'],
        weight: 'important',
    },
    // Timing & Delivery
    {
        id: 'timing',
        regulation: 'ECOA',
        citation: '12 CFR 1002.9(a)(1)',
        label: '30-Day Delivery Requirement',
        description: 'Notice must be delivered within 30 days of taking adverse action or receiving a completed application.',
        keywords: ['30 day', 'thirty day', 'within 30', 'date of application', 'date of decision', 'date:', 'dated:'],
        weight: 'recommended',
    },
    {
        id: 'applicant-info',
        regulation: 'ECOA',
        citation: '12 CFR 1002.9(a)(1)',
        label: 'Applicant Identification',
        description: 'Notice should identify the applicant and reference the specific application.',
        keywords: ['dear', 'applicant', 'application', 'reference', 'account', 'loan number', 'application number', 'application id', 'applied on', 'submitted on', 're:'],
        weight: 'recommended',
    },
];

const SAMPLE_NOTICES = {
    good: `Dear John Smith,

Re: Credit Card Application #A-2024-88321

After careful review of your application submitted on January 15, 2025, we regret to inform you that we are unable to approve your request for a Platinum Rewards Credit Card. This letter serves as your adverse action notice.

Specific Reasons for Denial:
1. Debt-to-income ratio exceeds our lending criteria
2. Insufficient length of credit history
3. Recent derogatory marks on credit report

This decision was based in part on information obtained from your consumer report provided by:
Experian
P.O. Box 4500
Allen, TX 75013
Phone: 1-888-397-3742

The consumer reporting agency listed above did not make the decision to take adverse action and is unable to provide specific reasons for this decision.

Your Rights Under Federal Law:
- You have the right to obtain a free copy of your consumer report from the reporting agency within 60 days of this notice
- You have the right to dispute the accuracy or completeness of any information in your report
- Your credit score used in this decision was 621 (range: 300-850), generated on January 14, 2025. Key factors: high revolving utilization, limited credit history length

Under the Equal Credit Opportunity Act (ECOA), the federal law prohibits creditors from discriminating against credit applicants on the basis of race, color, religion, national origin, sex, marital status, age (provided the applicant has the capacity to enter into a binding contract), because all or part of the applicant's income derives from any public assistance program, or because the applicant has in good faith exercised any right under the Consumer Credit Protection Act.

If you believe you have been discriminated against, you may file a complaint with:
Consumer Financial Protection Bureau (CFPB)
www.consumerfinance.gov
1-855-411-2372

Sincerely,
First National Bank
123 Main Street, Suite 400
New York, NY 10001`,

    bad: `Dear Customer,

We reviewed your application and unfortunately we cannot approve your request at this time.

Thank you,
ABC Financial`,
};

/* ─────────────────────────────────────────────────────────────
   COMPONENT
   ───────────────────────────────────────────────────────────── */

export default function NoticeValidatorPage() {
    const [noticeText, setNoticeText] = useState('');
    const [hasAnalyzed, setHasAnalyzed] = useState(false);

    const results = useMemo(() => {
        if (!hasAnalyzed || !noticeText.trim()) return null;

        const lower = noticeText.toLowerCase();
        const checks = REQUIREMENTS.map(req => {
            const found = req.keywords.some(kw => lower.includes(kw.toLowerCase()));
            return { ...req, found };
        });

        const critical = checks.filter(c => c.weight === 'critical');
        const important = checks.filter(c => c.weight === 'important');
        const recommended = checks.filter(c => c.weight === 'recommended');

        const criticalPass = critical.filter(c => c.found).length;
        const importantPass = important.filter(c => c.found).length;
        const recommendedPass = recommended.filter(c => c.found).length;

        const score = Math.round(
            ((criticalPass / critical.length) * 60 +
                (importantPass / important.length) * 25 +
                (recommendedPass / recommended.length) * 15)
        );

        let grade: 'A' | 'B' | 'C' | 'D' | 'F';
        if (score >= 90) grade = 'A';
        else if (score >= 75) grade = 'B';
        else if (score >= 60) grade = 'C';
        else if (score >= 40) grade = 'D';
        else grade = 'F';

        return { checks, score, grade, criticalPass, criticalTotal: critical.length, importantPass, importantTotal: important.length, recommendedPass, recommendedTotal: recommended.length };
    }, [noticeText, hasAnalyzed]);

    const analyze = useCallback(() => {
        if (noticeText.trim()) setHasAnalyzed(true);
    }, [noticeText]);

    const loadSample = useCallback((type: 'good' | 'bad') => {
        setNoticeText(SAMPLE_NOTICES[type]);
        setHasAnalyzed(false);
    }, []);

    const reset = useCallback(() => {
        setNoticeText('');
        setHasAnalyzed(false);
    }, []);

    const gradeColor = (g?: string) => {
        if (g === 'A') return '#10b981';
        if (g === 'B') return '#3b82f6';
        if (g === 'C') return '#f59e0b';
        return '#ef4444';
    };

    return (
        <>
            <style jsx global>{`
        :root {
          --nv-bg: #09090b;
          --nv-surface: #0f0f13;
          --nv-elevated: #16161d;
          --nv-border: rgba(255,255,255,0.08);
          --nv-border-strong: rgba(255,255,255,0.15);
          --nv-text: #e4e4e7;
          --nv-text-muted: #71717a;
          --nv-text-dim: #52525b;
          --nv-accent: #10b981;
          --nv-accent-hover: #34d399;
          --nv-fail: #ef4444;
          --nv-warn: #f59e0b;
          --nv-pass: #10b981;
        }
        .nv-page {
          min-height: 100vh;
          background: var(--nv-bg);
          color: var(--nv-text);
          font-family: 'Instrument Sans', 'Inter', system-ui, sans-serif;
        }
        .nv-container { max-width: 1100px; margin: 0 auto; padding: 0 1.5rem; }

        .nv-header { padding: 2rem 0; border-bottom: 1px solid var(--nv-border); }
        .nv-breadcrumb {
          display: flex; align-items: center; gap: 0.5rem;
          font-size: 0.8rem; color: var(--nv-text-muted); margin-bottom: 1.5rem;
        }
        .nv-breadcrumb a { color: var(--nv-text-muted); text-decoration: none; }
        .nv-breadcrumb a:hover { color: var(--nv-accent); }
        .nv-badge-free {
          display: inline-flex; align-items: center; gap: 0.35rem;
          background: rgba(16,185,129,0.1); color: var(--nv-accent);
          font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
          padding: 0.25rem 0.6rem; border-radius: 4px; border: 1px solid rgba(16,185,129,0.2); margin-bottom: 0.75rem;
        }
        .nv-page h1 { font-size: 2rem; font-weight: 700; margin: 0 0 0.75rem; letter-spacing: -0.025em; }
        .nv-subtitle { font-size: 1.05rem; color: var(--nv-text-muted); line-height: 1.6; max-width: 650px; }
        .nv-section-label {
          font-size: 0.7rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.1em;
          color: var(--nv-text-dim); margin-bottom: 1rem; margin-top: 2rem;
        }

        /* Samples */
        .nv-samples { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 1rem 0 1.5rem; }
        .nv-sample-btn {
          background: var(--nv-surface); border: 1px solid var(--nv-border);
          color: var(--nv-text-muted); padding: 0.5rem 1rem; border-radius: 6px;
          font-size: 0.8rem; cursor: pointer; transition: all 0.15s;
        }
        .nv-sample-btn:hover { border-color: var(--nv-border-strong); color: var(--nv-text); }

        /* Textarea */
        .nv-textarea {
          width: 100%; min-height: 300px; max-height: 600px;
          background: var(--nv-surface); border: 1px solid var(--nv-border);
          color: var(--nv-text); padding: 1.25rem; border-radius: 10px;
          font-family: 'JetBrains Mono', monospace; font-size: 0.82rem;
          line-height: 1.7; resize: vertical; transition: border-color 0.15s;
        }
        .nv-textarea:focus { outline: none; border-color: var(--nv-accent); }
        .nv-textarea::placeholder { color: var(--nv-text-dim); }
        .nv-char-count {
          text-align: right; font-size: 0.72rem; color: var(--nv-text-dim);
          font-family: 'JetBrains Mono', monospace; margin-top: 0.5rem;
        }

        /* Actions */
        .nv-actions { display: flex; gap: 0.75rem; margin: 1.5rem 0 2rem; flex-wrap: wrap; }
        .nv-btn {
          display: inline-flex; align-items: center; gap: 0.4rem;
          padding: 0.6rem 1.2rem; border-radius: 6px; font-size: 0.85rem;
          font-weight: 500; cursor: pointer; transition: all 0.15s; border: 1px solid transparent;
        }
        .nv-btn-primary {
          background: var(--nv-accent); color: #000; border-color: var(--nv-accent);
        }
        .nv-btn-primary:hover { background: var(--nv-accent-hover); }
        .nv-btn-primary:disabled { opacity: 0.4; cursor: not-allowed; }
        .nv-btn-secondary {
          background: var(--nv-surface); color: var(--nv-text-muted); border-color: var(--nv-border);
        }
        .nv-btn-secondary:hover { border-color: var(--nv-border-strong); color: var(--nv-text); }

        /* Score */
        .nv-score-panel {
          display: flex; align-items: center; gap: 2rem;
          padding: 1.5rem; border-radius: 10px;
          border: 1px solid var(--nv-border); margin-bottom: 1.5rem;
        }
        .nv-grade {
          width: 80px; height: 80px; border-radius: 50%;
          display: flex; align-items: center; justify-content: center;
          font-size: 2rem; font-weight: 800; font-family: 'JetBrains Mono', monospace;
          flex-shrink: 0; border: 3px solid;
        }
        .nv-score-details h3 { font-size: 1.1rem; font-weight: 600; margin: 0 0 0.35rem; }
        .nv-score-details p { font-size: 0.85rem; color: var(--nv-text-muted); margin: 0; line-height: 1.5; }
        .nv-score-bar {
          display: flex; gap: 1.5rem; margin-top: 0.75rem; flex-wrap: wrap;
        }
        .nv-score-item { font-size: 0.78rem; }
        .nv-score-num {
          font-family: 'JetBrains Mono', monospace; font-weight: 700; margin-right: 0.25rem;
        }

        /* Check Cards */
        .nv-checks { margin: 1.5rem 0; }
        .nv-check-group-title {
          font-size: 0.8rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em;
          margin: 1.5rem 0 0.75rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--nv-border);
        }
        .nv-check {
          display: flex; align-items: flex-start; gap: 0.75rem;
          padding: 1rem 1.25rem; margin-bottom: 0.5rem;
          background: var(--nv-surface); border: 1px solid var(--nv-border);
          border-radius: 8px; transition: border-color 0.15s;
        }
        .nv-check:hover { border-color: var(--nv-border-strong); }
        .nv-check.pass { border-left: 3px solid var(--nv-pass); }
        .nv-check.fail { border-left: 3px solid var(--nv-fail); }
        .nv-check-icon { flex-shrink: 0; margin-top: 2px; }
        .nv-check-content { flex: 1; min-width: 0; }
        .nv-check-top { display: flex; align-items: center; gap: 0.5rem; flex-wrap: wrap; margin-bottom: 0.25rem; }
        .nv-check-label { font-size: 0.88rem; font-weight: 600; }
        .nv-check-cite {
          font-family: 'JetBrains Mono', monospace; font-size: 0.68rem;
          color: var(--nv-accent); background: rgba(16,185,129,0.08);
          padding: 0.15rem 0.45rem; border-radius: 4px;
        }
        .nv-check-weight {
          font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
          padding: 0.15rem 0.4rem; border-radius: 3px;
        }
        .nv-w-critical { background: rgba(239,68,68,0.15); color: #ef4444; }
        .nv-w-important { background: rgba(245,158,11,0.15); color: #f59e0b; }
        .nv-w-recommended { background: rgba(59,130,246,0.15); color: #3b82f6; }
        .nv-check-desc { font-size: 0.8rem; color: var(--nv-text-muted); line-height: 1.55; }

        /* CTA */
        .nv-cta {
          background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(59,130,246,0.08));
          border: 1px solid rgba(16,185,129,0.2); border-radius: 10px;
          padding: 2rem; text-align: center; margin: 2.5rem 0;
        }
        .nv-cta h3 { font-size: 1.2rem; font-weight: 700; margin: 0 0 0.5rem; }
        .nv-cta p { font-size: 0.9rem; color: var(--nv-text-muted); margin: 0 0 1.25rem; line-height: 1.5; }
        .nv-cta-btn {
          display: inline-flex; align-items: center; gap: 0.5rem;
          background: var(--nv-accent); color: #000; font-weight: 600; font-size: 0.9rem;
          padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; transition: background 0.15s;
        }
        .nv-cta-btn:hover { background: #34d399; }

        .nv-footer {
          border-top: 1px solid var(--nv-border); padding: 2rem 0; margin-top: 3rem;
        }
        .nv-footer-text {
          font-size: 0.78rem; color: var(--nv-text-dim); line-height: 1.65; max-width: 700px;
        }
        .nv-tool-links {
          display: flex; gap: 1rem; margin-top: 0.75rem; flex-wrap: wrap;
        }

        @media (max-width: 768px) {
          .nv-page h1 { font-size: 1.5rem; }
          .nv-score-panel { flex-direction: column; text-align: center; }
        }
      `}</style>

            <div className="nv-page">
                <header className="nv-header">
                    <div className="nv-container">
                        <div className="nv-breadcrumb">
                            <Link href="/">RegEngine</Link>
                            <span>/</span>
                            <Link href="/verticals/finance">Finance</Link>
                            <span>/</span>
                            <span>Notice Validator</span>
                        </div>
                        <div className="flex justify-between items-start">
                            <div>
                                <div className="nv-badge-free"><Shield size={12} /> Free Tool</div>
                                <h1>Adverse Action Notice Validator</h1>
                                <p className="nv-subtitle">
                                    Paste your credit denial notice and instantly validate it against ECOA (Reg B) and FCRA
                                    requirements. Get a compliance grade with specific pass/fail checks for each regulatory element.
                                </p>
                            </div>
                            <div className="shrink-0 pt-8">
                                <FileWarning size={48} strokeWidth={1} color="var(--nv-accent)" />
                            </div>
                        </div>
                    </div>
                </header>

                <main className="nv-container">
                    {/* Sample Notices */}
                    <div className="nv-section-label">LOAD SAMPLE NOTICE</div>
                    <div className="nv-samples">
                        <button className="nv-sample-btn" onClick={() => loadSample('good')}>
                            ✓ Compliant Example (Grade A)
                        </button>
                        <button className="nv-sample-btn" onClick={() => loadSample('bad')}>
                            ✗ Deficient Example (Grade F)
                        </button>
                    </div>

                    {/* Input */}
                    <div className="nv-section-label">PASTE YOUR ADVERSE ACTION NOTICE</div>
                    <textarea
                        className="nv-textarea"
                        placeholder={"Paste the full text of your adverse action notice here...\n\nThe validator checks for:\n• Statement of action taken (ECOA)\n• Specific reasons for denial (ECOA)\n• Creditor identification (ECOA)\n• Anti-discrimination notice (ECOA)\n• CRA identification (FCRA)\n• Right to dispute & free report (FCRA)\n• Credit score disclosure (FCRA)\n• And more..."}
                        value={noticeText}
                        onChange={e => { setNoticeText(e.target.value); setHasAnalyzed(false); }}
                    />
                    <div className="nv-char-count">{noticeText.length.toLocaleString()} characters</div>

                    <div className="nv-actions">
                        <button className="nv-btn nv-btn-primary" onClick={analyze} disabled={!noticeText.trim()}>
                            <Scale size={16} />
                            Validate Notice
                        </button>
                        <button className="nv-btn nv-btn-secondary" onClick={reset}>
                            <RotateCcw size={16} />
                            Clear
                        </button>
                    </div>

                    {/* Results */}
                    {results && (
                        <div>
                            {/* Grade */}
                            <div className="nv-section-label">COMPLIANCE GRADE</div>
                            <div className="nv-score-panel" style={{
                                background: results.grade === 'A' ? 'rgba(16,185,129,0.06)' :
                                    results.grade === 'B' ? 'rgba(59,130,246,0.06)' :
                                        results.grade === 'C' ? 'rgba(245,158,11,0.06)' : 'rgba(239,68,68,0.06)',
                            }}>
                                <div className="nv-grade" style={{
                                    color: gradeColor(results.grade),
                                    borderColor: gradeColor(results.grade),
                                }}>
                                    {results.grade}
                                </div>
                                <div className="nv-score-details">
                                    <h3>
                                        {results.score}% Compliance Score
                                    </h3>
                                    <p>
                                        {results.grade === 'A' ? 'This notice appears to meet all major ECOA and FCRA requirements.'
                                            : results.grade === 'B' ? 'Good coverage of requirements, but some important elements may be missing.'
                                                : results.grade === 'C' ? 'Moderate compliance — several important regulatory elements are missing.'
                                                    : 'Significant compliance gaps detected — this notice may expose your organization to regulatory risk.'}
                                    </p>
                                    <div className="nv-score-bar">
                                        <div className="nv-score-item">
                                            <span className={`nv-score-num ${results.criticalPass === results.criticalTotal ? 'text-[var(--nv-pass)]' : 'text-[var(--nv-fail)]'}`}>
                                                {results.criticalPass}/{results.criticalTotal}
                                            </span>
                                            <span className="text-[var(--nv-text-dim)]">Critical</span>
                                        </div>
                                        <div className="nv-score-item">
                                            <span className={`nv-score-num ${results.importantPass === results.importantTotal ? 'text-[var(--nv-pass)]' : 'text-[var(--nv-warn)]'}`}>
                                                {results.importantPass}/{results.importantTotal}
                                            </span>
                                            <span className="text-[var(--nv-text-dim)]">Important</span>
                                        </div>
                                        <div className="nv-score-item">
                                            <span className="nv-score-num text-[var(--nv-text-muted)]">
                                                {results.recommendedPass}/{results.recommendedTotal}
                                            </span>
                                            <span className="text-[var(--nv-text-dim)]">Recommended</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {/* Individual Checks */}
                            <div className="nv-checks">
                                {(['critical', 'important', 'recommended'] as const).map(weight => {
                                    const items = results.checks.filter(c => c.weight === weight);
                                    return (
                                        <div key={weight}>
                                            <div className={`nv-check-group-title ${
                                                weight === 'critical' ? 'text-[#ef4444]' : weight === 'important' ? 'text-[#f59e0b]' : 'text-[#3b82f6]'
                                            }`}>
                                                {weight === 'critical' ? '🔴 Critical Requirements' : weight === 'important' ? '🟡 Important Requirements' : '🔵 Recommended Elements'}
                                            </div>
                                            {items.map(check => (
                                                <div key={check.id} className={`nv-check ${check.found ? 'pass' : 'fail'}`}>
                                                    <div className="nv-check-icon">
                                                        {check.found
                                                            ? <CheckCircle2 size={18} color="var(--nv-pass)" />
                                                            : <XCircle size={18} color="var(--nv-fail)" />
                                                        }
                                                    </div>
                                                    <div className="nv-check-content">
                                                        <div className="nv-check-top">
                                                            <span className="nv-check-label">{check.label}</span>
                                                            <span className="nv-check-cite">{check.citation}</span>
                                                            <span className={`nv-check-weight nv-w-${check.weight}`}>{check.weight}</span>
                                                        </div>
                                                        <div className="nv-check-desc">{check.description}</div>
                                                    </div>
                                                </div>
                                            ))}
                                        </div>
                                    );
                                })}
                            </div>

                            {/* CTA */}
                            <div className="nv-cta">
                                <h3>Automate Notice Generation</h3>
                                <p>
                                    RegEngine&apos;s Evidence Engine can generate compliant adverse action notices
                                    automatically — pulling reason codes, CRA data, and score disclosures directly
                                    from your decision pipeline.
                                </p>
                                <Link href="/verticals/finance" className="nv-cta-btn">
                                    Explore Finance API <ArrowRight size={16} />
                                </Link>
                            </div>
                        </div>
                    )}

                    {/* Methodology */}
                    {!results && (
                        <div className="bg-[var(--nv-surface)] border border-[var(--nv-border)] rounded-[10px] p-6 my-4">
                            <h3 className="text-[0.95rem] font-semibold m-0 mb-3 flex items-center gap-2">
                                <Info size={16} /> What This Tool Checks
                            </h3>
                            <p className="text-[0.85rem] text-[var(--nv-text-muted)] leading-[1.65] m-0 mb-3">
                                The validator scans your adverse action notice for <strong>11 regulatory requirements</strong> across
                                two federal laws:
                            </p>
                            <ul className="text-[0.85rem] text-[var(--nv-text-muted)] leading-[1.8] pl-5 m-0">
                                <li><strong>ECOA (Reg B)</strong> — Statement of action, specific denial reasons, creditor ID, anti-discrimination notice, CFPB contact, timing, applicant ID</li>
                                <li><strong>FCRA</strong> — CRA identification, CRA non-decision disclaimer, dispute rights & free report, credit score disclosure</li>
                            </ul>
                            <p className="text-[0.8rem] text-[var(--nv-text-dim)] leading-[1.55] mt-3 mb-0 italic">
                                Requirements are weighted: Critical (60%), Important (25%), Recommended (15%). The grade reflects overall
                                regulatory completeness based on keyword presence analysis.
                            </p>
                        </div>
                    )}

                    {/* Footer */}
                    <footer className="nv-footer">
                        <p className="nv-footer-text">
                            This tool performs keyword-based analysis for educational purposes only.
                            It does not guarantee legal compliance. All adverse action notices should be
                            reviewed by qualified legal counsel before use.
                        </p>
                        <div className="nv-tool-links">
                            <Link href="/tools/bias-checker" className="text-[var(--nv-accent)] text-[0.82rem]">
                                AI Model Bias Checker →
                            </Link>
                            <Link href="/tools/obligation-scanner" className="text-[var(--nv-accent)] text-[0.82rem]">
                                Obligation Scanner →
                            </Link>
                            <Link href="/verticals/finance" className="text-[var(--nv-accent)] text-[0.82rem]">
                                ← Finance Vertical
                            </Link>
                        </div>
                    </footer>
                </main>
            </div>
        </>
    );
}
