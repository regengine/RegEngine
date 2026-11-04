'use client';

import { useEffect } from 'react';
import Link from 'next/link';
import {
    Check, Zap, Rocket, Crown, ArrowRight, HelpCircle, Lock, ShieldCheck, KeyRound,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Container } from '@/components/layout/container';
import { PricingCheckoutButton } from '@/components/billing/PricingCheckoutButton';
import { analytics } from '@/lib/analytics';
import { cn } from '@/lib/utils';

const ICON_MAP: Record<string, LucideIcon> = {
    zap: Zap,
    rocket: Rocket,
    crown: Crown,
};

interface PricingTier {
    id: string;
    name: string;
    icon: string;
    description: string;
    gaMonthly: number;
    gaAnnual: number;
    partnerMonthly: number;
    partnerAnnual: number;
    highlighted: boolean;
    cta: string;
    features: string[];
    beta?: boolean;
}

export interface PricingComparisonRow {
    feature: string;
    regengine: string;
    foodlogiq: string;
    repositrak: string;
    tracegains: string;
}

export interface PricingFaqItem {
    q: string;
    a: string;
}

export function PricingPageClient({
    pricingTiers,
    comparisonRows,
    faq,
}: {
    pricingTiers: PricingTier[];
    comparisonRows: PricingComparisonRow[];
    faq: PricingFaqItem[];
}) {
    useEffect(() => {
        analytics.pricingPageView();
    }, []);

    return (
        <div className="re-page bg-re-surface-base text-re-text-secondary">
            <Container as="section" width="marketing" className="pb-7 pt-10 text-center sm:pb-10 sm:pt-14">
                <h1 className="mx-auto max-w-[34ch] font-display text-display text-re-text-primary">
                    FSMA 204 traceability readiness,<br />
                    priced for facility teams.
                </h1>
                <p className="mx-auto mb-3 mt-4 max-w-[68ch] text-body text-re-text-secondary">
                    Three indicative plans sized by facility count. Founding rate discounts are documented in the executed order form or design-partner agreement.
                </p>
                <p className="mx-auto max-w-[68ch] text-body font-medium text-re-text-primary">
                    Pricing shown is indicative. Executed agreement controls final plan, billing period, and checkout availability.
                </p>
                <p className="mt-2 text-small text-re-text-tertiary">
                    Annual billing saves ~15%. Monthly billing also available.
                </p>
            </Container>

            <Container as="section" width="marketing" className="pb-10 sm:pb-16">
                <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-5">
                    {pricingTiers.map((tier) => {
                        const Icon = ICON_MAP[tier.icon] ?? Zap;
                        return (
                            <Card
                                key={tier.id}
                                className={cn(
                                    'flex flex-col overflow-hidden',
                                    tier.highlighted && 'border-re-border-strong',
                                )}
                            >
                                {tier.highlighted && (
                                    <p className="bg-re-text-primary p-2 text-center font-mono text-label uppercase text-re-surface-base">
                                        Best fit for multi-facility teams
                                    </p>
                                )}
                                <div className="flex flex-1 flex-col p-6">
                                    <div className="mb-2 flex items-center gap-2.5">
                                        <Icon className="h-[18px] w-[18px] shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                        <span className="text-subheading text-re-text-primary">{tier.name}</span>
                                        {tier.beta && (
                                            <Badge size="sm">Beta</Badge>
                                        )}
                                    </div>
                                    <p className="mb-3 text-small text-re-text-tertiary">{tier.description}</p>
                                    <Badge tone="brand" size="sm" className="mb-4 self-start">
                                        Founding rate
                                    </Badge>

                                    <div className="mb-5">
                                        <div className="flex items-baseline gap-1.5">
                                            <span className="text-title tabular-nums text-re-text-primary">${tier.partnerAnnual}</span>
                                            <span className="text-ui text-re-text-tertiary">/mo</span>
                                        </div>
                                        <p className="mt-1 text-small text-re-text-tertiary">
                                            <span className="line-through">${tier.gaAnnual}/mo</span>
                                            {' '}Standard list price · billed annually
                                        </p>
                                        <p className="mt-0.5 text-small text-re-text-tertiary">
                                            ${tier.partnerMonthly}/mo if billed monthly
                                        </p>
                                    </div>

                                    <PricingCheckoutButton
                                        tierId={tier.id}
                                        label={tier.cta}
                                        highlighted={tier.highlighted}
                                    />

                                    <ul className="flex flex-1 flex-col gap-2.5">
                                        {tier.features.map((f, i) => (
                                            <li key={i} className="flex items-start gap-2">
                                                <Check className="mt-[3px] h-3.5 w-3.5 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                                <span className="text-small text-re-text-secondary">{f}</span>
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            </Card>
                        );
                    })}
                </div>
                <p className="mt-5 text-center text-small text-re-text-tertiary">
                    Base plan includes 500 CTEs/month. Standard and Premium are unlimited. Need more on Base? Additional CTE pricing is set in your agreement.{' '}
                    <Link href="/terms" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">See Terms</Link> for full details.
                </p>

                <Card padding="spacious" className="mx-auto mt-10 max-w-[68ch] text-center">
                    <p className="mb-2 text-subheading text-re-text-primary">
                        Founding Design Partner Program
                    </p>
                    <p className="mx-auto mb-2 max-w-[60ch] text-ui leading-relaxed text-re-text-secondary">
                        50% off standard list pricing under your executed design-partner terms. White-glove onboarding, custom integration scoping, and direct founder support.
                    </p>
                    <p className="mx-auto mb-3 max-w-[60ch] text-small leading-relaxed text-re-text-tertiary">
                        We are accepting a limited number of early testers ahead of the July 2028 FSMA 204 enforcement window. Your Founding rate is controlled by your agreement, including scope for facilities, add-ons, taxes, and plan changes.
                    </p>
                    <p className="mx-auto mb-5 max-w-[60ch] text-small leading-relaxed text-re-text-tertiary">
                        Larger deployments are scoped with the team so onboarding, billing, and integration support match your operating model.
                    </p>
                    <Button asChild size="lg">
                        <Link href="/signup" className="no-underline">
                            Apply as founding design partner <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                        </Link>
                    </Button>
                </Card>
            </Container>

            <section className="border-y border-re-border-subtle">
                <Container width="marketing" className="py-7">
                    <div className="flex flex-col items-center justify-center gap-6 sm:flex-row sm:gap-10">
                        <div className="flex items-center gap-2.5 text-ui text-re-text-secondary">
                            <Lock className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            <span>Managed-provider encryption at rest · encrypted transport</span>
                        </div>
                        <div className="hidden h-4 w-px bg-re-border sm:block" />
                        <div className="flex items-center gap-2.5 text-ui text-re-text-secondary">
                            <ShieldCheck className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            <span>Security posture and subprocessors documented in the Trust Center</span>
                        </div>
                        <div className="hidden h-4 w-px bg-re-border sm:block" />
                        <div className="flex items-center gap-2.5 text-ui text-re-text-secondary">
                            <KeyRound className="h-4 w-4 shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                            <span>Core PostgreSQL tenant scoping · <Link href="/security" className="text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand">Security details →</Link></span>
                        </div>
                    </div>
                </Container>
            </section>

            <section className="border-b border-re-border-subtle">
                <Container width="marketing" className="py-10 sm:py-16">
                    <h2 className="mb-3 text-center font-display text-heading-lg text-re-text-primary">
                        Compare the operating model
                    </h2>
                    <p className="mx-auto mb-4 max-w-[60ch] text-center text-body text-re-text-secondary">
                        RegEngine is priced around facility operations, not a long enterprise procurement cycle.
                    </p>
                    <p className="mx-auto mb-10 max-w-[64ch] text-center text-small leading-relaxed text-re-text-tertiary">
                        A GMA/FMI study found that the average major food recall costs companies over $10 million in lost product, logistics, and brand damage. RegEngine&apos;s Founding rate is documented in your executed design-partner agreement.
                    </p>
                    <div className="overflow-x-auto rounded-lg border border-re-border bg-re-surface-card">
                        <table className="w-full min-w-[640px] border-collapse text-ui">
                            <thead>
                                <tr className="border-b border-re-border-subtle bg-re-surface-inset">
                                    <th scope="col" className="p-4 text-left text-label text-re-text-tertiary">Feature</th>
                                    <th scope="col" className="p-4 text-center text-label text-re-text-primary">
                                        <span>RegEngine</span>
                                    </th>
                                    <th scope="col" className="p-4 text-center text-label text-re-text-tertiary">Trustwell</th>
                                    <th scope="col" className="p-4 text-center text-label text-re-text-tertiary">ReposiTrak</th>
                                    <th scope="col" className="p-4 text-center text-label text-re-text-tertiary">TraceGains</th>
                                </tr>
                            </thead>
                            <tbody>
                                {comparisonRows.map((row, i) => (
                                    <tr key={i} className="border-b border-re-border-subtle last:border-0">
                                        <th scope="row" className="px-4 py-3.5 text-left text-small font-medium text-re-text-secondary">{row.feature}</th>
                                        <td className="px-4 py-3.5 text-center text-small font-medium text-re-text-primary">{row.regengine}</td>
                                        <td className="px-4 py-3.5 text-center text-small text-re-text-tertiary">{row.foodlogiq}</td>
                                        <td className="px-4 py-3.5 text-center text-small text-re-text-tertiary">{row.repositrak}</td>
                                        <td className="px-4 py-3.5 text-center text-small text-re-text-tertiary">{row.tracegains}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                    <p className="mt-4 text-center text-small text-re-text-tertiary">
                        Operating-model comparison based on public information and RegEngine&apos;s current early access posture; validate competitor capabilities directly before procurement decisions.
                    </p>
                </Container>
            </section>

            <Container as="section" width="prose" className="py-10 sm:py-16">
                <h2 className="mb-10 text-center font-display text-heading-lg text-re-text-primary">
                    Frequently Asked Questions
                </h2>
                <div className="flex flex-col gap-4">
                    {faq.map((item, i) => (
                        <Card key={i} padding="default" className="p-5">
                            <div className="mb-3 flex items-start gap-3">
                                <HelpCircle className="mt-0.5 h-[18px] w-[18px] shrink-0 text-re-text-tertiary" strokeWidth={1.75} aria-hidden="true" />
                                <span className="text-subheading text-re-text-primary">{item.q}</span>
                            </div>
                            <p className="pl-[30px] text-ui leading-relaxed text-re-text-secondary">{item.a}</p>
                        </Card>
                    ))}
                </div>
            </Container>

            <section className="border-t border-re-border-subtle bg-re-surface-inset">
                <Container width="marketing" className="py-10 text-center sm:py-16">
                    <h2 className="mx-auto font-display text-heading-lg text-re-text-primary">
                        Become a founding design partner
                    </h2>
                    <p className="mx-auto mb-8 mt-3 max-w-[64ch] text-body text-re-text-secondary">
                        Founding rates are documented in the executed design-partner agreement. Apply now and get the product shaped around real supplier data.
                    </p>
                    <div className="flex flex-wrap justify-center gap-3">
                        <Button asChild size="lg">
                            <Link href="/signup" className="no-underline">
                                Apply now <ArrowRight className="h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/trust" className="no-underline">
                                Review Trust Center
                            </Link>
                        </Button>
                    </div>
                </Container>
            </section>
        </div>
    );
}
