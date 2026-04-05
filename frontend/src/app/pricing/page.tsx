import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Check, X, Zap, Rocket, Crown, ArrowRight, HelpCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PricingCheckoutButton } from '@/components/billing/PricingCheckoutButton';

export const metadata: Metadata = {
    title: 'FSMA 204 Pricing | RegEngine',
    description: 'FSMA 204 compliance from $425/mo. Founding Design Partners lock in 50% off for life.',
    openGraph: {
        title: 'FSMA 204 Pricing | RegEngine',
        description: 'FSMA 204 compliance from $425/mo. Founding Design Partners lock in 50% off for life.',
        url: 'https://www.regengine.co/pricing',
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
        Icon: Zap,
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
            'Compliance scoring + FDA-ready export',
            'Recall drill workflows',
            'Email support',
        ],
    },
    {
        id: 'standard',
        name: 'Standard',
        Icon: Rocket,
        description: '2\u20133 facilities, scaling up',
        gaMonthly: 1299,
        gaAnnual: 1099,
        partnerMonthly: 649,
        partnerAnnual: 549,
        highlighted: true,
        cta: 'Start Standard Plan',
        features: [
            '2\u20133 facilities',
            'Unlimited CTEs',
            'Everything in Base',
            'Multi-facility operations',
            'Retailer-specific readiness benchmarks',
            'FDA-ready export + EPCIS 2.0',
            'Priority email support',
        ],
    },
    {
        id: 'premium',
        name: 'Premium',
        Icon: Crown,
        description: '4+ facilities, full coverage',
        gaMonthly: 1499,
        gaAnnual: 1275,
        partnerMonthly: 749,
        partnerAnnual: 639,
        highlighted: false,
        cta: 'Start Premium Plan',
        features: [
            '4+ facilities',
            'Unlimited CTEs',
            'Everything in Standard',
            'Priority onboarding support',
            'Custom integration scoping',
            'Dedicated Slack channel',
            'Quarterly compliance reviews',
        ],
    },
];

const COMPETITOR_COMPARISON = [
    { feature: 'Starting Price', regengine: '$425/mo (partner)', foodlogiq: 'Enterprise pricing', repositrak: 'From $59/mo*', tracegains: 'Contact Sales' },
    { feature: 'Time to First CTE', regengine: 'Under 10 minutes', foodlogiq: 'Weeks (implementation)', repositrak: '<1 hour*', tracegains: 'Weeks (implementation)' },
    { feature: 'Public API Docs', regengine: '\u2713', foodlogiq: '\u2717', repositrak: '\u2717', tracegains: '\u2717' },
    { feature: 'Free Trial', regengine: '14 days', foodlogiq: 'Demo only', repositrak: 'Demo only', tracegains: 'Demo only' },
    { feature: 'Self-Serve Signup', regengine: '\u2713', foodlogiq: '\u2717', repositrak: '\u2717', tracegains: '\u2717' },
    { feature: 'Developer Sandbox', regengine: '\u2713', foodlogiq: '\u2717', repositrak: '\u2717', tracegains: '\u2717' },
    { feature: 'Payment Methods', regengine: 'Card, ACH, wire', foodlogiq: 'Enterprise contract', repositrak: 'Card', tracegains: 'Enterprise contract' },
];

