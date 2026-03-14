import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Check, X, Zap, Rocket, Crown, ArrowRight, HelpCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

export const metadata: Metadata = {
    title: 'FSMA 204 Pricing | RegEngine',
    description: 'FSMA 204 compliance pricing. Plans from $1,299/mo. Free traceability tools included.',
    openGraph: {
        title: 'FSMA 204 Pricing | RegEngine',
        description: 'FSMA 204 compliance pricing. Plans from $1,299/mo. Free traceability tools included.',
        url: 'https://www.regengine.co/pricing',
        type: 'website',
    },
};

const T = {
    bg: 'var(--re-surface-base)',
    surface: 'rgba(255,255,255,0.02)',
    border: 'rgba(255,255,255,0.06)',
    borderSubtle: 'rgba(255,255,255,0.03)',
    text: 'var(--re-text-secondary)',
    textMuted: 'var(--re-text-muted)',
    textDim: 'var(--re-text-disabled)',
    heading: 'var(--re-text-primary)',
    accent: 'var(--re-brand)',
    accentBg: 'rgba(16,185,129,0.1)',
};

const PRICING_TIERS = [
    {
        id: 'growth',
        name: 'Growth',
        Icon: Zap,
        description: 'Under $50M annual revenue',
        monthlyPrice: 1299,
        annualPrice: 1079,
        highlighted: false,
        cta: 'Start Growth Plan',
        features: [
            'Up to 10,000 CTEs/month',
            'Up to 3 locations',
            'FSMA 204 traceability workspace',
            'Supplier onboarding + FTL scoping',
            'CSV upload + API ingestion',
            'Compliance scoring + FDA-ready export',
            'Recall simulation + drill workflows',
            'Email support',
        ],
    },
    {
        id: 'scale',
        name: 'Scale',
        Icon: Rocket,
        description: '$50M\u2013$200M annual revenue',
        monthlyPrice: 2499,
        annualPrice: 2079,
        highlighted: true,
        cta: 'Start Scale Plan',
        features: [
            'Up to 100,000 CTEs/month',
            'Up to 10 locations',
            'Everything in Growth',
            'Multi-facility operations',
            'Priority onboarding support',
            'Retailer-specific readiness benchmarks',
            'Priority support',
        ],
    },
    {
        id: 'enterprise',
        name: 'Enterprise',
        Icon: Crown,
        description: 'Over $200M annual revenue',
        monthlyPrice: null,
        annualPrice: null,
        highlighted: false,
        cta: 'Talk to us',
        features: [
            'Unlimited CTEs + locations',
            'Everything in Scale',
            'Dedicated implementation plan',
            'Custom SLA + security review support',
            'Advanced integration and data architecture',
            'Executive sponsor + quarterly strategic reviews',
        ],
    },
];

const COMPETITOR_COMPARISON = [
    { feature: 'Starting Price', regengine: '$1,299/mo', foodlogiq: '$32,000+/yr', repositrak: '$2,148/facility/yr', tracegains: 'Contact Sales' },
    { feature: 'Time to First CTE', regengine: 'Under 10 minutes', foodlogiq: '6\u20138 weeks', repositrak: '<1 hour*', tracegains: '4\u20136 weeks' },
    { feature: 'Public API Docs', regengine: '\u2713', foodlogiq: '\u2717', repositrak: '\u2717', tracegains: '\u2717' },
    { feature: 'Free Trial', regengine: '14 days', foodlogiq: 'Demo only', repositrak: 'Demo only', tracegains: 'Demo only' },
    { feature: 'Self-Serve Signup', regengine: '\u2713', foodlogiq: '\u2717', repositrak: '\u2717', tracegains: '\u2717' },
    { feature: 'Developer Sandbox', regengine: '\u2713', foodlogiq: '\u2717', repositrak: '\u2717', tracegains: '\u2717' },
];

const FAQ = [
    { q: 'How do you decide between Growth and Scale?', a: 'Pricing is mapped to annual revenue bands: Growth is for teams under $50M, Scale is for $50M\u2013$200M, and Enterprise is custom above that.' },
    { q: 'Can I switch plans anytime?', a: "Yes! Upgrade anytime and we\u2019ll prorate. Downgrade at the end of your billing cycle." },
    { q: 'Do you offer pilot engagements?', a: 'Yes. We run structured pilot engagements for qualified teams preparing for retailer and FDA traceability requirements.' },
    { q: 'Do you offer annual contracts?', a: 'Yes. Annual contracts are available for all plans.' },
    { q: 'What integrations are available?', a: 'Core APIs and export flows are available today. ERP, retailer, and partner-system work should be evaluated by delivery mode: native API, webhook, CSV/SFTP import, export-only, or custom-scoped implementation.' },
    { q: 'How does self-serve differ from the design partner path?', a: 'Growth and Scale are the standard workspace plans. The design partner path is for customers who need custom integrations, guided rollout, or implementation support beyond standard onboarding.' },
];

