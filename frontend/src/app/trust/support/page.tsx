import type { Metadata } from 'next';
import Link from 'next/link';
import {
    ArrowLeft,
    ArrowRight,
    AlertTriangle,
    LifeBuoy,
    Mail,
    ShieldAlert,
    Siren,
    Zap,
} from 'lucide-react';
import { SUPPORT_CHANNELS } from '@/lib/customer-readiness';
import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Section } from '@/components/layout/section';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card } from '@/components/ui/card';

export const metadata: Metadata = {
    title: 'Support & Escalation Model | RegEngine',
    description:
        'Response windows, escalation paths, recall emergency procedures, and support boundaries by plan tier.',
    openGraph: {
        title: 'Support & Escalation Model | RegEngine',
        description: 'Support and escalation model for RegEngine FSMA 204 compliance platform.',
        url: 'https://regengine.co/trust/support',        type: 'website',
    },
};

const ESCALATION_PATH = [
    {
        step: '1',
        title: 'Self-serve documentation',
        description: 'FSMA 204 Guide, API docs, FTL Checker, and compliance dashboard. Most operational questions are answered here without waiting for a human.',
        icon: LifeBuoy,
        availability: 'Always available',
    },
    {
        step: '2',
        title: 'Email support',
        description: 'Standard support channel for configuration questions, export issues, data mapping help, and non-urgent compliance questions.',
        icon: Mail,
        availability: 'All plans',
    },
    {
        step: '3',
        title: 'Priority queue',
        description: 'Faster response for production issues affecting compliance workflows, such as ingestion failures, scoring errors, export failures, or integration breakages.',
        icon: Zap,
        availability: 'Standard and Premium',
    },
    {
        step: '4',
        title: 'Recall-response coordination',
        description: 'Customers with a recall-response addendum receive coordinated support on data exports and evidence packaging during active FDA investigations or live recall events, per the terms of that agreement. RegEngine does not own recall timeline management.',
        icon: Siren,
        availability: 'Per contract',
    },
];

const SUPPORT_BOUNDARIES = [
    {
        title: 'What support covers',
        items: [
            'Platform configuration and data mapping',
            'Export format questions and scheduling',
            'Compliance scoring interpretation',
            'Integration troubleshooting',
            'Ingestion error diagnosis',
            'Account and billing questions',
        ],
    },
    {
        title: 'What support does not cover',
        items: [
            'Regulatory legal advice or audit representation',
            'Upstream ERP/WMS system administration',
            'Custom report development outside your plan',
            'Recall operations or logistics coordination',
            'Food safety consulting or PCQI services',
            'Service-level commitments without enterprise contract',
        ],
    },
];

const BACK_LINK =
    'inline-flex items-center gap-1.5 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none';

