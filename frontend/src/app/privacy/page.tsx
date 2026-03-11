import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
    title: 'Privacy Policy | RegEngine',
    description: 'Plain language privacy policy. What RegEngine collects, why, and what we do with your compliance data.',
    openGraph: {
        title: 'Privacy Policy | RegEngine',
        description: 'Plain language privacy policy for FSMA 204 compliance.',
        url: 'https://www.regengine.co/privacy',
        type: 'website',
    },
};

const sections = [
    {
        title: "What We Collect",
        content: [
            {
                subtitle: "Account Information",
                text: "When you create an account, we collect your name, email address, company name, and billing information. We need this to provide you with our services and process payments.",
            },
            {
                subtitle: "Compliance Data",
                text: "When you use RegEngine to manage FSMA 204 compliance, we process and store the traceability data you submit — including Critical Tracking Events (CTEs), Key Data Elements (KDEs), and Traceability Lot Codes (TLCs). This data belongs to you. We store it to provide the service.",
            },
            {
                subtitle: "Usage Data",
                text: "We collect basic analytics: pages visited, features used, API calls made. We use this to improve the product. We do not sell this data to anyone.",
            },
            {
                subtitle: "FTL Checker (Free Tool)",
                text: "The FTL Coverage Checker does not require an account and does not store your selections. If you submit your email for a gap analysis, we store that email solely to send you the analysis.",
            },
        ],
    },
    {
        title: "How We Use Your Data",
        content: [
            { text: "Providing and maintaining RegEngine services" },
            { text: "Processing your compliance data as directed by you" },
            { text: "Generating FDA-ready exports and reports you request" },
            { text: "Sending transactional emails (account, billing, compliance alerts)" },
            { text: "Improving our platform based on aggregate usage patterns" },
            { text: "Responding to your support requests" },
        ],
    },
    {
        title: "What We Don't Do",
        content: [
            { text: "We do not sell your personal data or compliance data to third parties." },
            { text: "We do not use your compliance data to train machine learning models." },
            { text: "We do not share your data with other RegEngine tenants. Row-Level Security enforces tenant isolation at the database level." },
            { text: "We do not serve targeted ads." },
            { text: "We do not share your data with data brokers." },
        ],
    },
    {
        title: "Data Storage & Security",
        content: [
            {
                subtitle: "Where",
                text: "Your data is stored in US-based cloud infrastructure with encryption at rest (AES-256) and in transit (TLS 1.3).",
            },
            {
                subtitle: "Isolation",
                text: "Each tenant's data is isolated via PostgreSQL Row-Level Security policies. This is enforced at the database layer, not the application layer. See our Security page for verification details.",
            },
            {
                subtitle: "Integrity",
                text: "Regulatory facts are cryptographically hashed with SHA-256. You can independently verify data integrity using our open verification tools.",
            },
            {
                subtitle: "Retention",
                text: "We retain your compliance data for the duration of your subscription plus 90 days. After cancellation, you can request a full data export. After the retention period, data is permanently deleted.",
            },
        ],
    },
    {
        title: "Your Rights",
        content: [
            {
                subtitle: "Access & Export",
                text: "You can export all of your compliance data at any time via the API or dashboard. We support FDA-compliant CSV formats.",
            },
            {
                subtitle: "Deletion",
                text: "You can request deletion of your account and all associated data by contacting privacy@regengine.co. We will complete deletion within 30 days.",
            },
            {
                subtitle: "Correction",
                text: "You can update your account information at any time through the dashboard.",
            },
            {
                subtitle: "California Residents (CCPA)",
                text: "California residents have additional rights under the CCPA, including the right to know what personal information we collect and the right to opt out of data sales. We do not sell personal information.",
            },
        ],
    },
    {
        title: "Cookies",
        content: [
            {
                text: "We use essential cookies for authentication and session management. We use basic analytics cookies to understand product usage. We do not use third-party advertising cookies. You can disable non-essential cookies in your browser settings.",
            },
        ],
    },
    {
        title: "Third-Party Services",
        content: [
            {
                text: "We use a limited number of third-party services to operate RegEngine: cloud hosting (data storage and compute), payment processing (Stripe — they have their own privacy policy), and email delivery (transactional emails only). Each service provider is bound by data processing agreements.",
            },
        ],
    },
    {
        title: "Beta Service Notice",
        content: [
            {
                text: "RegEngine is currently in beta. Features and workflows may change as we improve the platform, and access may be modified during beta operations. This Privacy Policy applies during beta and after general availability.",
            },
        ],
    },
    {
        title: "Changes to This Policy",
        content: [
            {
                text: "We'll notify you of material changes via email at least 30 days before they take effect. Non-material changes (clarifications, formatting) may be made without notice.",
            },
        ],
    },
    {
        title: "Contact",
        content: [
            {
                text: "Questions about this policy? privacy@regengine.co — you'll hear from the founder directly, not a legal department.",
            },
        ],
    },
];

export default function PrivacyPage() {
    return (
        <div className="re-page">
            {/* Hero */}
            <section className="relative z-[2] max-w-[720px] mx-auto pt-20 px-6 pb-12">
                <span className="text-[11px] font-mono font-medium text-re-text-disabled tracking-widest uppercase">
                    Legal
                </span>
                <h1 className="text-4xl font-bold text-re-text-primary mt-4 mb-3 leading-tight">
                    Privacy Policy
                </h1>
                <p className="text-sm text-re-text-disabled font-mono">
                    Effective: March 11, 2026 · Last updated: March 11, 2026
                </p>
                <p className="text-base text-re-text-muted leading-relaxed mt-5">
                    Plain language. No legalese walls. Here&apos;s what we collect, why, and what we do with it.
                </p>
                <p className="text-sm text-re-text-muted leading-relaxed mt-4">
                    Related documents:{' '}
                    <Link href="/terms" className="text-re-brand underline hover:opacity-90">Terms of Service</Link>
                    {' '}and{' '}
                    <Link href="/security" className="text-re-brand underline hover:opacity-90">Security</Link>.
                </p>
            </section>

            {/* Sections */}
            <section className="relative z-[2] max-w-[720px] mx-auto px-6 pb-20">
                {sections.map((section, si) => (
                    <div
                        key={si}
                        className={si > 0 ? "pt-8 border-t border-white/[0.06]" : "pt-8"}
                    >
                        <h2 className="text-xl font-bold text-re-text-primary mb-5">
                            {section.title}
                        </h2>
                        <div className="flex flex-col gap-4">
                            {section.content.map((item, i) => (
                                <div key={i}>
                                    {'subtitle' in item && item.subtitle && (
                                        <h3 className="text-sm font-semibold text-re-brand mb-1">
                                            {item.subtitle}
                                        </h3>
                                    )}
                                    {item.text && (
                                        <p className="text-sm text-re-text-muted leading-relaxed">
                                            {item.text}
                                        </p>
                                    )}
                                </div>
                            ))}
                        </div>
                    </div>
                ))}
            </section>
        </div>
    );
}
