import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ArrowRight, AlertTriangle, Clock, CheckCircle2, ShieldCheck,
    FileCheck, Truck, Package, Zap, Users, Building2,
} from 'lucide-react';
import { Button } from '@/components/ui/button';

export const metadata: Metadata = {
    title: 'Your Buyer Requires FSMA 204 Compliance | RegEngine',
    description: 'Major retailers are requiring FSMA 204 traceability from suppliers now. Get compliant in minutes, not months. No rip-and-replace required.',
    openGraph: {
        title: 'Your Buyer Requires FSMA 204 Compliance | RegEngine',
        description: 'Major retailers are requiring FSMA 204 traceability from suppliers. Get compliant in minutes with RegEngine.',
        url: 'https://regengine.co/supplier-compliance',
        type: 'website',
    },
};

const COMPLIANCE_STEPS = [
    {
        step: '1',
        title: 'Get Your Portal Link',
        description: 'Your buyer sends you a portal link. Click it to open the submission form. No account creation, no downloads, no IT department.',
        icon: Zap,
        time: '30 seconds',
    },
    {
        step: '2',
        title: 'Submit Shipment Data',
        description: 'Enter your traceability lot code, product details, quantities, and shipping information. The form guides you through exactly what FSMA 204 requires.',
        icon: Package,
        time: '2 minutes',
    },
    {
        step: '3',
        title: 'Data is Verified & Recorded',
        description: 'Your submission is SHA-256 hashed, chain-linked, and stored in FDA-ready format. You receive a verification receipt with your event ID instantly.',
        icon: ShieldCheck,
        time: 'Instant',
    },
];

const RETAILERS_ENFORCING = [
    { name: 'Walmart', detail: 'Supplier compliance clauses active since August 2025' },
    { name: 'Albertsons', detail: 'FSMA 204 requirements in new supplier contracts' },
    { name: 'Kroger', detail: 'Enhanced traceability requirements for fresh categories' },
    { name: 'Costco', detail: 'Supplier quality programs incorporating traceability' },
];

const FAQ = [
    {
        q: 'Do I need to create an account?',
        a: 'No. If your buyer sent you a portal link, you can submit shipment data immediately. No account, no software installation, no IT involvement. Just click the link and fill out the form.',
    },
    {
        q: 'What is FSMA 204?',
        a: 'The FDA Food Safety Modernization Act Section 204 requires enhanced traceability for high-risk foods (fresh produce, seafood, dairy, eggs, deli items). Companies must record Key Data Elements at Critical Tracking Events and provide records to the FDA within 24 hours of request. The compliance deadline is July 20, 2028.',
    },
    {
        q: 'What if I already have a traceability system?',
        a: 'RegEngine works alongside your existing systems. You can submit data via our portal form, upload CSV files, or integrate via our API. We do not require you to replace anything.',
    },
    {
        q: 'What data do I need to provide?',
        a: 'For shipping events: your Traceability Lot Code (TLC), product description, quantity, unit of measure, ship date, origin facility, and destination facility. Optional fields include carrier name, PO number, temperature, and GLN identifiers.',
    },
    {
        q: 'Is my data secure?',
        a: 'Yes. Every submission is SHA-256 hashed and cryptographically chain-linked. Data is stored in tenant-isolated databases with row-level security. Your data is only visible to you and the buyer who generated your portal link.',
    },
    {
        q: 'What does this cost me?',
        a: 'Submitting data through a portal link is free. Your buyer pays for RegEngine. If you want your own RegEngine account to manage traceability across all your buyers, plans start at $425/mo (billed annually) for Founding Design Partners.',
    },
];