export default function SupportPage() {
    return (
        <div className="re-page min-h-screen">
            {/* Header */}
            <Container className="pb-10 pt-14 sm:pb-14 sm:pt-20">
                <PageHeader
                    breadcrumbs={
                        <Link href="/trust" className={BACK_LINK}>
                            <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.75} aria-hidden="true" />
                            Trust Center
                        </Link>
                    }
                    size="hero"
                    eyebrow={<span className="font-mono uppercase">Support &amp; Escalation</span>}
                    title="Who to call, when, and what to expect"
                    description="Support posture depends on plan tier. This page documents the escalation path from self-serve through emergency recall response so your team knows exactly what's available before they need it."
                    className="mb-0 border-b-0 pb-0"
                />
            </Container>

            {/* Escalation path */}
            <Section
                width="marketing"
                title="Escalation path"
                description="Four tiers, from self-serve to recall-response coordination. Plan availability is shown on each tier; specific response and availability commitments are negotiated per contract."
            >
                <Card className="overflow-hidden">
                    {ESCALATION_PATH.map((tier) => {
                        const Icon = tier.icon;
                        return (
                            <div key={tier.step} className="flex gap-4 border-b border-re-border-subtle p-5 last:border-0">
                                <Icon className="mt-0.5 h-5 w-5 shrink-0 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                                <div className="flex-1">
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="text-subheading text-re-text-primary">{tier.title}</div>
                                        <span className="mt-0.5 shrink-0 font-mono text-label uppercase text-re-text-muted">{tier.availability}</span>
                                    </div>
                                    <p className="mt-1.5 text-ui text-re-text-secondary">{tier.description}</p>
                                </div>
                            </div>
                        );
                    })}
                </Card>
            </Section>

            {/* Support channels by plan */}
            <Section
                width="marketing"
                title="Support channels by plan"
                description="We do not publish SLA numbers. Specific response, availability, and escalation commitments are negotiated per contract."
            >
                <Card className="overflow-hidden">
                    {SUPPORT_CHANNELS.map((channel) => (
                        <div key={channel.tier} className="border-b border-re-border-subtle p-5 last:border-0">
                            <div className="mb-2 flex items-center justify-between gap-3">
                                <div className="text-subheading text-re-text-primary">{channel.tier}</div>
                                <div className="font-mono text-[0.8125rem] text-re-text-tertiary">
                                    {channel.responseWindow}
                                </div>
                            </div>
                            <p className="text-ui text-re-text-secondary">{channel.escalation}</p>
                            <p className="mt-2 text-small text-re-text-tertiary">{channel.notes}</p>
                        </div>
                    ))}
                </Card>
            </Section>

            {/* Recall emergency */}
            <Section
                width="marketing"
                title="During a live recall"
                description="This page describes capabilities, not commitments. Customers should not rely on ad hoc vendor intervention to meet statutory retention or a live recall response. Your recall-readiness plan owns that."
            >
                <Callout tone="danger" icon={ShieldAlert}>
                    <h3 className="mb-2 text-subheading text-re-text-primary">What RegEngine does during a recall</h3>
                    <ul className="space-y-2 text-ui text-re-text-secondary">
                        <li>Generates FDA-oriented sortable spreadsheet for the affected product and date range</li>
                        <li>Provides hash-manifest verification artifacts for records in the recall scope</li>
                        <li>Exports available committed CTE/KDE records for affected lots, subject to upstream data quality and the configured workflow</li>
                        <li>Customers with a recall-response addendum receive coordinated export and evidence support per contract</li>
                    </ul>
                </Callout>
                <Callout tone="warning" icon={AlertTriangle} className="mt-3">
                    <h3 className="mb-2 text-subheading text-re-text-primary">What RegEngine does not do during a recall</h3>
                    <ul className="space-y-2 text-ui text-re-text-secondary">
                        <li>RegEngine does not coordinate recall logistics, supplier notifications, or retail removals</li>
                        <li>RegEngine does not provide legal representation or regulatory advice</li>
                        <li>RegEngine does not promise FDA acceptance of any export or report format</li>
                        <li>Public support windows are not a substitute for your recall-readiness plan</li>
                    </ul>
                </Callout>
            </Section>

            {/* Support boundaries */}
            <Section width="marketing" title="Support scope and boundaries">
                <div className="grid gap-4 md:grid-cols-2">
                    {SUPPORT_BOUNDARIES.map((group) => (
                        <Card key={group.title} className="p-5">
                            <h3 className="mb-3 text-subheading text-re-text-primary">{group.title}</h3>
                            <ul className="space-y-2">
                                {group.items.map((item, i) => (
                                    <li key={i} className="flex items-start gap-2 text-ui text-re-text-secondary">
                                        <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-re-text-muted" aria-hidden="true" />
                                        {item}
                                    </li>
                                ))}
                            </ul>
                        </Card>
                    ))}
                </div>
            </Section>

            {/* CTA */}
            <Section width="marketing">
                <div className="text-center">
                    <p className="mx-auto max-w-[68ch] text-ui text-re-text-secondary">
                        Questions about support coverage for your plan? Enterprise escalation terms are defined in your service agreement.
                    </p>
                    <div className="mt-4 flex flex-wrap justify-center gap-3">
                        <Button asChild size="lg">
                            <Link href="/pricing">
                                Compare plans <ArrowRight aria-hidden="true" strokeWidth={1.75} />
                            </Link>
                        </Button>
                        <Button asChild variant="ghost" size="lg">
                            <Link href="/contact">
                                Contact us <ArrowRight aria-hidden="true" strokeWidth={1.75} />
                            </Link>
                        </Button>
                        <Button asChild variant="ghost" size="lg">
                            <Link href="/trust">
                                Trust Center <ArrowRight aria-hidden="true" strokeWidth={1.75} />
                            </Link>
                        </Button>
                    </div>
                </div>
            </Section>
        </div>
    );
}
