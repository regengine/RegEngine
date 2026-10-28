'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Callout } from '@/components/ui/callout';

const sections = [
    {
        id: 'what-regengine-is',
        title: '1. What RegEngine Is',
        content: `RegEngine LLC provides API-first regulatory compliance tools, starting with FSMA 204 food traceability. We help food companies manage Critical Tracking Events (CTEs), Key Data Elements (KDEs), and Traceability Lot Codes (TLCs) to meet FDA requirements.

Features may change without notice, and we may suspend or modify access during staged rollouts, maintenance windows, or broader service updates.

We are a software tool. We are not a law firm, compliance consultancy, or government agency. Our tools help you organize and manage compliance data. They do not constitute legal advice or promise regulatory compliance. You are responsible for your own compliance decisions.`,
    },
    {
        id: 'accounts',
        title: '2. Accounts',
        content: `You must provide accurate information when creating an account. One person or entity per account. You're responsible for keeping your credentials secure. If you suspect unauthorized access, contact us immediately at security@regengine.co.

We may suspend accounts that violate these terms, engage in fraudulent activity, or attempt to access other tenants' data.

We may also suspend or restrict access to the Service if required to do so by law, court order, government request, or if continued operation poses a material legal, regulatory, or security risk to RegEngine LLC or other customers.`,
    },    {
        id: 'your-data',
        title: '3. Your Data',
        content: `As between you and RegEngine, you retain rights in the Customer Data you submit.

We store and process Customer Data to provide, secure, support, and improve RegEngine services as described in the Privacy Policy and applicable agreement. We do not claim ownership of your compliance data, traceability records, or exported reports.

You can export your data through the API, dashboard, or enabled workflow surfaces available to your plan and agreement. If you cancel your subscription or if RegEngine LLC terminates your account, your export and deletion window follows the active customer agreement and workspace operating posture.

If you have statutory or contractual retention obligations, you are responsible for maintaining an off-platform archive or recurring export process that meets those obligations.

You grant us a limited license to store, process, and display Customer Data as necessary to operate, secure, support, and improve the service under these Terms and any applicable agreement.`,
        hasPrivacyLink: true,
    },
    {
        id: 'free-tools',
        title: '4. Free Tools',
        content: `The FTL Coverage Checker, Retailer Readiness Assessment, and other free tools are provided as-is with no warranty. They are informational tools based on our reading of public FDA regulations.

Free tools are provided without warranties of any kind, including merchantability, fitness for a particular purpose, or non-infringement, and RegEngine LLC shall have no liability arising from reliance on free tools.

Free tools do not require an account. We do not store your selections or results unless you explicitly submit your email for follow-up, in which case we use that contact information for that request.

Free tools may be modified, updated, or discontinued at any time.`,
    },    {
        id: 'paid-services',
        title: '5. Paid Services',
        content: `Unless otherwise stated in a signed order form or customer agreement, paid plans are billed monthly or annually as selected. Prices are listed on our pricing page and may change with reasonable advance notice.

You can upgrade at any time (prorated). You can downgrade at the end of your current billing cycle. You can cancel at any time, with no cancellation fees.

Unless your signed order form or customer agreement states otherwise, if you exceed your CTE limit, we charge $0.002 per additional CTE. We will notify you by email before any overage charges are applied.

Refunds are discretionary and evaluated on a case-by-case basis. Except as required by law, refunds are limited to the express terms stated in these Terms. If you're genuinely unhappy with the service within the first 30 days, contact us at support@regengine.co.`,
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
        content: `We work to keep our regulatory data accurate. Our FTL Checker is an informational tool based on the Food Traceability List FDA publishes on its website (see 21 CFR 1.1300). It is not a coverage determination. Our data is cryptographically hashed and independently verifiable.

That said: regulations change. We monitor federal sources and update our data, but there may be delays. We strongly recommend verifying critical compliance decisions against official FDA sources (fda.gov, eCFR.gov).

REGENGINE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, OR THAT OUR REGULATORY DATA IS COMPLETE OR CURRENT AT ALL TIMES.`,
    },    {
        id: 'limitation-of-liability',
        title: '8. Limitation of Liability',
        content: `TO THE MAXIMUM EXTENT PERMITTED BY LAW, REGENGINE LLC SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, CONSEQUENTIAL, SPECIAL, EXEMPLARY, OR PUNITIVE DAMAGES, INCLUDING WITHOUT LIMITATION LOST PROFITS, LOST DATA, BUSINESS INTERRUPTION, REGULATORY FINES, OR PRODUCT RECALL COSTS, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

REGENGINE LLC'S TOTAL AGGREGATE LIABILITY ARISING OUT OF OR RELATING TO THE SERVICE SHALL NOT EXCEED THE AMOUNT PAID BY YOU TO REGENGINE LLC IN THE TWELVE (12) MONTHS PRECEDING THE EVENT GIVING RISE TO THE CLAIM.

This limitation applies regardless of the theory of liability (contract, tort, strict liability, or otherwise).`,
    },
    {
        id: 'security',
        title: '9. Security',
        content: `RegEngine uses PostgreSQL row-level policies and authenticated tenant context designed to restrict access on core PostgreSQL-backed paths, managed-provider encryption at rest, encrypted transport, and evidence manifests where supported workflows create them. See our Security page for details and verification evidence.

You are responsible for keeping your API keys and account credentials secure. If you believe your account has been compromised, notify us immediately.`,
    },
    {
        id: 'acceptable-use',
        title: '10. Acceptable Use',
        content: `Don't use RegEngine to: violate laws or regulations, attempt to access other tenants' data, reverse engineer the platform, send spam through our systems, store data unrelated to regulatory compliance, or impersonate others.

We reserve the right to suspend or terminate accounts that violate these terms.

You agree to defend, indemnify, and hold harmless RegEngine LLC, its officers, employees, and affiliates from any claims, damages, liabilities, and expenses (including reasonable attorneys' fees) arising out of your misuse of the Service, violation of these Terms, or violation of applicable laws or third-party rights.`,
    },    {
        id: 'force-majeure',
        title: '11. Force Majeure',
        content: `RegEngine LLC shall not be liable for failure or delay in performance resulting from events beyond its reasonable control, including acts of God, natural disasters, government actions (including FDA system outages), labor disputes, internet or cloud service outages, pandemics, or failures of third-party infrastructure providers.

In the event of a force majeure lasting more than 30 days, either party may terminate the agreement without penalty.`,
    },
    {
        id: 'termination',
        title: '12. Termination',
        content: `You can close your account at any time. We can terminate your account for material breach of these terms with 30 days' notice (or immediately for security-related violations).

Upon termination: your export and deletion window follows the active customer agreement and workspace operating posture. Any prepaid annual fees will be prorated and refunded for unused months, except where termination results from your uncured material breach.`,
    },
    {
        id: 'changes',
        title: '13. Changes to These Terms',
        content: `We may update these terms. Unless a signed order form or customer agreement controls changes for your workspace, material changes get reasonable advance notice by email and continued use after changes take effect constitutes acceptance.

If you disagree with changes, you can close your account before the updated terms take effect.`,
    },
    {
        id: 'dispute-resolution',
        title: '14. Dispute Resolution & Arbitration',
        content: `Any dispute, claim, or controversy arising out of or relating to these Terms or the use of RegEngine shall be resolved by binding arbitration administered by the American Arbitration Association under its Commercial Arbitration Rules.

YOU AND REGENGINE LLC AGREE TO WAIVE ANY RIGHT TO A JURY TRIAL OR TO PARTICIPATE IN A CLASS ACTION. Arbitration shall be conducted on an individual basis only.

The arbitration shall take place in Los Angeles County, California, unless the parties agree otherwise. The arbitrator's decision shall be final and binding.

Notwithstanding the above, either party may seek injunctive relief in any court of competent jurisdiction for violations of intellectual property rights or confidentiality obligations.`,
    },    {
        id: 'governing-law',
        title: '15. Governing Law',
        content: `These terms are governed by the laws of the State of California, without regard to conflict of law principles, unless a separate signed agreement with RegEngine states otherwise. Data-processing terms are governed by the signed DPA or executed agreement, subject to mandatory applicable privacy law.`,
    },
    {
        id: 'contact',
        title: '16. Contact',
        content: `Questions about these terms? legal@regengine.co

RegEngine LLC
Los Angeles, California`,
    },
];
const PROSE_LINK =
    'text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand';

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
        <div className="re-page min-h-screen">
            {/* ═══ HERO ═══ */}
            <Container width="prose" className="pb-10 pt-14 sm:pt-20">
                <PageHeader
                    size="hero"
                    eyebrow={<span className="font-mono uppercase">Legal</span>}
                    title="Terms of Service"
                    className="mb-0 border-b-0 pb-0"
                />
                <p className="mt-3 font-mono text-[0.8125rem] text-re-text-tertiary">
                    Effective: March 11, 2026 &middot; Last updated: March 11, 2026
                </p>
                <p className="mt-5 text-body text-re-text-secondary">
                    These are the rules for using RegEngine. We&apos;ve written them in plain language because compliance professionals shouldn&apos;t need a lawyer to understand a terms page.
                </p>
            </Container>

            {/* ═══ TL;DR CALLOUT ═══ */}
            <Container width="prose" className="pb-8">
                <Callout tone="info">
                    <h3 className="font-mono text-label uppercase text-re-text-primary">
                        TL;DR
                    </h3>
                    <p className="mt-2 text-ui text-re-text-secondary">
                        You retain rights in Customer Data you submit. We process it to provide, secure, support, and improve the service under the applicable terms. Free tools are informational. Paid-plan and legal terms may be controlled by a signed agreement. We&apos;re a software tool, not legal advice. Don&apos;t try to access other people&apos;s data.
                    </p>
                </Callout>
            </Container>

            {/* ═══ MAIN CONTENT: TOC + SECTIONS ═══ */}
            <Container width="docs" className="pb-20">
                <div className="grid gap-6 lg:grid-cols-[200px_minmax(0,720px)] lg:justify-center lg:gap-10">
                    {/* Sticky TOC - desktop only */}
                    <nav className="hidden lg:block">
                        <div className="sticky top-24">
                            <p className="mb-3 font-mono text-label uppercase text-re-text-muted">
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
                                            className={`border-l-2 py-1 pl-3 text-ui no-underline transition-colors duration-120 motion-reduce:transition-none ${
                                                activeId === s.id
                                                    ? 'border-re-brand font-medium text-re-text-primary'
                                                    : 'border-transparent text-re-text-secondary hover:border-re-border hover:text-re-text-primary'
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
                    <div className="min-w-0">
                        {sections.map((section) => (
                            <div
                                key={section.id}
                                id={section.id}
                                className="scroll-mt-24 border-t border-re-border-subtle py-8"
                            >
                                <h2 className="mb-4 flex items-baseline gap-3 text-heading text-re-text-primary">
                                    <span className="font-mono text-label tabular-nums text-re-text-muted">
                                        {section.title.match(/^\d+/)?.[0]}
                                    </span>
                                    <span>{section.title.replace(/^\d+\.\s*/, '')}</span>
                                </h2>
                                <p className="whitespace-pre-line text-ui leading-[1.75] text-re-text-secondary">
                                    {section.content}
                                </p>
                                {'hasPrivacyLink' in section && section.hasPrivacyLink && (
                                    <p className="mt-3 text-ui text-re-text-secondary">
                                        See our{' '}
                                        <Link href="/privacy" className={PROSE_LINK}>
                                            Privacy Policy
                                        </Link>{' '}
                                        for details on how we collect and process personal data.
                                    </p>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            </Container>
        </div>
    );
}