export default function SupplierCompliancePage() {
    return (
        <div className="overflow-x-hidden bg-[var(--re-surface-base)]">

            {/* Hero */}
            <section className="max-w-[900px] mx-auto px-4 sm:px-6 pt-14 sm:pt-20 pb-12 sm:pb-16 text-center">
                <div className="inline-flex items-center gap-2 bg-re-warning-muted dark:bg-re-warning text-re-warning dark:text-re-warning border border-amber-200 dark:border-amber-800 px-4 py-2 rounded-xl text-sm font-medium mb-6">
                    <AlertTriangle className="h-4 w-4" />
                    Your buyer requires FSMA 204 compliance
                </div>

                <h1 className="font-serif text-[clamp(1.75rem,4.5vw,2.75rem)] font-bold text-[var(--re-text-primary)] leading-[1.15] tracking-tight mb-6">
                    Get compliant in minutes,{' '}
                    <em className="font-medium text-[var(--re-brand-dark)]">not months.</em>
                </h1>

                <p className="text-lg text-[var(--re-text-muted)] max-w-[600px] mx-auto mb-8 leading-relaxed">
                    Major retailers are already enforcing FSMA 204 traceability requirements on their suppliers — ahead of the July 2028 FDA deadline. Non-compliant suppliers risk losing shelf access.
                </p>

                <div className="flex flex-col sm:flex-row gap-3 justify-center">
                    <Link
                        href="/retailer-readiness"
                        className="inline-flex items-center justify-center gap-2 bg-[var(--re-brand)] text-white px-7 py-3.5 rounded-xl text-[0.925rem] font-semibold transition-all hover:brightness-110 hover:-translate-y-[1px] active:translate-y-0 min-h-[48px]"
                    >
                        Check Your Readiness Score <ArrowRight className="h-4 w-4" />
                    </Link>
                    <Link
                        href="/pricing"
                        className="inline-flex items-center justify-center gap-2 border border-[var(--re-surface-border)] text-[var(--re-text-primary)] px-7 py-3.5 rounded-xl text-[0.925rem] font-medium transition-all hover:border-[var(--re-brand)] hover:text-[var(--re-brand)] min-h-[48px]"
                    >
                        See Pricing
                    </Link>
                </div>
            </section>

            {/* Urgency: Retailers already enforcing */}
            <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-10 sm:py-14 px-4 sm:px-6">
                <div className="max-w-[900px] mx-auto">
                    <div className="text-center mb-8">
                        <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">
                            These retailers are already enforcing compliance
                        </h2>
                        <p className="text-[var(--re-text-muted)]">
                            Suppliers who cannot demonstrate FSMA 204 traceability risk losing contracts.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 max-w-[700px] mx-auto">
                        {RETAILERS_ENFORCING.map((retailer) => (
                            <div
                                key={retailer.name}
                                className="flex items-start gap-3 bg-[var(--re-surface-elevated)] rounded-xl p-4 border border-[var(--re-surface-border)]"
                            >
                                <Building2 className="h-5 w-5 text-[var(--re-brand)] mt-0.5 flex-shrink-0" />
                                <div>
                                    <span className="font-semibold text-[var(--re-text-primary)] text-sm">{retailer.name}</span>
                                    <p className="text-xs text-[var(--re-text-muted)] mt-0.5">{retailer.detail}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* How it works */}
            <section className="max-w-[900px] mx-auto px-4 sm:px-6 py-12 sm:py-16">
                <div className="text-center mb-10">
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-2">
                        How it works for suppliers
                    </h2>
                    <p className="text-[var(--re-text-muted)]">
                        No software to install. No IT project. No learning curve.
                    </p>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                    {COMPLIANCE_STEPS.map((step) => (
                        <div
                            key={step.step}
                            className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-2xl p-6 text-center"
                        >
                            <div className="inline-flex items-center justify-center w-12 h-12 rounded-xl bg-[var(--re-brand-muted)] mb-4">
                                <step.icon className="h-6 w-6 text-[var(--re-brand)]" />
                            </div>
                            <div className="text-xs font-mono text-[var(--re-brand)] mb-2">Step {step.step}</div>
                            <h3 className="text-base font-semibold text-[var(--re-text-primary)] mb-2">
                                {step.title}
                            </h3>
                            <p className="text-sm text-[var(--re-text-muted)] leading-relaxed mb-3">
                                {step.description}
                            </p>
                            <div className="inline-flex items-center gap-1.5 text-xs text-[var(--re-brand)] font-medium">
                                <Clock className="h-3.5 w-3.5" />
                                {step.time}
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* What is FSMA 204 */}
            <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-10 sm:py-14 px-4 sm:px-6">
                <div className="max-w-[700px] mx-auto">
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-4 text-center">
                        What you need to know about FSMA 204
                    </h2>

                    <div className="space-y-4">
                        {[
                            {
                                icon: FileCheck,
                                title: 'Who it applies to',
                                body: 'Any business that manufactures, processes, packs, or holds foods on the Food Traceability List (FTL) — including fresh produce, seafood, dairy, eggs, deli salads, nut butters, and more. This includes domestic and foreign suppliers.',
                            },
                            {
                                icon: Truck,
                                title: 'What you must record',
                                body: 'Key Data Elements (KDEs) at Critical Tracking Events (CTEs): harvesting, cooling, packing, receiving, shipping, and transformation. Required fields include traceability lot codes, product descriptions, quantities, locations, and dates.',
                            },
                            {
                                icon: Clock,
                                title: 'The deadline',
                                body: 'The FDA compliance deadline is July 20, 2028. However, major retailers like Walmart and Albertsons are already requiring compliance from suppliers. Market-driven enforcement is happening now.',
                            },
                            {
                                icon: AlertTriangle,
                                title: 'What happens if you are not compliant',
                                body: 'The FDA can issue warning letters, charge re-inspection fees (~$225/hour), mandate product recalls, suspend facility registration (halting operations), and refuse import admission. More immediately, retailers may drop non-compliant suppliers.',
                            },
                        ].map((item) => (
                            <div
                                key={item.title}
                                className="flex gap-4 bg-[var(--re-surface-elevated)] rounded-xl p-5 border border-[var(--re-surface-border)]"
                            >
                                <item.icon className="h-5 w-5 text-[var(--re-brand)] mt-0.5 flex-shrink-0" />
                                <div>
                                    <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-1">{item.title}</h3>
                                    <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">{item.body}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* For buyers: invite your suppliers */}
            <section className="max-w-[700px] mx-auto px-4 sm:px-6 py-12 sm:py-16 text-center">
                <div className="inline-flex items-center gap-2 bg-[var(--re-brand-muted)] text-[var(--re-brand)] px-3 py-1.5 rounded-lg text-xs font-semibold mb-4">
                    <Users className="h-3.5 w-3.5" />
                    For Buyers
                </div>
                <h2 className="text-2xl font-bold text-[var(--re-text-primary)] mb-3">
                    Need your suppliers to submit traceability data?
                </h2>
                <p className="text-[var(--re-text-muted)] mb-6 leading-relaxed max-w-[500px] mx-auto">
                    Generate portal links from your RegEngine dashboard and share them with suppliers. They submit data directly — no account needed, no training required. Data flows into your tenant automatically.
                </p>
                <div className="flex gap-3 justify-center flex-wrap">
                    <Link href="/onboarding">
                        <Button className="bg-[var(--re-brand)] text-white font-semibold rounded-xl px-6 py-3.5 shadow-[0_4px_16px_rgba(16,185,129,0.25)]">
                            Get Started <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                    <Link href="/pricing">
                        <Button variant="outline" className="rounded-xl px-6 py-3.5">
                            See Pricing
                        </Button>
                    </Link>
                </div>
            </section>

            {/* FAQ */}
            <section className="bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-10 sm:py-14 px-4 sm:px-6">
                <div className="max-w-[700px] mx-auto">
                    <h2 className="text-2xl font-bold text-[var(--re-text-primary)] text-center mb-8">
                        Frequently Asked Questions
                    </h2>
                    <div className="space-y-4">
                        {FAQ.map((item, i) => (
                            <div
                                key={i}
                                className="bg-[var(--re-surface-elevated)] border border-[var(--re-surface-border)] rounded-xl p-5"
                            >
                                <h3 className="text-sm font-semibold text-[var(--re-text-primary)] mb-2">
                                    {item.q}
                                </h3>
                                <p className="text-sm text-[var(--re-text-muted)] leading-relaxed">
                                    {item.a}
                                </p>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Bottom CTA */}
            <section className="py-12 sm:py-16 px-4 sm:px-6 bg-[linear-gradient(135deg,var(--re-brand)_0%,#0ea5e9_100%)]">
                <div className="max-w-[600px] mx-auto text-center">
                    <h2 className="text-2xl font-bold text-white mb-3">
                        Do Not Lose Shelf Access
                    </h2>
                    <p className="text-base text-white/90 mb-8 leading-relaxed">
                        The cost of non-compliance is not a fine — it is losing your buyer. Get your free readiness assessment and see where you stand.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/retailer-readiness">
                            <Button className="bg-white text-[var(--re-brand)] font-semibold px-6 py-3.5">
                                Free Readiness Assessment <ArrowRight className="ml-2 w-4 h-4" />
                            </Button>
                        </Link>
                        <Link href="/fsma-204">
                            <Button variant="outline" className="bg-transparent text-white border border-white/30 px-6 py-3.5">
                                Read the FSMA 204 Guide
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
