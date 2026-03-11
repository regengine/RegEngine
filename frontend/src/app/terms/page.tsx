import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
    title: 'Terms of Service | RegEngine',
    description: 'RegEngine terms of service. Plain language rules for using FSMA 204 compliance tools.',
    openGraph: {
        title: 'Terms of Service | RegEngine',
        description: 'Terms of service for RegEngine FSMA 204 compliance platform.',
        url: 'https://www.regengine.co/terms',
        type: 'website',
    },
};

const sections = [
    {
        title: "1. What RegEngine Is",
        content: `RegEngine Inc. provides API-first regulatory compliance tools, starting with FSMA 204 food traceability. We help food companies manage Critical Tracking Events (CTEs), Key Data Elements (KDEs), and Traceability Lot Codes (TLCs) to meet FDA requirements.

RegEngine is currently in beta. Features may change without notice, and we may suspend or modify access during the beta period.

We are a software tool. We are not a law firm, compliance consultancy, or government agency. Our tools help you organize and manage compliance data — they do not constitute legal advice or guarantee regulatory compliance. You are responsible for your own compliance decisions.`,
    },
    {
        title: "2. Accounts",
        content: `You must provide accurate information when creating an account. One person or entity per account. You're responsible for keeping your credentials secure. If you suspect unauthorized access, contact us immediately at security@regengine.co.

We may suspend accounts that violate these terms, engage in fraudulent activity, or attempt to access other tenants' data.

We may also suspend or restrict access to the Service if required to do so by law, court order, government request, or if continued operation poses a material legal, regulatory, or security risk to RegEngine Inc. or other customers.`,
    },
    {
        title: "3. Your Data",
        content: `You own your compliance data. Period.

We store and process your data solely to provide RegEngine services. We do not claim any intellectual property rights over your compliance data, traceability records, or exported reports.

You can export all of your data at any time via the API or dashboard. If you cancel your subscription or if RegEngine Inc. terminates your account, you have 90 days to export your data before it is permanently deleted. This 90-day export window applies regardless of the reason for termination.

You grant us a limited license to store, process, and display your data as necessary to operate the service — nothing more.`,
    },
    {
        title: "4. Free Tools",
        content: `The FTL Coverage Checker, Retailer Readiness Assessment, and other free tools are provided as-is with no warranty. They are informational tools based on our reading of public FDA regulations.

Free tools are provided without warranties of any kind, including merchantability, fitness for a particular purpose, or non-infringement, and RegEngine Inc. shall have no liability arising from reliance on free tools.

Free tools do not require an account. We do not store your selections or results unless you explicitly submit your email for a gap analysis, in which case we store your email for that purpose only.

Free tools may be modified, updated, or discontinued at any time.`,
    },
    {
        title: "5. Paid Services",
        content: `Paid plans are billed monthly or annually as selected. Prices are listed on our pricing page and may change with 30 days' notice.

You can upgrade at any time (prorated). You can downgrade at the end of your current billing cycle. You can cancel at any time — no cancellation fees.

If you exceed your CTE limit, we charge $0.001 per additional CTE. We will notify you by email before any overage charges are applied.

Refunds are discretionary and evaluated on a case-by-case basis. Except as required by law, RegEngine Inc. does not guarantee refunds beyond the express terms stated in these Terms. If you're genuinely unhappy with the service within the first 30 days, contact us at support@regengine.co.`,
    },
    {
        title: "6. API Usage",
        content: `API access is included in all paid plans. You agree to use the API in accordance with our documentation and rate limits.

You may not use the API to: scrape our regulatory database for resale, build a competing service, overwhelm our infrastructure with excessive requests, or attempt to access data belonging to other tenants.

We reserve the right to throttle or suspend API access if usage patterns suggest abuse or threaten service stability.`,
    },
    {
        title: "7. Accuracy & Disclaimers",
        content: `We work hard to ensure our regulatory data is accurate. Our FTL Coverage Checker covers all 23 FDA Food Traceability List categories with citations to specific CFR sections. Our data is cryptographically hashed and independently verifiable.

That said: regulations change. We monitor federal sources and update our data, but there may be delays. We strongly recommend verifying critical compliance decisions against official FDA sources (fda.gov, eCFR.gov).

REGENGINE IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED. WE DO NOT WARRANT THAT THE SERVICE WILL BE UNINTERRUPTED, ERROR-FREE, OR THAT OUR REGULATORY DATA IS COMPLETE OR CURRENT AT ALL TIMES.`,
    },
    {
        title: "8. Limitation of Liability",
        content: `TO THE MAXIMUM EXTENT PERMITTED BY LAW, REGENGINE INC. SHALL NOT BE LIABLE FOR ANY INDIRECT, INCIDENTAL, CONSEQUENTIAL, SPECIAL, EXEMPLARY, OR PUNITIVE DAMAGES, INCLUDING WITHOUT LIMITATION LOST PROFITS, LOST DATA, BUSINESS INTERRUPTION, REGULATORY FINES, OR PRODUCT RECALL COSTS, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGES.

REGENGINE INC.'S TOTAL AGGREGATE LIABILITY ARISING OUT OF OR RELATING TO THE SERVICE SHALL NOT EXCEED THE AMOUNT PAID BY YOU TO REGENGINE INC. IN THE TWELVE (12) MONTHS PRECEDING THE EVENT GIVING RISE TO THE CLAIM.

This limitation applies regardless of the theory of liability (contract, tort, strict liability, or otherwise).`,
    },
    {
        title: "9. Security",
        content: `We implement Row-Level Security (RLS), encryption at rest (AES-256), encryption in transit (TLS 1.3), and cryptographic fact hashing (SHA-256). See our Security page for details and verification evidence.

You are responsible for keeping your API keys and account credentials secure. If you believe your account has been compromised, notify us immediately.`,
    },
    {
        title: "10. Acceptable Use",
        content: `Don't use RegEngine to: violate laws or regulations (ironic, we know), attempt to access other tenants' data, reverse engineer the platform, send spam through our systems, store data unrelated to regulatory compliance, or impersonate others.

We reserve the right to suspend or terminate accounts that violate these terms.

You agree to defend, indemnify, and hold harmless RegEngine Inc., its officers, employees, and affiliates from any claims, damages, liabilities, and expenses (including reasonable attorneys' fees) arising out of your misuse of the Service, violation of these Terms, or violation of applicable laws or third-party rights.`,
    },
    {
        title: "11. Force Majeure",
        content: `RegEngine Inc. shall not be liable for failure or delay in performance resulting from events beyond its reasonable control, including acts of God, natural disasters, government actions (including FDA system outages), labor disputes, internet or cloud service outages, pandemics, or failures of third-party infrastructure providers.

In the event of a force majeure lasting more than 30 days, either party may terminate the agreement without penalty.`,
    },
    {
        title: "12. Termination",
        content: `You can close your account at any time. We can terminate your account for material breach of these terms with 30 days' notice (or immediately for security-related violations).

Upon termination: you have 90 days to export your data, after which it is permanently deleted. Any prepaid annual fees will be prorated and refunded for unused months.`,
    },
    {
        title: "13. Changes to These Terms",
        content: `We may update these terms. Material changes get 30 days' email notice. Continued use after changes take effect constitutes acceptance.

If you disagree with changes, you can close your account before the updated terms take effect.`,
    },
    {
        title: "14. Dispute Resolution & Arbitration",
        content: `Any dispute, claim, or controversy arising out of or relating to these Terms or the use of RegEngine shall be resolved by binding arbitration administered by the American Arbitration Association under its Commercial Arbitration Rules.

YOU AND REGENGINE INC. AGREE TO WAIVE ANY RIGHT TO A JURY TRIAL OR TO PARTICIPATE IN A CLASS ACTION. Arbitration shall be conducted on an individual basis only.

The arbitration shall take place in Los Angeles County, California, unless the parties agree otherwise. The arbitrator's decision shall be final and binding.

Notwithstanding the above, either party may seek injunctive relief in any court of competent jurisdiction for violations of intellectual property rights or confidentiality obligations.`,
    },
    {
        title: "15. Governing Law",
        content: `These terms are governed by the laws of the State of California, without regard to conflict of law principles.`,
    },
    {
        title: "16. Contact",
        content: `Questions about these terms? legal@regengine.co

RegEngine Inc.
Los Angeles, California`,
    },
];