const FAQ = [
    { q: 'How do I choose between Base, Standard, and Premium?', a: 'It comes down to facility count. Base covers 1 facility with up to 500 CTEs/month. Standard handles 2\u20133 facilities with unlimited CTEs. Premium is for 4+ facilities with dedicated support and quarterly compliance reviews.' },
    { q: 'What do Founding Design Partners get?', a: 'Founding Design Partners lock in 50% off GA pricing for the life of their account. You also get white-glove onboarding, custom integration scoping, direct founder support, and a dedicated Slack channel. Your partner rate never increases.' },
    { q: 'Can I switch plans anytime?', a: "Yes! Upgrade anytime and we\u2019ll prorate. Downgrade at the end of your billing cycle." },
    { q: 'Do you offer annual billing?', a: 'Yes. Annual billing saves ~15% compared to monthly. Both options are available on all plans.' },
    { q: 'Does my partner pricing ever change?', a: 'No. Founding Design Partners lock in 50% off for the life of their account. Your rate never increases. This is our commitment to the partners who helped shape the product.' },
    { q: 'What integrations are available?', a: 'Core APIs and export flows are available today. ERP, retailer, and partner-system integrations are evaluated per delivery mode: native API, webhook, CSV/SFTP import, or custom-scoped implementation.' },
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

    return (
        <div className="re-page min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* Hero */}
            <section className="relative z-[2] max-w-[900px] mx-auto pt-14 sm:pt-20 pb-10 sm:pb-[60px] px-4 sm:px-6 text-center">
                <Badge className="bg-[var(--re-brand-muted)] text-[var(--re-brand)] border border-[var(--re-surface-border)] mb-5">
                    Founding Design Partners — 50% Off for Life
                </Badge>
                <h1 className="text-[clamp(32px,5vw,48px)] font-bold text-[var(--re-text-primary)] leading-[1.1] mb-4">
                    FSMA 204 Compliance,<br />
                    <span className="text-re-brand">Priced for Mid-Market</span>
                </h1>
                <p className="text-lg text-[var(--re-text-muted)] max-w-[600px] mx-auto mb-4 leading-relaxed">
                    Three plans sized by facility count. Founding Design Partners lock in 50% off for the life of their account — white-glove onboarding and direct founder support included.
                </p>
                <p className="text-sm text-[var(--re-text-disabled)]">
                    Annual billing saves ~15%. Monthly billing also available.
                </p>
            </section>

            {/* Pricing Cards */}
            <section className="relative z-[2] max-w-[1280px] mx-auto px-4 sm:px-6 pb-10 sm:pb-[60px]">
                <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-5">
                    {pricingTiers.map((tier) => {
                        const Icon = tier.Icon;
                        return (
                            <div
                                key={tier.id}
                                className={`bg-[var(--re-surface-card)] rounded-2xl overflow-hidden flex flex-col transition-all duration-300 ${
                                    tier.highlighted
                                        ? 'border-2 border-[var(--re-brand)] shadow-[0_8px_32px_rgba(16,185,129,0.12),0_0_0_1px_var(--re-surface-border)]'
                                        : 'border border-[var(--re-surface-border)] shadow-[0_2px_12px_rgba(0,0,0,0.06)]'
                                }`}
                            >
                                {tier.highlighted && (
                                    <div className="bg-[var(--re-brand)] text-white text-center p-2 text-xs font-bold tracking-[0.03em]">
                                        Most Popular
                                    </div>
                                )}
                                <div className="p-6 flex-1 flex flex-col">
                                    <div className="flex items-center gap-2.5 mb-2">
                                        <div className={`border border-[var(--re-surface-border)] rounded-[10px] p-2 ${
                                            tier.highlighted ? 'bg-[var(--re-brand-muted)]' : 'bg-[var(--re-surface-elevated)]'
                                        }`}>
                                            <Icon className={`w-[18px] h-[18px] ${
                                                tier.highlighted ? 'text-[var(--re-brand)]' : 'text-[var(--re-text-muted)]'
                                            }`} />
                                        </div>
                                        <span className="text-lg font-semibold text-[var(--re-text-primary)]">{tier.name}</span>
                                    </div>
                                    <p className="text-[13px] text-[var(--re-text-disabled)] mb-3">{tier.description}</p>
                                    <span className="inline-block text-[11px] font-semibold bg-[rgba(16,185,129,0.1)] text-[var(--re-brand)] px-2 py-[3px] rounded-md mb-4">
                                        50% Off — Founding Design Partner
                                    </span>

                                    <div className="mb-5">
                                        <div className="flex items-baseline gap-1.5">
                                            <span className="text-4xl font-bold text-[var(--re-text-primary)]">${tier.partnerAnnual}</span>
                                            <span className="text-[var(--re-text-muted)] text-sm">/mo</span>
                                        </div>
                                        <p className="text-xs text-[var(--re-text-disabled)] mt-1">
                                            <span className="line-through opacity-60">${tier.gaAnnual}/mo</span>
                                            {' '}General Availability (GA) price · billed annually
                                        </p>
                                        <p className="text-[11px] text-[var(--re-text-disabled)] mt-0.5">
                                            ${tier.partnerMonthly}/mo if billed monthly · 14-day free trial
                                        </p>
                                    </div>

                                    <div className="flex flex-col gap-2.5 flex-1">
                                        {tier.features.map((f, i) => (
                                            <div key={i} className="flex items-start gap-2">
                                                <Check className="w-3.5 h-3.5 text-[var(--re-brand)] mt-[3px] shrink-0" />
                                                <span className="text-[13px] text-[var(--re-text-secondary)]">{f}</span>
                                            </div>
                                        ))}
                                    </div>

                                    <PricingCheckoutButton
                                        tierId={tier.id}
                                        label={tier.cta}
                                        highlighted={tier.highlighted}
                                        style={{
                                            background: tier.highlighted ? 'var(--re-brand)' : 'var(--re-surface-elevated)',
                                            color: tier.highlighted ? '#fff' : 'var(--re-text-primary)',
                                            border: tier.highlighted ? 'none' : '1px solid var(--re-surface-border)',
                                            boxShadow: tier.highlighted ? '0 4px 16px rgba(16,185,129,0.25)' : 'none',
                                        }}
                                    />
                                </div>
                            </div>
                        );
                    })}
                </div>
                <p className="text-center text-xs text-[var(--re-text-disabled)] mt-5">
                    Base plan includes 500 CTEs/month. Standard and Premium are unlimited. Need more on Base? Add CTEs at $0.002 each.{' '}
                    <Link href="/terms" className="text-[var(--re-brand)] underline">See Terms</Link> for full details.
                </p>

                {/* Founding Design Partner callout */}
                <div className="max-w-[680px] mx-auto mt-10 rounded-2xl border-2 border-[var(--re-brand-muted)] bg-[var(--re-brand-muted)] px-8 py-7 text-center">
                    <p className="text-base font-bold text-[var(--re-brand)] mb-2">
                        Founding Design Partner Program
                    </p>
                    <p className="text-sm text-[var(--re-text-muted)] leading-[1.7] max-w-[520px] mx-auto mb-2">
                        50% off General Availability (GA) pricing for the life of your account. White-glove onboarding, custom integration scoping, direct founder support, and a dedicated Slack channel.
                    </p>
                    <p className="text-[13px] text-[var(--re-text-disabled)] leading-relaxed max-w-[480px] mx-auto mb-3">
                        We are onboarding a limited number of partners ahead of the July 2028 FSMA 204 deadline. Your Founding Design Partner rate is locked in permanently — no surprise increases, ever.
                    </p>
                    <p className="text-[13px] text-[var(--re-text-disabled)] leading-relaxed max-w-[480px] mx-auto mb-5">
                        Includes a 14-day free trial — no charge until day 15. Cancel anytime during the trial at no cost. We accept Visa, Mastercard, American Express, ACH bank transfer, and wire.
                    </p>
                    <Link href="/onboarding">
                        <Button className="bg-[var(--re-brand)] text-white font-semibold rounded-[10px] px-7 py-3 shadow-[0_4px_16px_rgba(16,185,129,0.25)]">
                            Apply as Founding Design Partner <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                </div>
            </section>

            {/* Competitor Comparison */}
            <section className="relative z-[2] py-10 sm:py-[60px] px-4 sm:px-6 bg-[var(--re-surface-card)] border-t border-b border-[var(--re-surface-border)]">
                <div className="max-w-[1000px] mx-auto">
                    <h2 className="text-[28px] font-bold text-[var(--re-text-primary)] text-center mb-3">
                        See How We Compare
                    </h2>
                    <p className="text-center text-[var(--re-text-muted)] max-w-[500px] mx-auto mb-4">
                        The competition charges enterprise prices for basic traceability. We believe compliance should be accessible.
                    </p>
                    <p className="text-center text-sm text-[var(--re-text-disabled)] max-w-[520px] mx-auto mb-10 leading-relaxed">
                        Industry studies estimate the average major food recall costs companies over $10&nbsp;million in lost product, logistics, and brand damage. RegEngine starts at $425/mo for Founding Design Partners.
                    </p>
                    <div className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-2xl overflow-hidden shadow-[0_2px_12px_rgba(0,0,0,0.06)]">
                        <div className="overflow-x-auto">
                            <table className="w-full border-collapse">
                                <thead>
                                    <tr className="border-b border-[var(--re-surface-border)]">
                                        <th className="text-left p-4 text-xs text-[var(--re-text-primary)] font-semibold uppercase tracking-[0.04em]">Feature</th>
                                        <th className="text-center p-4 text-xs bg-[var(--re-brand-muted)]">
                                            <span className="text-[var(--re-brand)] font-bold">RegEngine</span>
                                        </th>
                                        <th className="text-center p-4 text-xs text-[var(--re-text-disabled)] font-semibold">FoodLogiQ</th>
                                        <th className="text-center p-4 text-xs text-[var(--re-text-disabled)] font-semibold">ReposiTrak</th>
                                        <th className="text-center p-4 text-xs text-[var(--re-text-disabled)] font-semibold">TraceGains</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {COMPETITOR_COMPARISON.map((row, i) => (
                                        <tr key={i} className={`border-b border-[var(--re-surface-border)] ${i % 2 === 1 ? 'bg-[var(--re-surface-elevated)]' : 'bg-transparent'}`}>
                                            <td className="px-4 py-3.5 text-[13px] text-[var(--re-text-secondary)] font-medium">{row.feature}</td>
                                            <td className="text-center px-4 py-3.5 text-[13px] bg-[var(--re-brand-muted)] text-[var(--re-brand)] font-semibold">{row.regengine}</td>
                                            <td className="text-center px-4 py-3.5 text-[13px] text-[var(--re-text-disabled)]">{row.foodlogiq}</td>
                                            <td className="text-center px-4 py-3.5 text-[13px] text-[var(--re-text-disabled)]">{row.repositrak}</td>
                                            <td className="text-center px-4 py-3.5 text-[13px] text-[var(--re-text-disabled)]">{row.tracegains}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    <p className="text-[11px] text-[var(--re-text-disabled)] text-center mt-4">
                        * ReposiTrak publicly lists supplier plans from $59/mo (basic) to $179/mo (unlimited). Competitor data from public sources as of April 2026.
                    </p>
                </div>
            </section>

            {/* FAQ */}
            <section className="relative z-[2] max-w-[700px] mx-auto py-10 sm:py-[60px] px-4 sm:px-6">
                <h2 className="text-[28px] font-bold text-[var(--re-text-primary)] text-center mb-10">
                    Frequently Asked Questions
                </h2>
                <div className="flex flex-col gap-4">
                    {FAQ.map((item, i) => (
                        <div key={i} className="bg-[var(--re-surface-card)] border border-[var(--re-surface-border)] rounded-xl p-5">
                            <div className="flex items-start gap-3 mb-3">
                                <HelpCircle className="w-[18px] h-[18px] text-[var(--re-brand)] mt-0.5 shrink-0" />
                                <span className="text-[15px] font-semibold text-[var(--re-text-primary)]">{item.q}</span>
                            </div>
                            <p className="text-sm text-[var(--re-text-muted)] pl-[30px] leading-relaxed">{item.a}</p>
                        </div>
                    ))}
                </div>
            </section>

            {/* CTA */}
            <section className="relative z-[2] py-10 sm:py-[60px] px-4 sm:px-6 bg-[linear-gradient(135deg,var(--re-brand)_0%,#0ea5e9_100%)]">
                <div className="max-w-[600px] mx-auto text-center">
                    <h2 className="text-[28px] font-bold text-white mb-3">
                        Lock In 50% Off Before General Availability
                    </h2>
                    <p className="text-base text-white/90 mb-8">
                        Founding Design Partners start at $425/mo (billed annually). Apply now and get white-glove onboarding before the FSMA 204 deadline.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/onboarding">
                            <Button className="bg-white text-[var(--re-brand)] font-semibold px-6 py-3.5">
                                Apply Now <ArrowRight className="ml-2 w-4 h-4" />
                            </Button>
                        </Link>
                        <Link href="/trust">
                            <Button variant="outline" className="bg-transparent text-white border border-white/30 px-6 py-3.5">
                                Review Trust Center
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
