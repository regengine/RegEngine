import type { Metadata } from 'next';
import Link from 'next/link';
import {
    Check, X, Zap, Rocket, Crown, ArrowRight, HelpCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';

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

const T = {
    bg: 'var(--re-surface-base)',
    surface: 'var(--re-surface-card)',
    border: 'var(--re-surface-border)',
    borderSubtle: 'var(--re-surface-border)',
    text: 'var(--re-text-secondary)',
    textMuted: 'var(--re-text-muted)',
    textDim: 'var(--re-text-disabled)',
    heading: 'var(--re-text-primary)',
    accent: 'var(--re-brand)',
    accentBg: 'var(--re-brand-muted)',
};

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
    { feature: 'Starting Price', regengine: '$425/mo (partner)', foodlogiq: '$32,000+/yr', repositrak: 'From $59/mo*', tracegains: 'Contact Sales' },
    { feature: 'Time to First CTE', regengine: 'Under 10 minutes', foodlogiq: '6\u20138 weeks', repositrak: '<1 hour*', tracegains: '4\u20136 weeks' },
    { feature: 'Public API Docs', regengine: '\u2713', foodlogiq: '\u2717', repositrak: '\u2717', tracegains: '\u2717' },
    { feature: 'Free Trial', regengine: '14 days', foodlogiq: 'Demo only', repositrak: 'Demo only', tracegains: 'Demo only' },
    { feature: 'Self-Serve Signup', regengine: '\u2713', foodlogiq: '\u2717', repositrak: '\u2717', tracegains: '\u2717' },
    { feature: 'Developer Sandbox', regengine: '\u2713', foodlogiq: '\u2717', repositrak: '\u2717', tracegains: '\u2717' },
];

const FAQ = [
    { q: 'How do I choose between Base, Standard, and Premium?', a: 'It comes down to facility count. Base covers 1 facility with up to 500 CTEs/month. Standard handles 2\u20133 facilities with unlimited CTEs. Premium is for 4+ facilities with dedicated support and quarterly compliance reviews.' },
    { q: 'What do Founding Design Partners get?', a: 'Founding Design Partners lock in 50% off GA pricing for the life of their account. You also get white-glove onboarding, custom integration scoping, direct founder support, and a dedicated Slack channel. Your partner rate never increases.' },
    { q: 'Can I switch plans anytime?', a: "Yes! Upgrade anytime and we\u2019ll prorate. Downgrade at the end of your billing cycle." },
    { q: 'Do you offer annual billing?', a: 'Yes. Annual billing saves ~15% compared to monthly. Both options are available on all plans.' },
    { q: 'Does my partner pricing ever change?', a: 'No. Founding Design Partners lock in 50% off for the life of their account. Your rate never increases. This is our commitment to the partners who helped shape the product.' },
    { q: 'What integrations are available?', a: 'Core APIs and export flows are available today. ERP, retailer, and partner-system integrations are evaluated per delivery mode: native API, webhook, CSV/SFTP import, or custom-scoped implementation.' },
];