export default function TermsPage() {
    return (
        <div className="re-page">
            {/* Hero */}
            <section className="relative z-[2] max-w-[720px] mx-auto pt-20 px-6 pb-12">
                <span className="text-[11px] font-mono font-medium text-re-text-disabled tracking-widest uppercase">
                    Legal
                </span>
                <h1 className="text-4xl font-bold text-re-text-primary mt-4 mb-3 leading-tight">
                    Terms of Service
                </h1>
                <p className="text-sm text-re-text-disabled font-mono">
                    Effective: March 11, 2026 · Last updated: March 11, 2026
                </p>
                <p className="text-base text-re-text-muted leading-relaxed mt-5">
                    These are the rules for using RegEngine. We&apos;ve written them in plain language because compliance professionals shouldn&apos;t need a lawyer to understand a terms page.
                </p>
            </section>

            {/* TL;DR */}
            <section className="relative z-[2] max-w-[720px] mx-auto px-6 pb-8">
                <div className="p-5 bg-re-brand/[0.08] border border-re-brand/[0.15] rounded-xl">
                    <h3 className="text-sm font-semibold text-re-brand mb-2">
                        TL;DR
                    </h3>
                    <p className="text-sm text-re-text-muted leading-relaxed">
                        You own your data. We store it to provide the service. Free tools are free with no strings. Paid plans can be cancelled anytime. We&apos;re a software tool, not legal advice. Don&apos;t try to access other people&apos;s data. California law applies.
                    </p>
                </div>
            </section>

            {/* Sections */}
            <section className="relative z-[2] max-w-[720px] mx-auto px-6 pb-20">
                {sections.map((section, si) => (
                    <div
                        key={si}
                        className="py-7 border-t border-white/[0.06]"
                    >
                        <h2 className="text-lg font-bold text-re-text-primary mb-4">
                            {section.title}
                        </h2>
                        <p className="text-sm text-re-text-muted leading-relaxed whitespace-pre-line">
                            {section.content}
                        </p>
                        {section.title === "3. Your Data" && (
                            <p className="text-sm text-re-text-muted leading-relaxed mt-3">
                                See our{' '}
                                <Link href="/privacy" className="text-re-brand underline hover:opacity-90">
                                    Privacy Policy
                                </Link>{' '}
                                for details on how we collect and process personal data.
                            </p>
                        )}
                    </div>
                ))}
            </section>
        </div>
    );
}
