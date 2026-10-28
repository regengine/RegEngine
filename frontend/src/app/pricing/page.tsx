import type { Metadata } from 'next';
import Link from 'next/link';
import { PricingPageClient } from '@/components/pricing/PricingPageClient';
import type { PricingComparisonRow, PricingFaqItem } from '@/components/pricing/PricingPageClient';
import { Container } from '@/components/layout/container';
import { Button } from '@/components/ui/button';

export const metadata: Metadata = {
    title: 'FSMA 204 Pricing | RegEngine',
    description: 'FSMA 204 traceability readiness with transparent Founding rate pricing. Onboarding terms are controlled by your agreement.',
    openGraph: {
        title: 'FSMA 204 Pricing | RegEngine',
        description: 'FSMA 204 traceability readiness with transparent Founding rate pricing. Onboarding terms are controlled by your agreement.',
        url: 'https://regengine.co/pricing',
        type: 'website',
    },
};

// Cache pricing for 1 hour server-side so the page stays fast even when
// the billing service is slow. When billing is unreachable the page renders
// an honest unavailable state instead of hardcoded prices.
export const revalidate = 3600;

interface BillingPlan {
    id: string;
    name: string;
    description?: string;
    ga_monthly?: number;
    ga_annual?: number;
    partner_monthly?: number;
    partner_annual?: number;
    features?: string[];
}

async function fetchBillingPlans(): Promise<BillingPlan[] | null> {
    const adminServiceUrl =
        process.env.ADMIN_SERVICE_URL ||
        process.env.NEXT_PUBLIC_ADMIN_URL ||
        process.env.NEXT_PUBLIC_API_BASE_URL;

    if (!adminServiceUrl) return null;

    try {
        const base = adminServiceUrl.replace(/\/+$/, '');
        const res = await fetch(`${base}/billing/plans`, {
            headers: {
                'Content-Type': 'application/json',
            },
            // next.js fetch cache: honour the page-level revalidate
            next: { revalidate: 3600 },
        });

        if (!res.ok) return null;

        const data = await res.json() as { plans?: BillingPlan[] } | BillingPlan[];
        const plans = Array.isArray(data) ? data : data.plans;
        if (!Array.isArray(plans) || plans.length === 0) return null;
        return plans;
    } catch {
        // Billing service unreachable: caller renders the unavailable state.
        return null;
    }
}

// Static tier copy (names, feature lists, CTAs). Prices come only from the
// billing service; nothing here may carry a number.
const PRICING_TIERS = [
    {
        id: 'base',
        name: 'Base',
        icon: 'zap' as const,
        description: '1 facility, getting started',
        highlighted: false,
        cta: 'Apply for Base',
        features: [
            '1 facility',
            'Up to 500 CTEs/month',
            'FSMA 204 traceability workspace',
            'Supplier onboarding + FTL scoping',
            'CSV upload + API ingestion',
            'Self-check scoring + FDA-oriented sortable export workflow',
            'EPCIS 2.0 export (Preview)',
            'Recall drill workflows',
            'Email support',
        ],
    },
    {
        id: 'standard',
        name: 'Standard',
        icon: 'rocket' as const,
        description: '2 to 3 facilities, scaling up',
        highlighted: true,
        cta: 'Apply for Standard',
        features: [
            '2 to 3 facilities',
            'No per-CTE caps (fair use)',
            'Everything in Base',
            'Multi-facility operations',
            'Retailer-specific readiness benchmarks',
            'EPCIS 2.0 export (Preview)',
            'Priority email support',
        ],
    },
    {
        id: 'premium',
        name: 'Premium',
        icon: 'crown' as const,
        description: '4+ facilities, full coverage',
        highlighted: false,
        cta: 'Apply for Premium',
        features: [
            '4+ facilities',
            'No per-CTE caps (fair use)',
            'Everything in Standard',
            'Priority onboarding support',
            'Custom integration scoping (per scope of work)',
            'EPCIS 2.0 export (Preview)',
            'Shared Slack channel (per agreement)',
            'Quarterly compliance review (scheduled per agreement)',
        ],
    },
];

