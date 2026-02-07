'use client';

import { useState, useEffect } from "react";

const T = {
    bg: "#06090f",
    surface: "rgba(255,255,255,0.02)",
    border: "rgba(255,255,255,0.06)",
    accent: "#10b981",
    accentBg: "rgba(16,185,129,0.08)",
    textPrimary: "#f1f5f9",
    textBody: "#c8d1dc",
    textMuted: "#64748b",
    textDim: "#475569",
    textGhost: "#334155",
    sans: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    mono: "'JetBrains Mono', monospace",
};

const sections = [
    {
        title: "1. What RegEngine Is",
        content: `RegEngine Inc. provides API-first regulatory compliance tools, starting with FSMA 204 food traceability. We help food companies manage Critical Tracking Events (CTEs), Key Data Elements (KDEs), and Traceability Lot Codes (TLCs) to meet FDA requirements.

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
        content: `The FTL Coverage Checker, Walmart Readiness Assessment, and other free tools are provided as-is with no warranty. They are informational tools based on our reading of public FDA regulations.

Free tools are provided without warranties of any kind, including merchantability, fitness for a particular purpose, or non-infringement, and RegEngine Inc. shall have no liability arising from reliance on free tools.

Free tools do not require an account. We do not store your selections or results unless you explicitly submit your email for a gap analysis, in which case we store your email for that purpose only.

Free tools may be modified, updated, or discontinued at any time.`,
    },
    {
        title: "5. Paid Services",
        content: `Paid plans are billed monthly or annually as selected. Prices are listed on our pricing page and may change with 30 days' notice.

You can upgrade at any time (prorated). You can downgrade at the end of your current billing cycle. You can cancel at any time — no cancellation fees.

If you exceed your CTE limit, we charge $0.001 per additional CTE. We will notify you before overage charges apply.

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

We reserve the right to suspend or terminate accounts that violate these terms.`,
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

If you disagree with changes, you can close your account and receive a prorated refund for any prepaid period.`,
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
    const [animateIn, setAnimateIn] = useState(false);

    useEffect(() => {
        setAnimateIn(true);
    }, []);

    return (
        <div style={{ minHeight: "100vh", background: T.bg, fontFamily: T.sans, color: T.textBody }}>
            <link
                href="https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
                rel="stylesheet"
            />

            <div
                style={{
                    position: "fixed", inset: 0, opacity: 0.015, pointerEvents: "none", zIndex: 1,
                    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
                    backgroundSize: "128px 128px",
                }}
            />

            {/* Hero */}
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "80px 24px 48px" }}>
                <div
                    style={{
                        opacity: animateIn ? 1 : 0,
                        transform: animateIn ? "translateY(0)" : "translateY(16px)",
                        transition: "all 0.7s cubic-bezier(0.16, 1, 0.3, 1)",
                    }}
                >
                    <span style={{ fontSize: "11px", fontFamily: T.mono, fontWeight: 500, color: T.textDim, letterSpacing: "0.1em", textTransform: "uppercase" }}>
                        Legal
                    </span>
                    <h1 style={{ fontSize: "36px", fontWeight: 700, color: T.textPrimary, margin: "16px 0 12px", lineHeight: 1.15 }}>
                        Terms of Service
                    </h1>
                    <p style={{ fontSize: "14px", color: T.textDim, fontFamily: T.mono }}>
                        Effective: February 5, 2026 · Last updated: February 6, 2026
                    </p>
                    <p style={{ fontSize: "16px", color: T.textMuted, lineHeight: 1.7, margin: "20px 0 0" }}>
                        These are the rules for using RegEngine. We've written them in plain language because compliance professionals shouldn't need a lawyer to understand a terms page.
                    </p>
                </div>
            </section>

            {/* Quick Summary */}
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "0 24px 32px" }}>
                <div
                    style={{
                        padding: "20px 24px",
                        background: T.accentBg,
                        border: `1px solid rgba(16,185,129,0.15)`,
                        borderRadius: "10px",
                    }}
                >
                    <h3 style={{ fontSize: "14px", fontWeight: 600, color: T.accent, margin: "0 0 10px" }}>
                        TL;DR
                    </h3>
                    <div style={{ fontSize: "14px", color: T.textMuted, lineHeight: 1.7 }}>
                        You own your data. We store it to provide the service. Free tools are free with no strings. Paid plans can be cancelled anytime. We're a software tool, not legal advice. Don't try to access other people's data. California law applies.
                    </div>
                </div>
            </section>

            {/* Sections */}
            <section style={{ position: "relative", zIndex: 2, maxWidth: "720px", margin: "0 auto", padding: "0 24px 80px" }}>
                {sections.map((section, si) => (
                    <div
                        key={si}
                        style={{
                            padding: "28px 0",
                            borderTop: `1px solid ${T.border}`,
                        }}
                    >
                        <h2 style={{ fontSize: "18px", fontWeight: 700, color: T.textPrimary, margin: "0 0 16px" }}>
                            {section.title}
                        </h2>
                        <div style={{ fontSize: "14px", color: T.textMuted, lineHeight: 1.7, whiteSpace: "pre-line" }}>
                            {section.content}
                        </div>
                    </div>
                ))}
            </section>

            <style>{`* { box-sizing: border-box; margin: 0; }`}</style>
        </div>
    );
}
