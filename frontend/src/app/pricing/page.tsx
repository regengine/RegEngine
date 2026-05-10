import type { Metadata } from 'next';
import { PricingPageClient } from '@/components/pricing/PricingPageClient';
import type { PricingComparisonRow, PricingFaqItem } from '@/components/pricing/PricingPageClient';

export const metadata: Metadata = {
    title: 'FSMA 204 Pricing | RegEngine',
    description: 'FSMA 204 compliance from $425/mo. Transparent pricing, self-serve signup, no enterprise contract required.',
    openGraph: {
        title: 'FSMA 204 Pricing | RegEngine',
        description: 'FSMA 204 compliance from $425/mo. Transparent pricing, self-serve signup, no enterprise contract required.',
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
        const apiKey = process.env.REGENGINE_API_KEY || '';
        const res = await fetch(`${base}/billing/plans`, {
            headers: {
                'Content-Type': 'application/json',
                ...(apiKey ? { 'X-RegEngine-API-Key': apiKey } : {}),
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
        cta: 'Start Base Plan',
        features: [
            '1 facility',
            'Up to 500 CTEs/month',
            'FSMA 204 traceability workspace',
            'Supplier onboarding + FTL scoping',
            'CSV upload + API ingestion',
            'Self-check scoring + §1.1455(c)-formatted export',
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
        cta: 'Start Standard Plan',
        features: [
            '2–3 facilities',
            'No per-CTE caps (fair use)',
            'Everything in Base',
            'Multi-facility operations',
            'Retailer-specific readiness benchmarks',
            '§1.1455(c)-formatted export + EPCIS 2.0',
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
        cta: 'Start Premium Plan',
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
    { feature: 'Time to first FDA-formatted export', regengine: 'Minutes (self-serve)', foodlogiq: 'Enterprise implementation', repositrak: 'Retailer-coordinated', tracegains: 'Enterprise implementation' },
    { feature: 'Public API + OpenAPI Docs', regengine: '✓', foodlogiq: '◐', repositrak: '◐', tracegains: '◐' },
    { feature: 'Self-Serve Signup', regengine: '✓', foodlogiq: '✗', repositrak: '◐', tracegains: '✗' },
    { feature: 'Developer Sandbox', regengine: '✓', foodlogiq: '✗', repositrak: '✗', tracegains: '✗' },
    { feature: 'Hash-manifested audit trail', regengine: '✓', foodlogiq: '◐', repositrak: '◐', tracegains: '◐' },
    { feature: 'Free Trial', regengine: '14 days', foodlogiq: 'Demo only', repositrak: 'Demo only', tracegains: 'Demo only' },
    { feature: 'Pricing Model', regengine: 'Published, per-facility', foodlogiq: 'Enterprise contract', repositrak: 'Per-supplier tiers', tracegains: 'Enterprise contract' },
];

const FAQ: PricingFaqItem[] = [
    { q: 'How do I choose between Base, Standard, and Premium?', a: 'It comes down to facility count. Base covers 1 facility with up to 500 CTEs/month. Standard handles 2–3 facilities with unlimited CTEs. Premium is for 4+ facilities with dedicated support and quarterly compliance reviews.' },
    { q: 'What do Founding Design Partners get?', a: 'Founding Design Partners lock in 50% off GA pricing for the life of their account. You also get white-glove onboarding and custom integration scoping. Support is delivered per the terms of your partner agreement. Your partner rate never increases.' },
    { q: 'Can I switch plans anytime?', a: "Yes! Upgrade anytime and we'll prorate. Downgrade at the end of your billing cycle." },
    { q: 'Do you offer annual billing?', a: 'Yes. Annual billing saves ~15% compared to monthly. Both options are available on all plans.' },
    { q: 'Does my partner pricing ever change?', a: 'No. Founding Design Partners lock in 50% off for the life of their account. Your rate never increases. This is our commitment to the partners who helped shape the product.' },
    { q: 'What integrations are available?', a: 'Core APIs and export flows are available today. ERP, retailer, and partner-system integrations are evaluated per delivery mode: native API, webhook, CSV/SFTP import, or custom-scoped implementation.' },
    { q: 'What if the FDA delays enforcement again?', a: 'Major retailers are already requiring traceability data from suppliers regardless of the FDA timeline. RegEngine gives you the tooling and records to support either trigger — the FDA rule or a retailer mandate.' },
    { q: 'Do I need this if I\'m a small farm?', a: 'FSMA 204 applies to entities on the Food Traceability List handling specific foods. Use our free FTL Checker to see if your products are covered.' },
    { q: 'Can I integrate with my existing ERP?', a: 'Yes. RegEngine accepts data via API, CSV upload, or scoped ERP integration. Self-serve onboarding completes within days; complex ERP integrations are scoped separately.' },
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
