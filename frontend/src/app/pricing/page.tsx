import type { Metadata } from 'next';
import { PricingPageClient } from '@/components/pricing/PricingPageClient';
import type { PricingComparisonRow, PricingFaqItem } from '@/components/pricing/PricingPageClient';

export const metadata: Metadata = {
    title: 'FSMA 204 Pricing | RegEngine',
    description: 'FSMA 204 traceability readiness from $425/mo. Transparent design-partner pricing with onboarding terms controlled by your agreement.',
    openGraph: {
        title: 'FSMA 204 Pricing | RegEngine',
        description: 'FSMA 204 traceability readiness from $425/mo. Transparent design-partner pricing with onboarding terms controlled by your agreement.',
        url: 'https://regengine.co/pricing',
        type: 'website',
    },
};

// Cache pricing for 1 hour server-side so the page stays fast even when
// the billing service is slow. Falls back to hardcoded data on error.
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
        // Billing service unreachable — graceful degradation to hardcoded data.
        return null;
    }
}

const PRICING_TIERS = [
    {
        id: 'base',
        name: 'Base',
        icon: 'zap' as const,
        description: '1 facility, getting started',
        gaMonthly: 999,
        gaAnnual: 849,
        partnerMonthly: 499,
        partnerAnnual: 425,
        highlighted: false,
        cta: 'Apply for Base',
        features: [
            '1 facility',
            'Up to 500 CTEs/month',
            'FSMA 204 traceability workspace',
            'Supplier onboarding + FTL scoping',
            'CSV upload + API ingestion',
            'Self-check scoring + FDA-oriented sortable export workflow',
            'Recall drill workflows',
            'Email support',
        ],
    },
    {
        id: 'standard',
        name: 'Standard',
        icon: 'rocket' as const,
        description: '2–3 facilities, scaling up',
        gaMonthly: 1299,
        gaAnnual: 1099,
        partnerMonthly: 649,
        partnerAnnual: 549,
        highlighted: true,
        cta: 'Apply for Standard',
        features: [
            '2–3 facilities',
            'No per-CTE caps (fair use)',
            'Everything in Base',
            'Multi-facility operations',
            'Retailer-specific readiness benchmarks',
            'FDA-oriented sortable export + EPCIS 2.0 support',
            'Priority email support',
        ],
    },
    {
        id: 'premium',
        name: 'Premium',
        icon: 'crown' as const,
        description: '4+ facilities, full coverage',
        gaMonthly: 1499,
        gaAnnual: 1275,
        partnerMonthly: 749,
        partnerAnnual: 639,
        highlighted: false,
        cta: 'Apply for Premium',
        features: [
            '4+ facilities',
            'No per-CTE caps (fair use)',
            'Everything in Standard',
            'Priority onboarding support',
            'Custom integration scoping (per scope of work)',
            'Shared Slack channel (per agreement)',
            'Quarterly compliance review (scheduled per agreement)',
        ],
    },
];

const COMPETITOR_COMPARISON: PricingComparisonRow[] = [
    { feature: 'Time to first FDA-oriented export', regengine: 'Design-partner workflow', foodlogiq: 'Enterprise implementation', repositrak: 'Retailer-coordinated', tracegains: 'Enterprise implementation' },
    { feature: 'Public API + OpenAPI Docs', regengine: 'Available for contracted workspaces', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
    { feature: 'Self-Serve Signup', regengine: 'Available in staged rollout', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
    { feature: 'Developer Sandbox', regengine: 'Available in staged rollout', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
    { feature: 'Hash-manifested audit trail', regengine: 'Supported where export workflow creates manifests', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
    { feature: 'Free Trial', regengine: 'Design-partner terms', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
    { feature: 'Pricing Model', regengine: 'Indicative design-partner ranges; agreement controls', foodlogiq: 'Validate directly', repositrak: 'Validate directly', tracegains: 'Validate directly' },
];

const FAQ: PricingFaqItem[] = [
    { q: 'How do I choose between Base, Standard, and Premium?', a: 'It comes down to facility count. Base covers 1 facility with up to 500 CTEs/month. Standard handles 2–3 facilities with unlimited CTEs. Premium is for 4+ facilities with dedicated support and quarterly compliance reviews.' },
    { q: 'What do Founding Design Partners get?', a: 'Founding Design Partner discounts are documented in the executed order form or design-partner agreement, including term, scope, renewal, taxes, add-ons, plan-change treatment, onboarding, and integration support.' },
    { q: 'Can I switch plans anytime?', a: 'Plan changes are handled under your executed order form or design-partner agreement. We scope upgrades, downgrades, facility count, and billing changes before applying them.' },
    { q: 'Do you offer annual billing?', a: 'Annual and monthly billing can be scoped during procurement. Pricing shown is indicative; the executed agreement controls final plan, billing period, and checkout availability.' },
    { q: 'Does my partner pricing ever change?', a: 'Partner pricing is controlled by the executed order form or design-partner agreement, including renewal, scope, add-ons, taxes, and plan changes.' },
    { q: 'What integrations are available?', a: 'Core APIs and export flows are available today. ERP, retailer, and partner-system integrations are evaluated per delivery mode: native API, webhook, CSV/SFTP import, or custom-scoped implementation.' },
    { q: 'What if the FDA delays enforcement again?', a: 'Major retailers are already requiring traceability data from suppliers regardless of the FDA timeline. RegEngine gives you the tooling and records to support either trigger — the FDA rule or a retailer mandate.' },
    { q: 'Do I need this if I\'m a small farm?', a: 'FSMA 204 applies to entities on the Food Traceability List handling specific foods. Use our free FTL Checker to see if your products are covered.' },
    { q: 'Can I integrate with my existing ERP?', a: 'RegEngine accepts data via API, CSV upload, or scoped ERP integration. Guided onboarding is available for approved design-partner workspaces. Timeline, support, and commercial terms are confirmed during scoping.' },
    { q: 'What happens to my data?', a: 'Data is encrypted in transit. Encryption at rest is provided by our managed database and storage providers (see the Trust Center subprocessor list). Tenant data is isolated via PostgreSQL row-level policies; tenant-trust hardening is in active rollout. We do not share or sell your data.' },
];

export default async function PricingPage() {
    // Attempt to load live pricing from the billing service.
    // On failure (service down, network error, bad payload) we silently fall
    // back to the statically-defined PRICING_TIERS above.
    const livePlans = await fetchBillingPlans();

    const pricingTiers = livePlans
        ? PRICING_TIERS.map((tier) => {
              const live = livePlans.find((p) => p.id === tier.id);
              if (!live) return tier;
              return {
                  ...tier,
                  ...(live.ga_monthly !== undefined && { gaMonthly: live.ga_monthly }),
                  ...(live.ga_annual !== undefined && { gaAnnual: live.ga_annual }),
                  ...(live.partner_monthly !== undefined && { partnerMonthly: live.partner_monthly }),
                  ...(live.partner_annual !== undefined && { partnerAnnual: live.partner_annual }),
                  ...(live.description !== undefined && { description: live.description }),
                  ...(Array.isArray(live.features) && live.features.length > 0 && { features: live.features }),
              };
          })
        : PRICING_TIERS;

    return <PricingPageClient pricingTiers={pricingTiers} comparisonRows={COMPETITOR_COMPARISON} faq={FAQ} />;
}
