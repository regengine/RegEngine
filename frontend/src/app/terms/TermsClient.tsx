'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';

const sections = [
    {
        id: 'what-regengine-is',
        title: '1. What RegEngine Is',
        content: `RegEngine Inc. provides API-first regulatory compliance tools, starting with FSMA 204 food traceability. We help food companies manage Critical Tracking Events (CTEs), Key Data Elements (KDEs), and Traceability Lot Codes (TLCs) to meet FDA requirements.

Features may change without notice, and we may suspend or modify access during staged rollouts, maintenance windows, or broader service updates.

We are a software tool. We are not a law firm, compliance consultancy, or government agency. Our tools help you organize and manage compliance data — they do not constitute legal advice or guarantee regulatory compliance. You are responsible for your own compliance decisions.`,
    },
    {
        id: 'accounts',
        title: '2. Accounts',
        content: `You must provide accurate information when creating an account. One person or entity per account. You're responsible for keeping your credentials secure. If you suspect unauthorized access, contact us immediately at security@regengine.co.

We may suspend accounts that violate these terms, engage in fraudulent activity, or attempt to access other tenants' data.

We may also suspend or restrict access to the Service if required to do so by law, court order, government request, or if continued operation poses a material legal, regulatory, or security risk to RegEngine Inc. or other customers.`,
    },    {
        id: 'your-data',
        title: '3. Your Data',
        content: `You own your compliance data. Period.

We store and process your data solely to provide RegEngine services. We do not claim any intellectual property rights over your compliance data, traceability records, or exported reports.

You can export all of your data at any time via the API or dashboard. If you cancel your subscription or if RegEngine Inc. terminates your account, you have 90 days to export your data before it is permanently deleted. This 90-day export window applies regardless of the reason for termination.

If you have statutory or contractual retention obligations, you are responsible for maintaining an off-platform archive or recurring export process that satisfies those obligations.

You grant us a limited license to store, process, and display your data as necessary to operate the service — nothing more.`,
        hasPrivacyLink: true,
    },
    {
        id: 'free-tools',
        title: '4. Free Tools',
        content: `The FTL Coverage Checker, Retailer Readiness Assessment, and other free tools are provided as-is with no warranty. They are informational tools based on our reading of public FDA regulations.

Free tools are provided without warranties of any kind, including merchantability, fitness for a particular purpose, or non-infringement, and RegEngine Inc. shall have no liability arising from reliance on free tools.

Free tools do not require an account. We do not store your selections or results unless you explicitly submit your email for a gap analysis, in which case we store your email for that purpose only.

Free tools may be modified, updated, or discontinued at any time.`,
    },    {
        id: 'paid-services',
        title: '5. Paid Services',
        content: `Paid plans are billed monthly or annually as selected. Prices are listed on our pricing page and may change with 30 days' notice.

You can upgrade at any time (prorated). You can downgrade at the end of your current billing cycle. You can cancel at any time — no cancellation fees.

If you exceed your CTE limit, we charge $0.002 per additional CTE. We will notify you by email before any overage charges are applied.

Refunds are discretionary and evaluated on a case-by-case basis. Except as required by law, RegEngine Inc. does not guarantee refunds beyond the express terms stated in these Terms. If you're genuinely unhappy with the service within the first 30 days, contact us at support@regengine.co.`,
    },
    {
        id: 'api-usage',
        title: '6. API Usage',
        content: `API access is included in all paid plans. You agree to use the API in accordance with our documentation and rate limits.

You may not use the API to: scrape our regulatory database for resale, build a competing service, overwhelm our infrastructure with excessive requests, or attempt to access data belonging to other tenants.

We reserve the right to throttle or suspend API access if usage patterns suggest abuse or threaten service stability.`,
    },
    {
        id: 'accuracy-disclaimers',
        title: '7. Accuracy & Disclaimers',
        content: `We work hard to ensure our regulatory data is accurate. Our FTL Coverage Checker covers FDA Food Traceability List categories per 21 CFR 1.1300 with citations to specific CFR sections. Our data is cryptographically hashed and independently verifiable.

That said: regulations change. We monitor federal sources and update our data, but there may be delays. We strongly recommend verifying critical compliance decisions against official FDA sources (fda.gov, eCFR.gov).

REGENGINE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, OR THAT OUR REGULATORY DATA IS COMPLETE OR CURRENT AT ALL TIMES.`,
    },    {
        id: 'limitation-of-liability',
        title: '8. Limitation of Liability',
        content: `TO THE MAXIMUM EXTENT PERMITTED BY LAW, REGENGINE INC. SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, CONSEQUENTIAL, SPECIAL, EXEMPLARY, OR PUNITIVE DAMAGES, INCLUDING WITHOUT LIMITATION LOST PROFITS, LOST DATA, BUSINESS INTERRUPTION, REGULATORY FINES, OR PRODUCT RECALL COSTS, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

REGENGINE INC.'S TOTAL AGGREGATE LIABILITY ARISING OUT OF OR RELATING TO THE SERVICE SHALL NOT EXCEED THE AMOUNT PAID BY YOU TO REGENGINE INC. IN THE TWELVE (12) MONTHS PRECEDING THE EVENT GIVING RISE TO THE CLAIM.

This limitation applies regardless of the theory of liability (contract, tort, strict liability, or otherwise).`,
    },
    {
        id: 'security',
        title: '9. Security',
        content: `We implement Row-Level Security (RLS), encryption at rest (AES-256), encryption in transit (TLS 1.3), and cryptographic fact hashing (SHA-256). See our Security page for details and verification evidence.

You are responsible for keeping your API keys and account credentials secure. If you believe your account has been compromised, notify us immediately.`,
    },
    {
        id: 'acceptable-use',
        title: '10. Acceptable Use',
        content: `Don't use RegEngine to: violate laws or regulations (ironic, we know), attempt to access other tenants' data, reverse engineer the platform, send spam through our systems, store data unrelated to regulatory compliance, or impersonate others.

We reserve the right to suspend or terminate accounts that violate these terms.

You agree to defend, indemnify, and hold harmless RegEngine Inc., its officers, employees, and affiliates from any claims, damages, liabilities, and expenses (including reasonable attorneys' fees) arising out of your misuse of the Service, violation of these Terms, or violation of applicable laws or third-party rights.`,
    },    {
        id: 'force-majeure',
        title: '11. Force Majeure',
        content: `RegEngine Inc. shall not be liable for failure or delay in performance resulting from events beyond its reasonable control, including acts of God, natural disasters, government actions (including FDA system outages), labor disputes, internet or cloud service outages, pandemics, or failures of third-party infrastructure providers.

In the event of a force majeure lasting more than 30 days, either party may terminate the agreement without penalty.`,
    },
    {
        id: 'termination',
        title: '12. Termination',
        content: `You can close your account at any time. We can terminate your account for material breach of these terms with 30 days' notice (or immediately for security-related violations).

Upon termination: you have 90 days to export your data, after which it is permanently deleted. Any prepaid annual fees will be prorated and refunded for unused months.`,
    },
    {
        id: 'changes',
        title: '13. Changes to These Terms',
        content: `We may update these terms. Material changes get 30 days' email notice. Continued use after changes take effect constitutes acceptance.

If you disagree with changes, you can close your account before the updated terms take effect.`,
    },
    {
        id: 'dispute-resolution',
        title: '14. Dispute Resolution & Arbitration',
        content: `Any dispute, claim, or controversy arising out of or relating to these Terms or the use of RegEngine shall be resolved by binding arbitration administered by the American Arbitration Association under its Commercial Arbitration Rules.

YOU AND REGENGINE INC. AGREE TO WAIVE ANY RIGHT TO A JURY TRIAL OR TO PARTICIPATE IN A CLASS ACTION. Arbitration shall be conducted on an individual basis only.

The arbitration shall take place in Los Angeles County, California, unless the parties agree otherwise. The arbitrator's decision shall be final and binding.

Notwithstanding the above, either party may seek injunctive relief in any court of competent jurisdiction for violations of intellectual property rights or confidentiality obligations.`,
    },    {
        id: 'governing-law',
        title: '15. Governing Law',
        content: `These terms are governed by the laws of the State of California, without regard to conflict of law principles.`,
    },
    {
        id: 'contact',
        title: '16. Contact',
        content: `Questions about these terms? legal@regengine.co

RegEngine Inc.
Los Angeles, California`,
    },
];
export default function TermsClient() {
    const [activeId, setActiveId] = useState('');

    useEffect(() => {
        const observer = new IntersectionObserver(
            (entries) => {
                const visible = entries.filter(e => e.isIntersecting);
                if (visible.length > 0) {
                    setActiveId(visible[0].target.id);
                }
            },
            { rootMargin: '-80px 0px -60% 0px', threshold: 0 }
        );
        sections.forEach(s => {
            const el = document.getElementById(s.id);
            if (el) observer.observe(el);
        });
        return () => observer.disconnect();
    }, []);

    return (
        <div className="re-page">
            {/* ═══ HERO ═══ */}
            <section className="relative z-[2] max-w-[960px] mx-auto pt-14 sm:pt-20 px-4 sm:px-6 pb-10">
                <span className="text-[11px] font-mono font-medium text-[var(--re-text-disabled)] tracking-widest uppercase">
                    Legal
                </span>
                <h1 className="text-4xl font-bold text-[var(--re-text-primary)] mt-4 mb-3 leading-tight">
                    Terms of Service
                </h1>
                <p className="text-sm text-[var(--re-text-disabled)] font-mono">
                    Effective: March 11, 2026 &middot; Last updated: March 11, 2026
                </p>
                <p className="text-base text-[var(--re-text-muted)] leading-relaxed mt-5 max-w-[700px]">
                    These are the rules for using RegEngine. We&apos;ve written them in plain language because compliance professionals shouldn&apos;t need a lawyer to understand a terms page.
                </p>
            </section>
            {/* ═══ TL;DR CALLOUT ═══ */}
            <section className="relative z-[2] max-w-[960px] mx-auto px-4 sm:px-6 pb-8">
                <div className="max-w-[700px]">
                    <div className="rounded-2xl border-2 border-[var(--re-brand)]/20 bg-[var(--re-brand-muted)] p-6">
                        <div className="flex items-center gap-2 mb-2">
                            <div className="w-6 h-6 rounded-md bg-[var(--re-brand)] flex items-center justify-center">
                                <span className="text-white text-xs font-bold">TL</span>
                            </div>
                            <h3 className="text-sm font-bold text-[var(--re-brand)] uppercase tracking-wider">
                                TL;DR
                            </h3>
                        </div>
                        <p className="text-sm text-[var(--re-text-secondary)] leading-relaxed">
                            You own your data. We store it to provide the service. Free tools are free with no strings. Paid plans can be cancelled anytime. We&apos;re a software tool, not legal advice. Don&apos;t try to access other people&apos;s data. California law applies.
                        </p>
                    </div>
                </div>
            </section>
            {/* ═══ MAIN CONTENT: TOC + SECTIONS ═══ */}
            <section className="relative z-[2] max-w-[960px] mx-auto px-4 sm:px-6 pb-20">
                <div className="flex gap-10">
                    {/* Sticky TOC — desktop only */}
                    <nav className="hidden lg:block w-[220px] shrink-0">
                        <div className="sticky top-24">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-[var(--re-text-disabled)] mb-3">
                                On this page
                            </p>
                            <div className="flex flex-col gap-0.5">
                                {sections.map(s => {
                                    const shortTitle = s.title.replace(/^\d+\.\s*/, '');
                                    return (
                                        <a
                                            key={s.id}
                                            href={`#${s.id}`}
                                            onClick={(e) => {
                                                e.preventDefault();
                                                document.getElementById(s.id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                                            }}
                                            className={`text-[12px] py-1 pl-3 border-l-2 transition-all ${
                                                activeId === s.id
                                                    ? 'border-[var(--re-brand)] text-[var(--re-brand)] font-semibold'
                                                    : 'border-transparent text-[var(--re-text-muted)] hover:text-[var(--re-text-secondary)] hover:border-[var(--re-surface-border)]'
                                            }`}
                                        >
                                            {shortTitle}
                                        </a>
                                    );
                                })}
                            </div>
                        </div>
                    </nav>
                    {/* Content */}
                    <div className="flex-grow min-w-0 max-w-[700px]">
                        {sections.map((section) => (
                            <div
                                key={section.id}
                                id={section.id}
                                className="scroll-mt-24 py-8 border-t border-[var(--re-surface-border)]"
                            >
                                <h2 className="text-lg font-bold text-[var(--re-text-primary)] mb-4 flex items-center gap-3">
                                    <span className="inline-flex items-center justify-center w-7 h-7 rounded-lg bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] text-xs font-bold text-[var(--re-text-muted)]">
                                        {section.title.match(/^\d+/)?.[0]}
                                    </span>
                                    <span>{section.title.replace(/^\d+\.\s*/, '')}</span>
                                </h2>
                                <p className="text-sm text-[var(--re-text-muted)] leading-[1.75] whitespace-pre-line">
                                    {section.content}
                                </p>
                                {'hasPrivacyLink' in section && section.hasPrivacyLink && (
                                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mt-3">
                                        See our{' '}
                                        <Link href="/privacy" className="text-[var(--re-brand)] underline hover:opacity-90">
                                            Privacy Policy
                                        </Link>{' '}
                                        for details on how we collect and process personal data.
                                    </p>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            </section>
        </div>
    );
}