export default function PricingPage() {
    return (
        <div className="re-page" style={{ minHeight: '100vh', background: T.bg, color: T.text }}>
            {/* Hero */}
            <section className="relative z-[2] max-w-[900px] mx-auto pt-14 sm:pt-20 pb-10 sm:pb-[60px] px-4 sm:px-6 text-center">
                <Badge style={{ background: T.accentBg, color: T.accent, border: `1px solid ${T.border}`, marginBottom: '20px' }}>
                    Founding Design Partners — 50% Off for Life
                </Badge>
                <h1 style={{ fontSize: 'clamp(32px, 5vw, 48px)', fontWeight: 700, color: T.heading, lineHeight: 1.1, margin: '0 0 16px' }}>
                    FSMA 204 Compliance,<br />
                    <span className="text-re-brand">Priced for Mid-Market</span>
                </h1>
                <p style={{ fontSize: '18px', color: T.textMuted, maxWidth: '600px', margin: '0 auto 16px', lineHeight: 1.6 }}>
                    Three plans sized by facility count. Founding Design Partners lock in 50% off for the life of their account — white-glove onboarding and direct founder support included.
                </p>
                <p style={{ fontSize: '14px', color: T.textDim }}>
                    Annual billing saves ~15%. Monthly billing also available.
                </p>
            </section>

            {/* Pricing Cards */}
            <section className="relative z-[2] max-w-[1280px] mx-auto px-4 sm:px-6 pb-10 sm:pb-[60px]">
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '20px' }}>
                    {PRICING_TIERS.map((tier) => {
                        const Icon = tier.Icon;
                        return (
                            <div
                                key={tier.id}
                                style={{
                                    background: T.surface,
                                    border: tier.highlighted ? `2px solid ${T.accent}` : `1px solid ${T.border}`,
                                    borderRadius: '16px', overflow: 'hidden', display: 'flex', flexDirection: 'column',
                                    boxShadow: tier.highlighted
                                        ? `0 8px 32px rgba(16,185,129,0.12), 0 0 0 1px ${T.border}`
                                        : `0 2px 12px rgba(0,0,0,0.06)`,
                                    transition: 'all 0.3s',
                                }}
                            >
                                {tier.highlighted && (
                                    <div style={{ background: T.accent, color: '#fff', textAlign: 'center', padding: '8px', fontSize: '12px', fontWeight: 700, letterSpacing: '0.03em' }}>
                                        Most Popular
                                    </div>
                                )}
                                <div style={{ padding: '24px', flex: 1, display: 'flex', flexDirection: 'column' }}>
                                    <div className="flex items-center gap-2.5 mb-2">
                                        <div style={{ background: tier.highlighted ? T.accentBg : 'var(--re-surface-elevated)', border: `1px solid ${T.border}`, borderRadius: '10px', padding: '8px' }}>
                                            <Icon style={{ width: 18, height: 18, color: tier.highlighted ? T.accent : T.textMuted }} />
                                        </div>
                                        <span style={{ fontSize: '18px', fontWeight: 600, color: T.heading }}>{tier.name}</span>
                                    </div>
                                    <p style={{ fontSize: '13px', color: T.textDim, marginBottom: '12px' }}>{tier.description}</p>
                                    <span style={{ display: 'inline-block', fontSize: '11px', fontWeight: 600, background: 'rgba(16,185,129,0.1)', color: T.accent, padding: '3px 8px', borderRadius: '6px', marginBottom: '16px' }}>
                                        50% Off — Founding Design Partner
                                    </span>

                                    <div style={{ marginBottom: '20px' }}>
                                        <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px' }}>
                                            <span style={{ fontSize: '36px', fontWeight: 700, color: T.heading }}>${tier.partnerAnnual}</span>
                                            <span style={{ color: T.textMuted, fontSize: '14px' }}>/mo</span>
                                        </div>
                                        <p style={{ fontSize: '12px', color: T.textDim, marginTop: '4px' }}>
                                            <span style={{ textDecoration: 'line-through', opacity: 0.6 }}>${tier.gaAnnual}/mo</span>
                                            {' '}GA price · billed annually
                                        </p>
                                        <p style={{ fontSize: '11px', color: T.textDim, marginTop: '2px' }}>
                                            ${tier.partnerMonthly}/mo if billed monthly
                                        </p>
                                    </div>

                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', flex: 1 }}>
                                        {tier.features.map((f, i) => (
                                            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                                                <Check style={{ width: 14, height: 14, color: T.accent, marginTop: 3, flexShrink: 0 }} />
                                                <span style={{ fontSize: '13px', color: T.text }}>{f}</span>
                                            </div>
                                        ))}
                                    </div>

                                    <Link href="/alpha">
                                        <Button
                                            style={{
                                                width: '100%', marginTop: '24px',
                                                background: tier.highlighted ? T.accent : 'var(--re-surface-elevated)',
                                                color: tier.highlighted ? '#fff' : T.heading,
                                                border: tier.highlighted ? 'none' : `1px solid ${T.border}`,
                                                fontWeight: 600,
                                                borderRadius: '10px',
                                                padding: '12px 20px',
                                                boxShadow: tier.highlighted ? '0 4px 16px rgba(16,185,129,0.25)' : 'none',
                                                transition: 'all 0.2s',
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
                    Base plan includes 500 CTEs/month. Standard and Premium are unlimited. Need more on Base? Add CTEs at $0.002 each.{' '}
                    <Link href="/terms" style={{ color: T.accent, textDecoration: 'underline' }}>See Terms</Link> for full details.
                </p>

                {/* Founding Design Partner callout */}
                <div style={{
                    maxWidth: '680px', margin: '40px auto 0',
                    borderRadius: '16px', border: `2px solid var(--re-brand-muted)`,
                    background: T.accentBg, padding: '28px 32px', textAlign: 'center',
                }}>
                    <p style={{ fontSize: '16px', fontWeight: 700, color: T.accent, marginBottom: '8px' }}>
                        Founding Design Partner Program
                    </p>
                    <p style={{ fontSize: '14px', color: T.textMuted, lineHeight: 1.7, marginBottom: '8px', maxWidth: '520px', margin: '0 auto 8px' }}>
                        50% off GA pricing for the life of your account. White-glove onboarding, custom integration scoping, direct founder support, and a dedicated Slack channel.
                    </p>
                    <p style={{ fontSize: '13px', color: T.textDim, lineHeight: 1.6, marginBottom: '20px', maxWidth: '480px', margin: '0 auto 20px' }}>
                        We are onboarding a limited number of partners ahead of the July 2028 FSMA 204 deadline. Your Founding Design Partner rate is locked in permanently — no surprise increases, ever.
                    </p>
                    <Link href="/onboarding">
                        <Button style={{
                            background: T.accent, color: '#fff', fontWeight: 600,
                            borderRadius: '10px', padding: '12px 28px',
                            boxShadow: '0 4px 16px rgba(16,185,129,0.25)',
                        }}>
                            Apply as Founding Design Partner <ArrowRight className="ml-2 w-4 h-4" />
                        </Button>
                    </Link>
                </div>
            </section>

            {/* Competitor Comparison */}
            <section className="relative z-[2] py-10 sm:py-[60px] px-4 sm:px-6" style={{ background: T.surface, borderTop: `1px solid ${T.border}`, borderBottom: `1px solid ${T.border}` }}>
                <div className="max-w-[1000px] mx-auto">
                    <h2 style={{ fontSize: '28px', fontWeight: 700, color: T.heading, textAlign: 'center', marginBottom: '12px' }}>
                        See How We Compare
                    </h2>
                    <p style={{ textAlign: 'center', color: T.textMuted, marginBottom: '16px', maxWidth: '500px', margin: '0 auto 16px' }}>
                        The competition charges enterprise prices for basic traceability. We believe compliance should be accessible.
                    </p>
                    <p style={{ textAlign: 'center', fontSize: '14px', color: T.textDim, maxWidth: '520px', margin: '0 auto 40px', lineHeight: 1.6 }}>
                        Industry studies estimate the average major food recall costs companies over $10&nbsp;million in lost product, logistics, and brand damage. RegEngine starts at $425/mo for Founding Design Partners.
                    </p>
                    <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: '16px', overflow: 'hidden', boxShadow: '0 2px 12px rgba(0,0,0,0.06)' }}>
                        <div style={{ overflowX: 'auto' }}>
                            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                                <thead>
                                    <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                        <th style={{ textAlign: 'left', padding: '16px', fontSize: '12px', color: T.heading, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Feature</th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '12px', background: T.accentBg }}>
                                            <span style={{ color: T.accent, fontWeight: 700 }}>RegEngine</span>
                                        </th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '12px', color: T.textDim, fontWeight: 600 }}>FoodLogiQ</th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '12px', color: T.textDim, fontWeight: 600 }}>ReposiTrak</th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '12px', color: T.textDim, fontWeight: 600 }}>TraceGains</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {COMPETITOR_COMPARISON.map((row, i) => (
                                        <tr key={i} style={{ borderBottom: `1px solid ${T.border}`, background: i % 2 === 1 ? 'var(--re-surface-elevated)' : 'transparent' }}>
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
                        * ReposiTrak publicly lists supplier plans from $59/mo (basic) to $179/mo (unlimited). Competitor data from public sources as of Jan 2026.
                    </p>
                </div>
            </section>

            {/* FAQ */}
            <section className="relative z-[2] max-w-[700px] mx-auto py-10 sm:py-[60px] px-4 sm:px-6">
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
            <section className="relative z-[2] py-10 sm:py-[60px] px-4 sm:px-6" style={{ background: 'linear-gradient(135deg, var(--re-brand) 0%, #0ea5e9 100%)' }}>
                <div style={{ maxWidth: '600px', margin: '0 auto', textAlign: 'center' }}>
                    <h2 style={{ fontSize: '28px', fontWeight: 700, color: '#fff', marginBottom: '12px' }}>
                        Lock In 50% Off Before GA Launch
                    </h2>
                    <p style={{ fontSize: '16px', color: 'rgba(255,255,255,0.9)', marginBottom: '32px' }}>
                        Founding Design Partners start at $425/mo (billed annually). Apply now and get white-glove onboarding before the FSMA 204 deadline.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/onboarding">
                            <Button style={{ background: '#fff', color: T.accent, fontWeight: 600, padding: '14px 24px' }}>
                                Apply Now <ArrowRight className="ml-2 w-4 h-4" />
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
