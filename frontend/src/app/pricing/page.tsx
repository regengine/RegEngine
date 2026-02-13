'use client';

import { useState } from 'react';
import {
    Check,
    X,
    Zap,
    Building2,
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
        id: 'starter',
        name: 'Starter',
        icon: Zap,
        description: 'For small operations getting started with FSMA 204',
        monthlyPrice: 299,
        annualPrice: 249,
        cteLimit: '10,000',
        highlighted: false,
        cta: 'Start Free Trial',
        features: [
            { text: 'API access', included: true },
            { text: '1 integration', included: true },
            { text: 'Basic Gap Analysis', included: true },
            { text: 'Email support', included: true },
            { text: 'FDA 204 export', included: true },
            { text: '7-day data retention', included: true },
            { text: 'Multi-tenant isolation', included: false },
            { text: 'Dedicated support', included: false },
            { text: 'Custom integrations', included: false },
        ],
    },
    {
        id: 'growth',
        name: 'Growth',
        icon: Rocket,
        description: 'For growing companies with multiple facilities',
        monthlyPrice: 799,
        annualPrice: 665,
        cteLimit: '100,000',
        highlighted: true,
        cta: 'Start Free Trial',
        features: [
            { text: 'Everything in Starter', included: true },
            { text: '5 integrations', included: true },
            { text: 'Advanced Gap Analysis', included: true },
            { text: 'Drift Alerts', included: true },
            { text: 'Recall drill simulator', included: true },
            { text: '90-day data retention', included: true },
            { text: 'Multi-tenant isolation', included: true },
            { text: 'Priority email support', included: true },
            { text: 'Custom integrations', included: false },
        ],
    },
    {
        id: 'scale',
        name: 'Scale',
        icon: Building2,
        description: 'For enterprises with complex supply chains',
        monthlyPrice: 1999,
        annualPrice: 1665,
        cteLimit: '1,000,000',
        highlighted: false,
        cta: 'Start Free Trial',
        features: [
            { text: 'Everything in Growth', included: true },
            { text: 'Unlimited integrations', included: true },
            { text: 'Regulatory intelligence feed', included: true },
            { text: 'Supplier health dashboard', included: true },
            { text: 'White-label reports', included: true },
            { text: 'Unlimited data retention', included: true },
            { text: 'SSO/SAML support', included: true },
            { text: 'Dedicated Slack channel', included: true },
            { text: 'Enterprise SLA', included: true },
        ],
    },
    {
        id: 'enterprise',
        name: 'Enterprise',
        icon: Crown,
        description: 'Custom solutions for the largest organizations',
        monthlyPrice: null,
        annualPrice: null,
        cteLimit: 'Unlimited',
        highlighted: false,
        cta: 'Contact Sales',
        href: 'mailto:sales@regengine.co?subject=Enterprise%20Inquiry',
        features: [
            { text: 'Everything in Scale', included: true },
            { text: 'On-premise deployment option', included: true },
            { text: 'Custom API limits', included: true },
            { text: 'Compliance consulting hours', included: true },
            { text: 'Custom contract terms', included: true },
            { text: 'Dedicated success manager', included: true },
            { text: 'SOC 2 Type II report', included: true },
            { text: 'Custom integrations', included: true },
            { text: '24/7 phone support', included: true },
        ],
    },
];

const COMPETITOR_COMPARISON = [
    { feature: 'Starting Price', regengine: '$249/mo', foodlogiq: '$32,000+/yr', repositrak: '$49-179/mo', tracegains: 'Contact Sales' },
    { feature: 'Time to First CTE', regengine: '5 minutes', foodlogiq: '6-8 weeks', repositrak: '<1 hour*', tracegains: '4-6 weeks' },
    { feature: 'Public API Docs', regengine: '✓', foodlogiq: '✗', repositrak: '✗', tracegains: '✗' },
    { feature: 'Free Trial', regengine: '14 days', foodlogiq: 'Demo only', repositrak: 'Demo only', tracegains: 'Demo only' },
    { feature: 'Self-Serve Signup', regengine: '✓', foodlogiq: '✗', repositrak: '✗', tracegains: '✗' },
    { feature: 'Developer Sandbox', regengine: '✓', foodlogiq: '✗', repositrak: '✗', tracegains: '✗' },
];

