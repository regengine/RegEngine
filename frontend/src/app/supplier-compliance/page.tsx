import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ArrowRight, AlertTriangle, Clock, ShieldCheck,
    FileCheck, Truck, Package, Zap, Users, Building2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Container } from '@/components/layout/container';

export const metadata: Metadata = {
    title: 'Your Buyer Asked About FSMA 204 Traceability | RegEngine',
    description: 'Major retailers are increasingly asking suppliers for FSMA 204 traceability data. Start submitting in minutes; full FSMA 204 program coverage takes longer. No rip-and-replace required.',
    openGraph: {
        title: 'Your Buyer Asked About FSMA 204 Traceability | RegEngine',
        description: 'Major retailers are asking suppliers for traceability data. Start submitting in minutes with RegEngine.',
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
        description: 'Your submission is SHA-256 hashed, chain-linked, and stored in an FDA-oriented sortable structure. You receive a verification receipt with your event ID instantly.',
        icon: ShieldCheck,
        time: 'Instant',
    },
];

// Generic, hedged framing - we don't claim insider knowledge of specific
// retailer contracting terms. If a buyer mandate is publicly cited, link
// to the source rather than asserting it here.
const RETAILERS_ENFORCING = [
    { name: 'Major retailers', detail: 'Multiple top-10 grocers have publicly signaled supplier traceability expectations ahead of the 2028 deadline. Specific requirements vary by buyer, so confirm directly with your buyer.' },
];

const FAQ = [
    {
        q: 'Do I need to create an account?',
        a: 'No. If your buyer sent you a portal link, you can submit shipment data immediately. No account, no software installation, no IT involvement. Just click the link and fill out the form.',
    },
    {
        q: 'What is FSMA 204?',
        a: 'The FDA Food Safety Modernization Act Section 204 requires enhanced traceability for foods on the Food Traceability List. Covered companies must record Key Data Elements at Critical Tracking Events and may need to provide records to the FDA within 24 hours of request. Current public FDA posture points to July 20, 2028 as the earliest enforcement date under congressional direction.',
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
        a: 'Submitting data through a portal link is free. Your buyer pays for RegEngine. If you want your own RegEngine account to manage traceability across all your buyers, plans start at $425/mo (billed annually) at the Founding rate.',
    },
];