export default function PricingPage() {
    return (
        <div className="re-page" style={{ minHeight: '100vh', background: T.bg, color: T.text }}>
            {/* Hero */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '900px', margin: '0 auto', padding: '80px 24px 60px', textAlign: 'center' }}>
                <Badge style={{ background: T.accentBg, color: T.accent, border: '1px solid rgba(16,185,129,0.2)', marginBottom: '20px' }}>
                    Transparent Pricing
                </Badge>
                <h1 style={{ fontSize: 'clamp(32px, 5vw, 48px)', fontWeight: 700, color: T.heading, lineHeight: 1.1, margin: '0 0 16px' }}>
                    FSMA 204 Compliance,<br />
                    <span className="text-re-brand">Priced by Revenue Tier</span>
                </h1>
                <p style={{ fontSize: '18px', color: T.textMuted, maxWidth: '560px', margin: '0 auto 16px', lineHeight: 1.6 }}>
                    Simple pricing for food safety teams: Growth, Scale, and Enterprise.
                </p>
                <p style={{ fontSize: '14px', color: T.textDim }}>
                    Annual pricing shown below (save ~17%). Monthly billing also available.
                </p>
                <p style={{ fontSize: '13px', color: T.textDim, marginTop: '12px' }}>
                    Standard plans cover the core workspace. Custom integrations and contractual SLA work route through the design partner or enterprise process.
                </p>
            </section>

            {/* Pricing Cards */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '1280px', margin: '0 auto', padding: '0 24px 60px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px' }}>
                    {PRICING_TIERS.map((tier) => {
                        const Icon = tier.Icon;
                        return (
                            <div
                                key={tier.id}
                                style={{
                                    background: T.surface,
                                    border: tier.highlighted ? '2px solid rgba(16,185,129,0.3)' : `1px solid ${T.border}`,
                                    borderRadius: '12px', overflow: 'hidden', display: 'flex', flexDirection: 'column',
                                }}
                            >
                                {tier.highlighted && (
                                    <div style={{ background: T.accent, color: '#000', textAlign: 'center', padding: '6px', fontSize: '12px', fontWeight: 600 }}>
                                        Most Popular
                                    </div>
                                )}
                                <div style={{ padding: '24px', flex: 1, display: 'flex', flexDirection: 'column' }}>
                                    <div className="flex items-center gap-2.5 mb-2">
                                        <div style={{ background: tier.highlighted ? T.accentBg : T.surface, border: `1px solid ${tier.highlighted ? 'rgba(16,185,129,0.2)' : T.border}`, borderRadius: '8px', padding: '8px' }}>
                                            <Icon style={{ width: 18, height: 18, color: tier.highlighted ? T.accent : T.textMuted }} />
                                        </div>
                                        <span style={{ fontSize: '18px', fontWeight: 600, color: T.heading }}>{tier.name}</span>
                                    </div>
                                    <p style={{ fontSize: '13px', color: T.textDim, marginBottom: '20px' }}>{tier.description}</p>

                                    <div style={{ marginBottom: '20px' }}>
                                        {tier.annualPrice !== null ? (
                                            <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                                                <span style={{ fontSize: '36px', fontWeight: 700, color: T.heading }}>${tier.annualPrice}</span>
                                                <span style={{ color: T.textMuted, fontSize: '14px' }}>/mo</span>
                                            </div>
                                        ) : (
                                            <span style={{ fontSize: '28px', fontWeight: 700, color: T.heading }}>Custom</span>
                                        )}
                                        {tier.monthlyPrice !== null && (
                                            <p style={{ fontSize: '12px', color: T.textDim, marginTop: '4px' }}>
                                                ${tier.monthlyPrice}/mo billed monthly
                                            </p>
                                        )}
                                    </div>

                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', flex: 1 }}>
                                        {tier.features.map((f, i) => (
                                            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                                                <Check style={{ width: 14, height: 14, color: T.accent, marginTop: 3, flexShrink: 0 }} />
                                                <span style={{ fontSize: '13px', color: T.text }}>{f}</span>
                                            </div>
                                        ))}
                                    </div>

                                    <Link href={tier.id === 'enterprise' ? '/contact' : `/checkout?plan=${tier.id}&billing=annual`}>
                                        <Button
                                            style={{
                                                width: '100%', marginTop: '24px',
                                                background: tier.highlighted ? T.accent : 'transparent',
                                                color: tier.highlighted ? '#000' : T.text,
                                                border: tier.highlighted ? 'none' : `1px solid ${T.border}`,
                                                fontWeight: 600,
                                            }}
                                        >
                                            {tier.cta}
                                            <ArrowRight className="ml-2 w-4 h-4" />
                                        </Button>
                                    </Link>
                                </div>
                            </div>
                        );
                    })}
                </div>
                <p style={{ textAlign: 'center', fontSize: '12px', color: T.textDim, marginTop: '20px' }}>
                    All plans include a standard CTE volume. Additional Critical Tracking Events billed at $0.001/CTE.{' '}
                    <Link href="/terms" style={{ color: T.accent, textDecoration: 'underline' }}>See Terms</Link> for full details.
                </p>
                <p style={{ textAlign: 'center', fontSize: '12px', color: T.textDim, marginTop: '10px' }}>
                    Review the{' '}
                    <Link href="/trust" style={{ color: T.accent, textDecoration: 'underline' }}>Trust Center</Link>
                    {' '}for retention posture, support windows, and integration delivery modes before production rollout.
                </p>
            </section>

            {/* Competitor Comparison */}
            <section style={{ position: 'relative', zIndex: 2, background: T.surface, borderTop: `1px solid ${T.border}`, borderBottom: `1px solid ${T.border}`, padding: '60px 24px' }}>
                <div className="max-w-[1000px] mx-auto">
                    <h2 style={{ fontSize: '28px', fontWeight: 700, color: T.heading, textAlign: 'center', marginBottom: '12px' }}>
                        See How We Compare
                    </h2>
                    <p style={{ textAlign: 'center', color: T.textMuted, marginBottom: '40px', maxWidth: '500px', margin: '0 auto 40px' }}>
                        The competition charges enterprise prices for basic traceability. We believe compliance should be accessible.
                    </p>
                    <div style={{ background: T.bg, border: `1px solid ${T.border}`, borderRadius: '12px', overflow: 'hidden' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                        <th style={{ textAlign: 'left', padding: '16px', fontSize: '13px', color: T.textMuted, fontWeight: 500 }}>Feature</th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '13px', background: T.accentBg }}>
                                            <span style={{ color: T.accent, fontWeight: 700 }}>RegEngine</span>
                                        </th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '13px', color: T.textDim }}>FoodLogiQ</th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '13px', color: T.textDim }}>ReposiTrak</th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '13px', color: T.textDim }}>TraceGains</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {COMPETITOR_COMPARISON.map((row, i) => (
                                        <tr key={i} style={{ borderBottom: `1px solid ${T.borderSubtle}` }}>
                                            <td style={{ padding: '14px 16px', fontSize: '13px', color: T.text, fontWeight: 500 }}>{row.feature}</td>
                                            <td style={{ textAlign: 'center', padding: '14px 16px', fontSize: '13px', background: T.accentBg, color: T.accent, fontWeight: 600 }}>{row.regengine}</td>
                                            <td style={{ textAlign: 'center', padding: '14px 16px', fontSize: '13px', color: T.textDim }}>{row.foodlogiq}</td>
                                            <td style={{ textAlign: 'center', padding: '14px 16px', fontSize: '13px', color: T.textDim }}>{row.repositrak}</td>
                                            <td style={{ textAlign: 'center', padding: '14px 16px', fontSize: '13px', color: T.textDim }}>{row.tracegains}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    <p style={{ fontSize: '11px', color: T.textDim, textAlign: 'center', marginTop: '16px' }}>
                        * ReposiTrak pricing from publicly listed $179/facility/month. Competitor data from public sources as of Jan 2026.
                    </p>
                </div>
            </section>

            {/* FAQ */}
            <section style={{ position: 'relative', zIndex: 2, maxWidth: '700px', margin: '0 auto', padding: '60px 24px' }}>
                <h2 style={{ fontSize: '28px', fontWeight: 700, color: T.heading, textAlign: 'center', marginBottom: '40px' }}>
                    Frequently Asked Questions
                </h2>
                <div className="flex flex-col gap-4">
                    {FAQ.map((item, i) => (
                        <div key={i} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: '12px', padding: '20px' }}>
                            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', marginBottom: '12px' }}>
                                <HelpCircle style={{ width: 18, height: 18, color: T.accent, marginTop: 2, flexShrink: 0 }} />
                                <span style={{ fontSize: '15px', fontWeight: 600, color: T.heading }}>{item.q}</span>
                            </div>
                            <p style={{ fontSize: '14px', color: T.textMuted, paddingLeft: '30px', lineHeight: 1.6 }}>{item.a}</p>
                        </div>
                    ))}
                </div>
            </section>

            {/* CTA */}
            <section style={{ position: 'relative', zIndex: 2, background: 'linear-gradient(135deg, var(--re-brand) 0%, #0ea5e9 100%)', padding: '60px 24px' }}>
                <div style={{ maxWidth: '600px', margin: '0 auto', textAlign: 'center' }}>
                    <h2 style={{ fontSize: '28px', fontWeight: 700, color: '#fff', marginBottom: '12px' }}>
                        Ready to Choose Your Plan?
                    </h2>
                    <p style={{ fontSize: '16px', color: 'rgba(255,255,255,0.9)', marginBottom: '32px' }}>
                        Book a fast fit-check and we will map your operation to the right FSMA plan.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/contact">
                            <Button style={{ background: '#fff', color: T.accent, fontWeight: 600, padding: '14px 24px' }}>
                                Talk to Us <ArrowRight className="ml-2 w-4 h-4" />
                            </Button>
                        </Link>
                        <Link href="/trust">
                            <Button variant="outline" style={{ background: 'transparent', color: '#fff', border: '1px solid rgba(255,255,255,0.3)', padding: '14px 24px' }}>
                                Review Trust Center
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