const FAQ = [
    { q: 'What happens if I exceed my CTE limit?', a: 'We charge $0.001 per CTE over your limit—no surprises, no overage charges that blow up your bill. You can also upgrade mid-cycle.' },
    { q: 'Can I switch plans anytime?', a: "Yes! Upgrade anytime and we'll prorate. Downgrade at the end of your billing cycle." },
    { q: "What's included in the free trial?", a: 'Full access to all features in your selected tier for 14 days. No credit card required to start.' },
    { q: 'Do you offer discounts for annual billing?', a: 'Yes! Save ~17% when you pay annually instead of monthly.' },
    { q: 'What integrations are available?', a: 'We support GS1 EPCIS 2.0, REST APIs for any ERP/WMS, and pre-built connectors for SAP, Oracle, and common platforms.' },
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
                    <span className="text-re-brand">Without the Enterprise Price Tag</span>
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
                    The only traceability API with public pricing. No sales calls required.
                </p>

                {/* Billing Toggle */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '16px' }}>
                    <button
                        type="button"
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
                    <Switch checked={annual} onCheckedChange={setAnnual} />
                    <button
                        type="button"
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
                            Save 17%
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

                        return (
                            <div
                                key={tier.id}
                                onClick={() => setSelectedPlan(tier.id)}
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
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
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
                                            Up to {tier.cteLimit} CTEs/month
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
                                    <Link href={tier.id === 'enterprise' ? (tier as any).href || 'mailto:sales@regengine.co' : `/checkout?plan=${tier.id}`}>
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
                                            <ArrowRight style={{ marginLeft: 8, width: 16, height: 16 }} />
                                        </Button>
                                    </Link>
                                </div>
                            </div>
                        );
                    })}
                </div>

                <p style={{ textAlign: 'center', fontSize: '13px', color: T.textDim, marginTop: '32px' }}>
                    Need more CTEs? Just <strong className="text-re-text-secondary">$0.001 per additional CTE</strong>. No surprise bills.
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
                <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
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
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '13px', color: T.textDim }}>FoodLogiQ</th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '13px', color: T.textDim }}>ReposiTrak</th>
                                        <th style={{ textAlign: 'center', padding: '16px', fontSize: '13px', color: T.textDim }}>TraceGains</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {COMPETITOR_COMPARISON.map((row, i) => (
                                        <tr key={i} style={{ borderBottom: `1px solid ${T.borderSubtle}` }}>
                                            <td style={{ padding: '14px 16px', fontSize: '13px', color: T.text, fontWeight: 500 }}>{row.feature}</td>
                                            <td style={{ textAlign: 'center', padding: '14px 16px', fontSize: '13px', background: T.accentBg, color: T.accent, fontWeight: 600 }}>
                                                {row.regengine}
                                            </td>
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
                        * ReposiTrak onboarding time is for network registration; full CTE integration varies. Competitor data from public sources as of Jan 2026.
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
                        Ready to Get Started?
                    </h2>
                    <p style={{ fontSize: '16px', color: 'rgba(255,255,255,0.9)', marginBottom: '32px' }}>
                        14-day free trial. No credit card required. First CTE in 5 minutes.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/onboarding">
                            <Button
                                style={{
                                    background: '#fff',
                                    color: T.accent,
                                    fontWeight: 600,
                                    padding: '14px 24px',
                                }}
                            >
                                Start Free Trial
                                <ArrowRight style={{ marginLeft: 8, width: 16, height: 16 }} />
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