export default function SupplierCompliancePage() {
    return (
        <div className="bg-re-surface-base">

            {/* Hero */}
            <Container as="section" width="tool" className="pb-12 pt-14 text-center sm:pb-16 sm:pt-20">
                <Badge tone="warning" className="mb-6 h-auto whitespace-normal py-1 text-left">
                    <AlertTriangle className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                    Did your buyer ask about FSMA 204?
                </Badge>

                <h1 className="mx-auto mb-6 max-w-[22ch] font-display text-display text-re-text-primary">
                    Start submitting traceability data{' '}
                    <em className="font-medium">in minutes.</em>
                </h1>

                <p className="mx-auto mb-8 max-w-[60ch] text-body leading-relaxed text-re-text-secondary">
                    Major retailers are signaling traceability expectations ahead of the July 2028 FDA date. Non-compliant suppliers risk losing shelf access.
                </p>

                <div className="flex flex-col justify-center gap-3 sm:flex-row">
                    <Button asChild size="lg">
                        <Link href="/retailer-readiness" className="no-underline">
                            Check Your Readiness Score <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        </Link>
                    </Button>
                    <Button asChild variant="secondary" size="lg">
                        <Link href="/pricing" className="no-underline">
                            See Pricing
                        </Link>
                    </Button>
                </div>
            </Container>

            {/* Urgency: Retailers already enforcing */}
            <section className="border-t border-re-border-subtle">
                <Container width="tool" className="py-10 sm:py-14">
                    <div className="mb-8 text-center">
                        <h2 className="mb-2 font-display text-heading-lg text-re-text-primary">
                            Retailers are signaling traceability expectations
                        </h2>
                        <p className="text-body text-re-text-secondary">
                            Suppliers who cannot demonstrate FSMA 204 traceability risk losing contracts.
                        </p>
                    </div>

                    <div className="mx-auto grid max-w-[700px] grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-4">
                        {RETAILERS_ENFORCING.map((retailer) => (
                            <Card key={retailer.name} padding="compact" className="flex items-start gap-3">
                                <Building2 className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <div className="min-w-0">
                                    <span className="text-ui font-medium text-re-text-primary">{retailer.name}</span>
                                    <p className="mt-0.5 text-small leading-relaxed text-re-text-tertiary">{retailer.detail}</p>
                                </div>
                            </Card>
                        ))}
                    </div>
                </Container>
            </section>

            {/* How it works */}
            <section className="border-t border-re-border-subtle">
                <Container width="tool" className="py-12 sm:py-16">
                    <div className="mb-10 text-center">
                        <h2 className="mb-2 font-display text-heading-lg text-re-text-primary">
                            How it works for suppliers
                        </h2>
                        <p className="text-body text-re-text-secondary">
                            No software to install. No IT project. No learning curve.
                        </p>
                    </div>

                    <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
                        {COMPLIANCE_STEPS.map((step) => (
                            <Card key={step.step} padding="spacious" className="text-center">
                                <step.icon className="mx-auto mb-4 h-5 w-5 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <p className="mb-2 font-mono text-label uppercase text-re-text-muted">Step {step.step}</p>
                                <h3 className="mb-2 text-subheading text-re-text-primary">
                                    {step.title}
                                </h3>
                                <p className="mb-3 text-ui leading-relaxed text-re-text-secondary">
                                    {step.description}
                                </p>
                                <p className="inline-flex items-center gap-1.5 text-small text-re-text-tertiary">
                                    <Clock className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                    {step.time}
                                </p>
                            </Card>
                        ))}
                    </div>
                </Container>
            </section>

            {/* What is FSMA 204 */}
            <section className="border-t border-re-border-subtle">
                <Container width="prose" className="py-10 sm:py-14">
                    <h2 className="mb-4 text-center font-display text-heading-lg text-re-text-primary">
                        What you need to know about FSMA 204
                    </h2>

                    <div className="space-y-4">
                        {[
                            {
                                icon: FileCheck,
                                title: 'Who it applies to',
                                body: 'Any business that manufactures, processes, packs, or holds foods on the Food Traceability List (FTL), including fresh produce, seafood, dairy, eggs, deli salads, nut butters, and more. This includes domestic and foreign suppliers.',
                            },
                            {
                                icon: Truck,
                                title: 'What you must record',
                                body: 'Key Data Elements (KDEs) at Critical Tracking Events (CTEs): harvesting, cooling, packing, first land-based receiving, shipping, receiving, and transformation. Required fields include traceability lot codes, product descriptions, quantities, locations, and dates.',
                            },
                            {
                                icon: Clock,
                                title: 'The deadline',
                                body: 'Current public FDA posture points to July 20, 2028 as the earliest enforcement date under congressional direction. Many major retailers are signaling traceability expectations to suppliers ahead of that date. Specific retailer requirements vary by buyer and should be confirmed directly with your buyer.',
                            },
                            {
                                icon: AlertTriangle,
                                title: 'What happens if you are not compliant',
                                body: 'The FDA can issue warning letters, charge re-inspection fees (~$225/hour), mandate product recalls, suspend facility registration (halting operations), and refuse import admission. More immediately, retailers may drop non-compliant suppliers.',
                            },
                        ].map((item) => (
                            <Card key={item.title} padding="default" className="flex gap-4 p-5">
                                <item.icon className="mt-0.5 h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <div className="min-w-0">
                                    <h3 className="mb-1 text-subheading text-re-text-primary">{item.title}</h3>
                                    <p className="text-ui leading-relaxed text-re-text-secondary">{item.body}</p>
                                </div>
                            </Card>
                        ))}
                    </div>
                </Container>
            </section>

            {/* For buyers: invite your suppliers */}
            <section className="border-t border-re-border-subtle">
                <Container width="prose" className="py-12 text-center sm:py-16">
                    <Badge tone="brand" className="mb-4">
                        <Users className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                        For Buyers
                    </Badge>
                    <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">
                        Need your suppliers to submit traceability data?
                    </h2>
                    <p className="mx-auto mb-6 max-w-[56ch] text-body leading-relaxed text-re-text-secondary">
                        Generate portal links from your RegEngine dashboard and share them with suppliers. They submit data directly, with no account needed and no training required. Data flows into your workspace automatically.
                    </p>
                    <div className="flex flex-wrap justify-center gap-3">
                        <Button asChild size="lg">
                            <Link href="/onboarding" className="no-underline">
                                Get Started <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/pricing" className="no-underline">
                                See Pricing
                            </Link>
                        </Button>
                    </div>
                </Container>
            </section>

            {/* FAQ */}
            <section className="border-t border-re-border-subtle">
                <Container width="prose" className="py-10 sm:py-14">
                    <h2 className="mb-8 text-center font-display text-heading-lg text-re-text-primary">
                        Frequently Asked Questions
                    </h2>
                    <div className="space-y-4">
                        {FAQ.map((item, i) => (
                            <Card key={i} padding="default" className="p-5">
                                <h3 className="mb-2 text-subheading text-re-text-primary">
                                    {item.q}
                                </h3>
                                <p className="text-ui leading-relaxed text-re-text-secondary">
                                    {item.a}
                                </p>
                            </Card>
                        ))}
                    </div>
                </Container>
            </section>

            {/* Bottom CTA */}
            <section className="border-t border-re-border-subtle bg-re-surface-inset">
                <Container width="prose" className="py-12 text-center sm:py-16">
                    <h2 className="mb-3 font-display text-heading-lg text-re-text-primary">
                        Buyers are starting to ask
                    </h2>
                    <p className="mx-auto mb-8 max-w-[56ch] text-body leading-relaxed text-re-text-secondary">
                        Be ready when they do. Get a free readiness self-check and see where your traceability records stand.
                    </p>
                    <div className="flex flex-wrap justify-center gap-3">
                        <Button asChild size="lg">
                            <Link href="/retailer-readiness" className="no-underline">
                                Free Readiness Assessment <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/fsma-204" className="no-underline">
                                Read the FSMA 204 Guide
                            </Link>
                        </Button>
                    </div>
                </Container>
            </section>
        </div>
    );
}
