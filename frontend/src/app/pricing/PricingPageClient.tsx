'use client';

import { useState } from 'react';
import {
    Check,
    X,
    Zap,
    Rocket,
    Crown,
    ArrowRight,
    HelpCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import Link from 'next/link';

/* ─────────────────────────────────────────────────────────────
   DESIGN TOKENS — Matched to homepage design system
   ───────────────────────────────────────────────────────────── */
const T = {
    bg: 'var(--re-surface-base)',
    surface: 'rgba(255,255,255,0.02)',
    surfaceHover: 'rgba(255,255,255,0.04)',
    border: 'rgba(255,255,255,0.06)',
    borderSubtle: 'rgba(255,255,255,0.03)',
    text: 'var(--re-text-secondary)',
    textMuted: 'var(--re-text-muted)',
    textDim: 'var(--re-text-disabled)',
    heading: 'var(--re-text-primary)',
    accent: 'var(--re-brand)',
    accentHover: 'var(--re-brand-dark)',
    accentBg: 'rgba(16,185,129,0.1)',
    fontSans: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    fontMono: "'JetBrains Mono', monospace",
};

const PRICING_TIERS = [
    {
        id: 'growth',
        name: 'Growth',
        icon: Zap,
        description: 'Under $50M annual revenue',
        monthlyPrice: 999,
        annualPrice: 832,
        revenueBand: 'Under $50M annual revenue',
        highlighted: false,
        cta: 'Start Growth Plan',
        features: [
            { text: 'FSMA 204 traceability workspace', included: true },
            { text: 'Supplier onboarding + FTL scoping', included: true },
            { text: 'CSV upload + API ingestion', included: true },
            { text: 'Compliance scoring + FDA-ready export', included: true },
            { text: 'Recall simulation + drill workflows', included: true },
            { text: 'Email support', included: true },
        ],
    },
    {
        id: 'scale',
        name: 'Scale',
        icon: Rocket,
        description: '$50M–$200M annual revenue',
        monthlyPrice: 1999,
        annualPrice: 1666,
        revenueBand: '$50M–$200M annual revenue',
        highlighted: true,
        cta: 'Start Scale Plan',
        features: [
            { text: 'Everything in Growth', included: true },
            { text: 'Multi-facility operations', included: true },
            { text: 'Expanded API + webhook limits', included: true },
            { text: 'Priority onboarding support', included: true },
            { text: 'Retailer-specific readiness benchmarks', included: true },
            { text: 'Priority support', included: true },
        ],
    },
    {
        id: 'enterprise',
        name: 'Enterprise',
        icon: Crown,
        description: 'Over $200M annual revenue',
        monthlyPrice: null,
        annualPrice: null,
        revenueBand: 'Over $200M annual revenue',
        highlighted: false,
        cta: 'Talk to us',
        href: '/alpha',
        features: [
            { text: 'Everything in Scale', included: true },
            { text: 'Dedicated implementation plan', included: true },
            { text: 'Custom SLA + security review support', included: true },
            { text: 'Advanced integration and data architecture', included: true },
            { text: 'Executive sponsor + quarterly roadmap reviews', included: true },
        ],
    },
];

const COMPETITOR_COMPARISON = [
    { feature: 'Starting Price', regengine: '$999/mo', foodlogiq: '$32,000+/yr', repositrak: '$2,148/facility/yr', tracegains: 'Contact Sales' },
    { feature: 'Time to First CTE', regengine: 'Under 10 minutes', foodlogiq: '6-8 weeks', repositrak: '<1 hour*', tracegains: '4-6 weeks' },
    { feature: 'Public API Docs', regengine: '✓', foodlogiq: '✗', repositrak: '✗', tracegains: '✗' },
    { feature: 'Free Trial', regengine: '14 days', foodlogiq: 'Demo only', repositrak: 'Demo only', tracegains: 'Demo only' },
    { feature: 'Self-Serve Signup', regengine: '✓', foodlogiq: '✗', repositrak: '✗', tracegains: '✗' },
    { feature: 'Developer Sandbox', regengine: '✓', foodlogiq: '✗', repositrak: '✗', tracegains: '✗' },
];

const FAQ = [
    { q: 'How do you decide between Growth and Scale?', a: 'Pricing is mapped to annual revenue bands: Growth is for teams under $50M, Scale is for $50M–$200M, and Enterprise is custom above that.' },
    { q: 'Can I switch plans anytime?', a: "Yes! Upgrade anytime and we'll prorate. Downgrade at the end of your billing cycle." },
    { q: 'Do you offer pilot engagements?', a: 'Yes. We run structured pilot engagements for qualified teams preparing for retailer and FDA traceability requirements.' },
    { q: 'Do you offer annual contracts?', a: 'Yes. Annual contracts are available for all plans.' },
    { q: 'What integrations are available?', a: 'We support GS1 EPCIS 2.0 and REST APIs for any ERP/WMS today. SAP and Oracle connectors are on the roadmap.' },
];

export default function PricingPage() {
    const [annual, setAnnual] = useState(true);
    const [selectedPlan, setSelectedPlan] = useState<string>('growth');

    return (
        <div
            style={{
                minHeight: '100vh',
                background: T.bg,
                color: T.text,
                fontFamily: T.fontSans,
            }}
        >
            {/* Noise texture overlay */}
            <div
                style={{
                    position: 'fixed',
                    inset: 0,
                    backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='noise'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23noise)'/%3E%3C/svg%3E")`,
                    opacity: 0.015,
                    pointerEvents: 'none',
                    zIndex: 1,
                }}
            />

            {/* ─── HERO ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '900px',
                    margin: '0 auto',
                    padding: '80px 24px 60px',
                    textAlign: 'center',
                }}
            >
                <div
                    style={{
                        position: 'absolute',
                        top: '-60px',
                        left: '50%',
                        transform: 'translateX(-50%)',
                        width: '600px',
                        height: '400px',
                        background: `radial-gradient(ellipse, ${T.accent}08 0%, transparent 70%)`,
                        pointerEvents: 'none',
                    }}
                />

                <Badge
                    style={{
                        background: T.accentBg,
                        color: T.accent,
                        border: `1px solid rgba(16,185,129,0.2)`,
                        marginBottom: '20px',
                    }}
                >
                    Transparent Pricing
                </Badge>

                <h1
                    style={{
                        fontSize: 'clamp(32px, 5vw, 48px)',
                        fontWeight: 700,
                        color: T.heading,
                        lineHeight: 1.1,
                        margin: '0 0 16px',
                    }}
                >
                    FSMA 204 Compliance,<br />
                    <span className="text-re-brand">Priced by Revenue Tier</span>
                </h1>

                <p
                    style={{
                        fontSize: '18px',
                        color: T.textMuted,
                        maxWidth: '560px',
                        margin: '0 auto 32px',
                        lineHeight: 1.6,
                    }}
                >
                    Simple pricing for food safety teams: Growth, Scale, and Enterprise.
                </p>

                {/* Billing Toggle */}
                <div
                    role="group"
                    aria-label="Billing period"
                    style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px' }}
                >
                    <button
                        type="button"
                        aria-pressed={!annual}
                        onClick={() => setAnnual(false)}
                        style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            fontSize: '15px',
                            fontWeight: !annual ? 600 : 400,
                            color: !annual ? T.heading : T.textMuted,
                            transition: 'color 0.2s',
                        }}
                    >
                        Monthly
                    </button>
                    <Switch aria-label="Toggle annual billing" checked={annual} onCheckedChange={setAnnual} />
                    <button
                        type="button"
                        aria-pressed={annual}
                        onClick={() => setAnnual(true)}
                        style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            fontSize: '15px',
                            fontWeight: annual ? 600 : 400,
                            color: annual ? T.heading : T.textMuted,
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            transition: 'color 0.2s',
                        }}
                    >
                        Annual
                        <Badge
                            style={{
                                background: T.accentBg,
                                color: T.accent,
                                border: `1px solid rgba(16,185,129,0.2)`,
                                fontSize: '11px',
                            }}
                        >
                            Save ~17%
                        </Badge>
                    </button>
                </div>
            </section>

            {/* ─── PRICING CARDS ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '1280px',
                    margin: '0 auto',
                    padding: '0 24px 60px',
                }}
            >
                <div
                    role="radiogroup"
                    aria-label="Select pricing tier"
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                        gap: '20px',
                    }}
                >
                    {PRICING_TIERS.map((tier) => {
                        const Icon = tier.icon;
                        const price = annual ? tier.annualPrice : tier.monthlyPrice;
                        const isSelected = selectedPlan === tier.id;
                        const planPriceLabel = price !== null ? `$${price} per month` : 'custom pricing';

                        return (
                            <div
                                key={tier.id}
                                role="radio"
                                aria-checked={isSelected}
                                aria-label={`${tier.name} plan, ${planPriceLabel}`}
                                tabIndex={0}
                                onClick={() => setSelectedPlan(tier.id)}
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' || e.key === ' ') {
                                        e.preventDefault();
                                        setSelectedPlan(tier.id);
                                    }
                                }}
                                style={{
                                    background: T.surface,
                                    border: isSelected
                                        ? `2px solid ${T.accent}`
                                        : tier.highlighted
                                            ? `2px solid rgba(16,185,129,0.3)`
                                            : `1px solid ${T.border}`,
                                    borderRadius: '12px',
                                    overflow: 'hidden',
                                    cursor: 'pointer',
                                    transition: 'all 0.2s',
                                    display: 'flex',
                                    flexDirection: 'column',
                                }}
                            >
                                {/* Selection / Popular banner */}
                                {isSelected && (
                                    <div
                                        style={{
                                            background: T.accent,
                                            color: '#000',
                                            textAlign: 'center',
                                            padding: '6px',
                                            fontSize: '12px',
                                            fontWeight: 600,
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            gap: '4px',
                                        }}
                                    >
                                        <Check className="w-3.5 h-3.5" /> Selected
                                    </div>
                                )}
                                {tier.highlighted && !isSelected && (
                                    <div
                                        style={{
                                            background: T.accent,
                                            color: '#000',
                                            textAlign: 'center',
                                            padding: '6px',
                                            fontSize: '12px',
                                            fontWeight: 600,
                                        }}
                                    >
                                        Most Popular
                                    </div>
                                )}

                                <div style={{ padding: '24px', flex: 1, display: 'flex', flexDirection: 'column' }}>
                                    {/* Header */}
                                    <div className="flex items-center gap-2.5 mb-2">
                                        <div
                                            style={{
                                                background: tier.highlighted ? T.accentBg : T.surface,
                                                border: `1px solid ${tier.highlighted ? 'rgba(16,185,129,0.2)' : T.border}`,
                                                borderRadius: '8px',
                                                padding: '8px',
                                            }}
                                        >
                                            <Icon style={{ width: 18, height: 18, color: tier.highlighted ? T.accent : T.textMuted }} />
                                        </div>
                                        <span style={{ fontSize: '18px', fontWeight: 600, color: T.heading }}>{tier.name}</span>
                                    </div>
                                    <p style={{ fontSize: '13px', color: T.textDim, marginBottom: '20px' }}>{tier.description}</p>

                                    {/* Price */}
                                    <div style={{ marginBottom: '20px' }}>
                                        {price !== null ? (
                                            <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px' }}>
                                                <span style={{ fontSize: '36px', fontWeight: 700, color: T.heading }}>${price}</span>
                                                <span style={{ color: T.textMuted, fontSize: '14px' }}>/mo</span>
                                            </div>
                                        ) : (
                                            <span style={{ fontSize: '28px', fontWeight: 700, color: T.heading }}>Custom</span>
                                        )}
                                        <p style={{ fontSize: '12px', color: T.textDim, marginTop: '4px' }}>
                                            {tier.revenueBand}
                                        </p>
                                    </div>

                                    {/* Features */}
                                    <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', flex: 1 }}>
                                        {tier.features.map((feature, i) => (
                                            <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                                                {feature.included ? (
                                                    <Check style={{ width: 14, height: 14, color: T.accent, marginTop: 3, flexShrink: 0 }} />
                                                ) : (
                                                    <X style={{ width: 14, height: 14, color: T.textDim, marginTop: 3, flexShrink: 0 }} />
                                                )}
                                                <span style={{ fontSize: '13px', color: feature.included ? T.text : T.textDim }}>
                                                    {feature.text}
                                                </span>
                                            </div>
                                        ))}
                                    </div>

                                    {/* CTA */}
                                    <Link href={tier.id === 'enterprise' ? tier.href || '/alpha' : `/checkout?plan=${tier.id}&billing=${annual ? 'annual' : 'monthly'}`}>
                                        <Button
                                            style={{
                                                width: '100%',
                                                marginTop: '24px',
                                                background: isSelected ? T.accent : 'transparent',
                                                color: isSelected ? '#000' : T.text,
                                                border: isSelected ? 'none' : `1px solid ${T.border}`,
                                                fontWeight: 600,
                                            }}
                                        >
                                            {isSelected ? `Continue with ${tier.name}` : tier.cta}
                                            <ArrowRight className="ml-2 w-4 h-4" />
                                        </Button>
                                    </Link>
                                </div>
                            </div>
                        );
                    })}
                </div>

                <p style={{ textAlign: 'center', fontSize: '13px', color: T.textDim, marginTop: '32px' }}>
                    Need help choosing? Use annual revenue bands as a quick guide, then validate in a 30-minute planning call.
                </p>
            </section>

            {/* ─── COMPETITOR COMPARISON ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    background: T.surface,
                    borderTop: `1px solid ${T.border}`,
                    borderBottom: `1px solid ${T.border}`,
                    padding: '60px 24px',
                }}
            >
                <div className="max-w-[1000px] mx-auto">
                    <h2 style={{ fontSize: '28px', fontWeight: 700, color: T.heading, textAlign: 'center', marginBottom: '12px' }}>
                        See How We Compare
                    </h2>
                    <p style={{ textAlign: 'center', color: T.textMuted, marginBottom: '40px', maxWidth: '500px', margin: '0 auto 40px' }}>
                        The competition charges enterprise prices for basic traceability. We believe compliance should be accessible.
                    </p>

                    <div
                        style={{
                            background: T.bg,
                            border: `1px solid ${T.border}`,
                            borderRadius: '12px',
                            overflow: 'hidden',
                        }}
                    >
                        <div style={{ overflowX: 'auto' }}>
                            <table className="re-table">
                                <thead>
                                    <tr style={{ borderBottom: `1px solid ${T.border}` }}>
                                        <th style={{ textAlign: 'left', padding: '16px', fontSize: '13px', color: T.textMuted, fontWeight: 500 }}>Feature</th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '13px', background: T.accentBg }}>
                                            <span style={{ color: T.accent, fontWeight: 700 }}>RegEngine</span>
                                        </th>
                                        <th className="text-center p-4 text-[13px] text-re-text-disabled">FoodLogiQ</th>
                                        <th className="text-center p-4 text-[13px] text-re-text-disabled">ReposiTrak</th>
                                        <th className="text-center p-4 text-[13px] text-re-text-disabled">TraceGains</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {COMPETITOR_COMPARISON.map((row, i) => (
                                        <tr key={i} style={{ borderBottom: `1px solid ${T.borderSubtle}` }}>
                                            <td style={{ padding: '14px 16px', fontSize: '13px', color: T.text, fontWeight: 500 }}>{row.feature}</td>
                                            <td style={{ textAlign: 'center', padding: '14px 16px', fontSize: '13px', background: T.accentBg, color: T.accent, fontWeight: 600 }}>
                                                {row.regengine}
                                            </td>
                                            <td className="text-center px-4 py-3.5 text-[13px] text-re-text-disabled">{row.foodlogiq}</td>
                                            <td className="text-center px-4 py-3.5 text-[13px] text-re-text-disabled">{row.repositrak}</td>
                                            <td className="text-center px-4 py-3.5 text-[13px] text-re-text-disabled">{row.tracegains}</td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <p style={{ fontSize: '11px', color: T.textDim, textAlign: 'center', marginTop: '16px' }}>
                        * ReposiTrak pricing shown as $2,148/facility/year (annualized from publicly listed $179/facility/month Traceability Network pricing). ReposiTrak onboarding time is for network registration; full CTE integration varies. Competitor data from public sources as of Jan 2026.
                    </p>
                </div>
            </section>

            {/* ─── FAQ ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '700px',
                    margin: '0 auto',
                    padding: '60px 24px',
                }}
            >
                <h2 style={{ fontSize: '28px', fontWeight: 700, color: T.heading, textAlign: 'center', marginBottom: '40px' }}>
                    Frequently Asked Questions
                </h2>

                <div className="flex flex-col gap-4">
                    {FAQ.map((item, i) => (
                        <div
                            key={i}
                            style={{
                                background: T.surface,
                                border: `1px solid ${T.border}`,
                                borderRadius: '12px',
                                padding: '20px',
                            }}
                        >
                            <div style={{ display: 'flex', alignItems: 'flex-start', gap: '12px', marginBottom: '12px' }}>
                                <HelpCircle style={{ width: 18, height: 18, color: T.accent, marginTop: 2, flexShrink: 0 }} />
                                <span style={{ fontSize: '15px', fontWeight: 600, color: T.heading }}>{item.q}</span>
                            </div>
                            <p style={{ fontSize: '14px', color: T.textMuted, paddingLeft: '30px', lineHeight: 1.6 }}>{item.a}</p>
                        </div>
                    ))}
                </div>
            </section>

            {/* ─── CTA ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    background: `linear-gradient(135deg, ${T.accent} 0%, #0ea5e9 100%)`,
                    padding: '60px 24px',
                }}
            >
                <div style={{ maxWidth: '600px', margin: '0 auto', textAlign: 'center' }}>
                    <h2 style={{ fontSize: '28px', fontWeight: 700, color: '#fff', marginBottom: '12px' }}>
                        Ready to Choose Your Plan?
                    </h2>
                    <p style={{ fontSize: '16px', color: 'rgba(255,255,255,0.9)', marginBottom: '32px' }}>
                        Book a fast fit-check and we will map your operation to the right FSMA plan.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/alpha">
                            <Button
                                style={{
                                    background: '#fff',
                                    color: T.accent,
                                    fontWeight: 600,
                                    padding: '14px 24px',
                                }}
                            >
                                Talk to Us
                                <ArrowRight className="ml-2 w-4 h-4" />
                            </Button>
                        </Link>
                        <Link href="/ftl-checker">
                            <Button
                                variant="outline"
                                style={{
                                    background: 'transparent',
                                    color: '#fff',
                                    border: '1px solid rgba(255,255,255,0.3)',
                                    padding: '14px 24px',
                                }}
                            >
                                Check Your FTL Coverage First
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>

            <style>{`
                * { box-sizing: border-box; margin: 0; }
            `}</style>
        </div>
    );
}
