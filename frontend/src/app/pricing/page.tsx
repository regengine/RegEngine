import type { Metadata } from 'next';
import { PricingPageClient } from '@/components/pricing/PricingPageClient';
import type { PricingComparisonRow, PricingFaqItem } from '@/components/pricing/PricingPageClient';
import { FOUNDING_PRICE_LINE, LIST_PRICE_LINE, PILOT_LINE, PRICING_SUMMARY } from '@/lib/pricing-terms';

export const metadata: Metadata = {
    title: 'FSMA 204 Pricing | RegEngine',
    description: `FSMA 204 recordkeeping workspace pricing. ${PRICING_SUMMARY}`,
    openGraph: {
        title: 'FSMA 204 Pricing | RegEngine',
        description: `FSMA 204 recordkeeping workspace pricing. ${PRICING_SUMMARY}`,
        url: 'https://regengine.co/pricing',
        type: 'website',
    },
};

// Cache plan copy for 1 hour server-side so the page stays fast even when
// the billing service is slow. Prices come from the approved terms in
// lib/pricing-terms; the billing service only refines plan descriptions
// and feature lists.
export const revalidate = 3600;

interface BillingPlan {
    id: string;
    name: string;
    description?: string;
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
        // Billing service unreachable: caller falls back to static plan copy.
        return null;
    }
}

// Static tier copy (names, feature lists, CTAs). Prices come only from
// lib/pricing-terms; nothing here may carry a price.
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
            'Coverage and completeness checklist + FDA-oriented sortable export workflow',
            'EPCIS 2.0 export (Preview)',
            'Recall drill workflows',
            'Email support',
        ],
    },
    {
        id: 'standard',
        name: 'Standard',
        beta: true,
        icon: 'rocket' as const,
        description: '2 to 3 facilities, scaling up',
        highlighted: true,
        cta: 'Apply for Standard',
        features: [
            '2 to 3 facilities',
            'No per-CTE caps (fair use)',
            'Everything in Base',
            'Multi-facility operations',
            'Retailer-specific coverage checklist benchmarks',
            'EPCIS 2.0 export (Preview)',
            'Priority email support',
        ],
    },
    {
        id: 'premium',
        name: 'Premium',
        beta: true,
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
    { feature: 'Pricing Model', regengine: 'Published per-facility pricing; agreement controls', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
];

/** Keep Preview on any live billing feature string that names EPCIS without a status label. */
function ensureEpcisPreviewLabel(features: string[]): string[] {
    return features.map((feature) => {
        if (!/epcis/i.test(feature)) return feature;
        if (/\bpreview\b/i.test(feature)) return feature;
        return `${feature.trimEnd()} (Preview)`;
    });
}

const FAQ: PricingFaqItem[] = [
    { q: 'How do I choose between Base, Standard, and Premium?', a: 'It comes down to facility count. Base covers 1 facility with up to 500 CTEs/month. Standard (Beta) handles 2 to 3 facilities with unlimited CTEs. Premium (Beta) is for 4+ facilities with dedicated support and quarterly compliance reviews.' },
    { q: 'What does RegEngine cost?', a: `${LIST_PRICE_LINE} ${FOUNDING_PRICE_LINE} The founding design partner price applies under an executed design-partner agreement.` },
    { q: 'How does the pilot work?', a: PILOT_LINE },
    { q: 'Can I switch plans anytime?', a: 'Plan changes are handled under your executed order form or design-partner agreement. We scope upgrades, downgrades, facility count, and billing changes before applying them.' },
    { q: 'How is billing set up?', a: 'Published prices are per month, per facility. Your executed order form or design-partner agreement controls scope, taxes, add-ons, and renewal.' },
    { q: 'What integrations are available?', a: 'Core APIs and export flows are available today. ERP, retailer, and partner-system integrations are evaluated per delivery mode: CSV upload, the JSON events API, or custom-scoped implementation. EPCIS 2.0 is in Preview.' },
    { q: 'What am I paying for if I must archive externally?', a: 'FSMA 204 requires at least two-year retention of traceability records under 21 CFR 1.1455. RegEngine is a compliance evidence layer with contract-defined retention, not a long-term archive. Your subscription pays for workspace access, ingestion, validation, and export workflows. You keep off-platform archives for long-term retention. See the Trust Center retention guidance for export and archive posture.' },
    { q: 'What if the FDA delays enforcement again?', a: 'Major retailers are already requiring traceability data from suppliers regardless of the FDA timeline. RegEngine gives you the tooling and records to support either trigger: the FDA rule or a retailer mandate.' },
    { q: 'Do I need this if I\'m a small farm?', a: 'FSMA 204 applies to covered persons who manufacture, process, pack, or hold foods on the Food Traceability List. Being on the list is not the same as being a covered person. Use our free FTL Checker as a starting point, not a determination.' },
    { q: 'Can I integrate with my existing ERP?', a: 'RegEngine accepts data via API, CSV upload, or scoped ERP integration. Guided onboarding is available for approved design-partner workspaces. Timeline, support, and commercial terms are confirmed during scoping.' },
    { q: 'What happens to my data?', a: 'Data is encrypted in transit. Encryption at rest is provided by our managed database and storage providers (see the Trust Center subprocessor list). Tenant data is isolated via PostgreSQL row-level policies; tenant-trust hardening is in active rollout. We do not share or sell your data.' },
];

export default async function PricingPage() {
    // Live plan copy refines descriptions and features when billing is
    // reachable; otherwise the static tier copy is shown. Prices never come
    // from here.
    const livePlans = await fetchBillingPlans();

    const pricingTiers = PRICING_TIERS.map((tier) => {
        const live = livePlans?.find((p) => p.id === tier.id);
        return {
            ...tier,
            description: live?.description ?? tier.description,
            features: ensureEpcisPreviewLabel(
                live && Array.isArray(live.features) && live.features.length > 0 ? live.features : tier.features,
            ),
        };
    });

    return <PricingPageClient pricingTiers={pricingTiers} comparisonRows={COMPETITOR_COMPARISON} faq={FAQ} />;
}