const COMPETITOR_COMPARISON: PricingComparisonRow[] = [
    { feature: 'Time to first FDA-oriented export', regengine: 'Design-partner workflow', foodlogiq: 'Enterprise implementation', repositrak: 'Retailer-coordinated', tracegains: 'Enterprise implementation' },
    { feature: 'Public API + OpenAPI Docs', regengine: 'Available for contracted workspaces', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
    { feature: 'Self-Serve Signup', regengine: 'Available in staged rollout', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
    { feature: 'Hash-manifested audit trail', regengine: 'Supported where export workflow creates manifests', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
    { feature: 'Free Trial', regengine: 'Design-partner terms', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
    { feature: 'Pricing Model', regengine: 'Indicative design-partner ranges; agreement controls', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
];

const FAQ: PricingFaqItem[] = [
    { q: 'How do I choose between Base, Standard, and Premium?', a: 'It comes down to facility count. Base covers 1 facility with up to 500 CTEs/month. Standard handles 2 to 3 facilities with unlimited CTEs. Premium is for 4+ facilities with dedicated support and quarterly compliance reviews.' },
    { q: 'What does the Founding rate include?', a: 'Founding rate discounts are documented in the executed order form or design-partner agreement, including term, scope, renewal, taxes, add-ons, plan-change treatment, onboarding, and integration support.' },
    { q: 'Can I switch plans anytime?', a: 'Plan changes are handled under your executed order form or design-partner agreement. We scope upgrades, downgrades, facility count, and billing changes before applying them.' },
    { q: 'Do you offer annual billing?', a: 'Annual and monthly billing can be scoped during procurement. Pricing shown is indicative; the executed agreement controls final plan, billing period, and checkout availability.' },
    { q: 'Does my Founding rate ever change?', a: 'Your Founding rate is controlled by the executed order form or design-partner agreement, including renewal, scope, add-ons, taxes, and plan changes.' },
    { q: 'What integrations are available?', a: 'Core APIs and export flows are available today. ERP, retailer, and partner-system integrations are evaluated per delivery mode: CSV upload, the JSON events API, or custom-scoped implementation. EPCIS 2.0 is in Preview.' },
    { q: 'What if the FDA delays enforcement again?', a: 'Major retailers are already requiring traceability data from suppliers regardless of the FDA timeline. RegEngine gives you the tooling and records to support either trigger: the FDA rule or a retailer mandate.' },
    { q: 'Do I need this if I\'m a small farm?', a: 'FSMA 204 applies to entities on the Food Traceability List handling specific foods. Use our free FTL Checker to see if your products are covered.' },
    { q: 'Can I integrate with my existing ERP?', a: 'RegEngine accepts data via API, CSV upload, or scoped ERP integration. Guided onboarding is available for approved design-partner workspaces. Timeline, support, and commercial terms are confirmed during scoping.' },
    { q: 'What happens to my data?', a: 'Data is encrypted in transit. Encryption at rest is provided by our managed database and storage providers (see the Trust Center subprocessor list). Tenant data is isolated via PostgreSQL row-level policies; tenant-trust hardening is in active rollout. We do not share or sell your data.' },
];

export default async function PricingPage() {
    // Load live pricing from the billing service. When it is unreachable or
    // returns no usable plans, show an honest unavailable state rather than
    // any hardcoded figures.
    const livePlans = await fetchBillingPlans();

    if (!livePlans) {
        return (
            <div className="re-page bg-re-surface-base text-re-text-secondary">
                <Container as="section" width="prose" className="py-16 text-center sm:py-24">
                    <h1 className="font-display text-display text-re-text-primary">
                        Pricing is temporarily unavailable
                    </h1>
                    <p className="mx-auto mt-4 max-w-[60ch] text-body text-re-text-secondary">
                        We could not load current plan pricing from our billing service, so no figures are shown here.
                        Plan rates are confirmed in your executed order form or design-partner agreement.
                    </p>
                    <div className="mt-8 flex flex-wrap justify-center gap-3">
                        <Button asChild size="lg">
                            <Link href="/signup" className="no-underline">
                                Apply as a founding design partner
                            </Link>
                        </Button>
                        <Button asChild variant="secondary" size="lg">
                            <Link href="/contact" className="no-underline">
                                Contact us
                            </Link>
                        </Button>
                    </div>
                </Container>
            </div>
        );
    }

    const pricingTiers = PRICING_TIERS.flatMap((tier) => {
        const live = livePlans.find((p) => p.id === tier.id);
        if (!live) return [];
        const { ga_monthly, ga_annual, partner_monthly, partner_annual } = live;
        if (
            typeof ga_monthly !== 'number' ||
            typeof ga_annual !== 'number' ||
            typeof partner_monthly !== 'number' ||
            typeof partner_annual !== 'number'
        ) {
            return [];
        }
        return [{
            ...tier,
            gaMonthly: ga_monthly,
            gaAnnual: ga_annual,
            partnerMonthly: partner_monthly,
            partnerAnnual: partner_annual,
            description: live.description ?? tier.description,
            features: Array.isArray(live.features) && live.features.length > 0 ? live.features : tier.features,
        }];
    });

    return <PricingPageClient pricingTiers={pricingTiers} comparisonRows={COMPETITOR_COMPARISON} faq={FAQ} />;
}
