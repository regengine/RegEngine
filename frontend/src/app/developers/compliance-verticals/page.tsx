'use client';

import {
    ArrowLeft,
    Egg,
    Fish,
    Leaf,
    Milk,
    UtensilsCrossed,
} from 'lucide-react';
import Link from 'next/link';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Container } from '@/components/layout/container';

const FRAMEWORKS = [
    {
        id: 'fresh-produce',
        title: 'Fresh Produce',
        icon: Leaf,
        description: 'Leafy greens, herbs, melons, and fresh-cut produce workflows',
        details: 'Maps receiving, cooling, transformation, and shipping CTEs with KDE coverage patterns commonly requested by grocery buyers.',
        jsonSnippet: `{
  "profile": "fresh_produce",
  "ftl_categories": ["Leafy Greens", "Melons"],
  "required_ctes": ["RECEIVING", "TRANSFORMING", "SHIPPING"],
  "kde_focus": ["grower_lot", "harvest_date", "cooling_location"]
}`,
    },
    {
        id: 'seafood',
        title: 'Seafood',
        icon: Fish,
        description: 'Finfish and shellfish chain-of-custody controls',
        details: 'Reference scaffold for seafood obtained from a fishing vessel — uses §1.1335 First Land-Based Receiving as the entry CTE. Final CTE/KDE coverage is configured during onboarding.',
        jsonSnippet: `{
  "profile": "seafood",
  "ftl_categories": ["Fresh Finfish", "Crustaceans"],
  "required_ctes": ["FIRST_LAND_BASED_RECEIVING", "RECEIVING", "SHIPPING"],
  "kde_focus": ["harvest_vessel", "landing_date", "harvest_area"]
}`,
    },
    {
        id: 'dairy',
        title: 'Dairy',
        icon: Milk,
        description: 'Milk, cheese, and cultured product traceability profiles',
        details: 'Captures co-mingling and rework events with deterministic lineage so auditors can verify exactly which lots entered finished product batches.',
        jsonSnippet: `{
  "profile": "dairy",
  "ftl_categories": ["Soft Cheeses", "Fluid Dairy"],
  "required_ctes": ["RECEIVING", "TRANSFORMING", "PACKING", "SHIPPING"],
  "kde_focus": ["supplier_lot", "production_line", "hold_release_status"]
}`,
    },
    {
        id: 'deli-prepared',
        title: 'Deli & Prepared',
        icon: UtensilsCrossed,
        description: 'Ready-to-eat and mixed-ingredient operational profiles',
        details: 'Manages transformation-heavy workflows where a single output lot draws from many upstream inputs and must still support rapid backward tracing.',
        jsonSnippet: `{
  "profile": "deli_prepared",
  "ftl_categories": ["Ready-to-Eat Deli Salads"],
  "required_ctes": ["RECEIVING", "TRANSFORMING", "SHIPPING"],
  "kde_focus": ["input_lot_map", "recipe_revision", "pack_timestamp"]
}`,
    },
    {
        id: 'shell-eggs',
        title: 'Shell Eggs',
        icon: Egg,
        description: 'Pack-date, facility, and distributor continuity controls',
        details: 'Supports egg-specific lot and date coding expectations while preserving supplier-facility relationships needed for retailer and FDA record pulls.',
        jsonSnippet: `{
  "profile": "shell_eggs",
  "ftl_categories": ["Shell Eggs"],
  "required_ctes": ["RECEIVING", "PACKING", "SHIPPING"],
  "kde_focus": ["pack_date", "facility_registration", "distributor_reference"]
}`,
    },
];

function CodeBlock({ code }: { code: string }) {
    return (
        <pre className="overflow-x-auto rounded-md border border-re-border-subtle bg-re-surface-inset p-4 font-mono text-[0.8125rem] text-re-text-secondary">
            <code>{code}</code>
        </pre>
    );
}

export default function ComplianceVerticalsPage() {
    return (
        <div className="bg-re-surface-base text-re-text-secondary">
            <Container as="section" width="marketing" className="py-16 sm:py-20">
                <Link
                    href="/developers"
                    className="mb-8 inline-flex items-center text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                >
                    <ArrowLeft className="mr-2 h-4 w-4" strokeWidth={1.75} aria-hidden="true" />
                    Back to Developers
                </Link>

                <div>
                    <Badge tone="brand" className="mb-6 w-fit">
                        FSMA 204 Profiles
                    </Badge>
                    <h1 className="mb-4 font-display text-display text-re-text-primary">
                        Food-First Compliance
                        <br />
                        Vertical Profiles
                    </h1>
                    <p className="max-w-[68ch] text-body text-re-text-secondary">
                        Pre-built FSMA 204 profile templates for the food categories most frequently
                        requested in retailer onboarding and recall drills.
                    </p>
                </div>
            </Container>

            <Container as="section" width="marketing" className="pb-16 sm:pb-20">
                <div className="grid gap-8">
                    {FRAMEWORKS.map((framework) => (
                        <Card key={framework.id} className="overflow-hidden">
                            <div className="grid md:grid-cols-2">
                                <div className="flex min-w-0 flex-col justify-center p-6 md:p-8">
                                    <h2 className="mb-4 font-display text-heading-lg text-re-text-primary">{framework.title}</h2>

                                    <Badge tone="neutral" className="mb-4 h-auto w-fit max-w-full items-start whitespace-normal py-1 text-left">
                                        <framework.icon className="mt-0.5 h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                                        {framework.description}
                                    </Badge>

                                    <p className="mb-6 text-ui leading-relaxed text-re-text-secondary">
                                        {framework.details}
                                    </p>

                                    <div className="flex flex-wrap gap-3">
                                        <Button asChild variant="secondary" size="lg">
                                            <Link href="/docs/fsma-204" className="no-underline">View FSMA Controls</Link>
                                        </Button>
                                        <Button asChild size="lg">
                                            <Link href="/onboarding" className="no-underline">Start Guided Setup</Link>
                                        </Button>
                                    </div>
                                </div>

                                <div className="min-w-0 border-t border-re-border-subtle p-6 md:border-l md:border-t-0 md:p-8">
                                    <div className="mb-4 flex items-center justify-between gap-3">
                                        <span className="font-mono text-label uppercase text-re-text-muted">
                                            Example Seed Data
                                        </span>
                                        <Badge tone="neutral" size="sm" mono>
                                            JSON
                                        </Badge>
                                    </div>
                                    <CodeBlock code={framework.jsonSnippet} />
                                </div>
                            </div>
                        </Card>
                    ))}
                </div>
            </Container>

            <section className="border-t border-re-border-subtle bg-re-surface-inset">
                <Container width="marketing" className="py-16 text-center sm:py-20">
                    <h3 className="mb-2 font-display text-heading-lg text-re-text-primary">Built for FDA and Retailer Readiness</h3>
                    <p className="mx-auto max-w-[68ch] text-body text-re-text-secondary">
                        Each profile maps to practical CTE and KDE coverage so teams can move from supplier
                        data chaos to auditable FSMA 204 responses.
                    </p>
                </Container>
            </section>
        </div>
    );
}
