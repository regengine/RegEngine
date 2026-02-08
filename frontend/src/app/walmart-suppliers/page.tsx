'use client';

import { useState } from 'react';
import {
    Clock,
    Shield,
    CheckCircle2,
    ArrowRight,
    AlertTriangle,
    Package,
    FileCheck,
    Zap,
    Calendar,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { useToast } from '@/components/ui/use-toast';
import FSMAChecklist from '@/components/fsma-checklist';
import Link from 'next/link';

/* ─────────────────────────────────────────────────────────────
   DESIGN TOKENS — Matched to homepage design system
   ───────────────────────────────────────────────────────────── */
const T = {
    bg: '#06090f',
    surface: 'rgba(255,255,255,0.02)',
    surfaceHover: 'rgba(255,255,255,0.04)',
    border: 'rgba(255,255,255,0.06)',
    borderSubtle: 'rgba(255,255,255,0.03)',
    text: '#c8d1dc',
    textMuted: '#64748b',
    textDim: '#475569',
    heading: '#e2e8f0',
    accent: '#10b981',       // emerald
    accentHover: '#059669',
    warning: '#f59e0b',      // amber for urgency
    warningBg: 'rgba(245,158,11,0.1)',
    danger: '#ef4444',
    fontSans: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    fontMono: "'JetBrains Mono', monospace",
};


const PRICING_TIERS = [
    {
        revenue: 'Under $50M',
        price: '$999',
        features: ['Up to 10,000 CTEs/month', '3 locations', 'Email support', 'FDA 204 export'],
    },
    {
        revenue: '$50M - $200M',
        price: '$1,999',
        features: ['Up to 100,000 CTEs/month', '10 locations', 'Priority support', 'Mock recall drills', 'Integration support'],
        highlighted: true,
    },
    {
        revenue: 'Over $200M',
        price: 'Custom',
        features: ['Unlimited CTEs', 'Unlimited locations', 'Dedicated support', 'On-premise option', 'Custom SLA'],
    },
];

export default function WalmartSuppliersPage() {
    const [email, setEmail] = useState('');
    const [companyName, setCompanyName] = useState('');
    const [submitted, setSubmitted] = useState(false);
    const { toast } = useToast();

    const handleAssessment = (e: React.FormEvent) => {
        e.preventDefault();
        if (email && companyName) {
            localStorage.setItem('walmart_supplier_lead', JSON.stringify({ email, companyName, date: new Date().toISOString() }));
            setSubmitted(true);
            toast({
                title: 'Assessment Requested',
                description: "We'll send your free Walmart-readiness assessment within 24 hours.",
            });
        }
    };

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

            {/* ─── URGENCY BANNER ─── */}
            <div
                style={{
                    background: T.warningBg,
                    borderBottom: `1px solid ${T.border}`,
                    padding: '12px 24px',
                    position: 'relative',
                    zIndex: 2,
                }}
            >
                <div
                    style={{
                        maxWidth: '1120px',
                        margin: '0 auto',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '12px',
                    }}
                >
                    <AlertTriangle style={{ width: 18, height: 18, color: T.warning }} />
                    <span style={{ fontSize: '14px', color: T.warning, fontWeight: 500 }}>
                        Walmart's traceability deadline is earlier than FDA's July 2028. Don't lose shelf space.
                    </span>
                </div>
            </div>

            {/* ─── HERO ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '1120px',
                    margin: '0 auto',
                    padding: '80px 24px 60px',
                    textAlign: 'center',
                }}
            >
                {/* Gradient glow */}
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
                        background: T.warningBg,
                        color: T.warning,
                        border: `1px solid rgba(245,158,11,0.2)`,
                        marginBottom: '20px',
                    }}
                >
                    Walmart Supplier Requirements
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
                    Walmart-Ready<br />
                    <span style={{ color: T.accent }}>In 30 Days or Less</span>
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
                    Meet Walmart's internal traceability requirements before you lose your spot on the shelf.
                    API-first. No portal logins. No spreadsheets.
                </p>

                {/* Early Access Badge */}
                <div
                    style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '12px',
                        background: T.surface,
                        border: `1px solid ${T.border}`,
                        borderRadius: '9999px',
                        padding: '12px 24px',
                        marginBottom: '32px',
                    }}
                >
                    <Shield style={{ width: 20, height: 20, color: T.accent }} />
                    <span style={{ fontWeight: 600, color: T.heading, fontSize: '14px' }}>
                        Founder-Led Early Access
                    </span>
                    <span style={{ color: T.textDim, fontSize: '13px' }}>
                        direct support, fast iteration
                    </span>
                </div>

                <div style={{ display: 'flex', gap: '12px', justifyContent: 'center', flexWrap: 'wrap' }}>
                    <Link href="#assessment">
                        <Button
                            style={{
                                background: T.accent,
                                color: '#000',
                                fontWeight: 600,
                                padding: '12px 24px',
                                fontSize: '15px',
                            }}
                        >
                            Get Free Assessment
                            <ArrowRight style={{ marginLeft: 8, width: 16, height: 16 }} />
                        </Button>
                    </Link>
                    <Link href="/ftl-checker">
                        <Button
                            variant="outline"
                            style={{
                                background: 'transparent',
                                color: T.text,
                                border: `1px solid ${T.border}`,
                                padding: '12px 24px',
                                fontSize: '15px',
                            }}
                        >
                            Try FTL Checker Free
                        </Button>
                    </Link>
                </div>
            </section>

            {/* ─── THE PROBLEM / SOLUTION ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '1120px',
                    margin: '0 auto',
                    padding: '60px 24px',
                }}
            >
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))',
                        gap: '40px',
                        alignItems: 'start',
                    }}
                >
                    {/* Problem Side */}
                    <div>
                        <h2 style={{ fontSize: '28px', fontWeight: 700, color: T.heading, marginBottom: '16px' }}>
                            The Walmart Reality
                        </h2>
                        <p style={{ fontSize: '16px', color: T.textMuted, lineHeight: 1.7, marginBottom: '24px' }}>
                            Walmart's internal compliance deadline is <strong style={{ color: T.heading }}>earlier than FDA's July 2028</strong>.
                            Suppliers who can't demonstrate traceability capability are being deprioritized or dropped entirely.
                        </p>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            {[
                                { icon: AlertTriangle, color: T.danger, title: 'Lose Your Shelf Space', desc: 'Walmart is actively evaluating suppliers on traceability readiness' },
                                { icon: Clock, color: T.warning, title: '24-Hour FDA Response Required', desc: 'If FDA requests your data, you have 24 hours. Not 24 days.' },
                                { icon: FileCheck, color: T.warning, title: "Spreadsheets Won't Cut It", desc: 'FDA requires electronic, sortable, searchable records' },
                            ].map((item, i) => (
                                <div key={i} style={{ display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
                                    <item.icon style={{ width: 18, height: 18, color: item.color, marginTop: 4, flexShrink: 0 }} />
                                    <div>
                                        <p style={{ fontWeight: 600, color: T.heading, fontSize: '14px', marginBottom: 2 }}>{item.title}</p>
                                        <p style={{ fontSize: '13px', color: T.textDim }}>{item.desc}</p>
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* Solution Side */}
                    <div
                        style={{
                            background: T.surface,
                            border: `1px solid ${T.border}`,
                            borderRadius: '12px',
                            padding: '24px',
                        }}
                    >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '20px' }}>
                            <Zap style={{ width: 20, height: 20, color: T.accent }} />
                            <span style={{ fontSize: '16px', fontWeight: 600, color: T.heading }}>The RegEngine Solution</span>
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                            {[
                                'API plugs into your existing WMS/ERP',
                                'No portal logins for your team',
                                'Automatic CTE capture from existing workflows',
                                '5-second trace across entire supply chain',
                                'FDA-ready export at the click of a button',
                            ].map((item, i) => (
                                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                    <CheckCircle2 style={{ width: 16, height: 16, color: T.accent, flexShrink: 0 }} />
                                    <span style={{ fontSize: '14px', color: T.text }}>{item}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* ─── FSMA CHECKLIST ─── */}
            <FSMAChecklist />

            {/* ─── PRICING ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '1120px',
                    margin: '0 auto',
                    padding: '60px 24px',
                }}
            >
                <div style={{ textAlign: 'center', marginBottom: '40px' }}>
                    <h2 style={{ fontSize: '28px', fontWeight: 700, color: T.heading, marginBottom: '12px' }}>
                        Simple, Transparent Pricing
                    </h2>
                    <p style={{ color: T.textMuted, fontSize: '15px' }}>
                        Based on your company size. No hidden fees. Cancel anytime.
                    </p>
                </div>

                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                        gap: '20px',
                    }}
                >
                    {PRICING_TIERS.map((tier, i) => (
                        <div
                            key={tier.revenue}
                            style={{
                                background: T.surface,
                                border: tier.highlighted ? `2px solid ${T.accent}` : `1px solid ${T.border}`,
                                borderRadius: '12px',
                                padding: tier.highlighted ? '0' : '24px',
                                overflow: 'hidden',
                            }}
                        >
                            {tier.highlighted && (
                                <div
                                    style={{
                                        background: T.accent,
                                        color: '#000',
                                        textAlign: 'center',
                                        padding: '8px',
                                        fontSize: '12px',
                                        fontWeight: 600,
                                        textTransform: 'uppercase',
                                        letterSpacing: '0.05em',
                                    }}
                                >
                                    Most Common
                                </div>
                            )}
                            <div style={{ padding: tier.highlighted ? '24px' : '0' }}>
                                <p style={{ fontSize: '12px', color: T.textDim, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '8px' }}>
                                    {tier.revenue} Revenue
                                </p>
                                <p style={{ fontSize: '32px', fontWeight: 700, color: T.heading, marginBottom: '20px' }}>
                                    {tier.price}
                                    {tier.price !== 'Custom' && <span style={{ fontSize: '14px', fontWeight: 400, color: T.textMuted }}>/mo</span>}
                                </p>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                                    {tier.features.map((feature, j) => (
                                        <div key={j} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                                            <CheckCircle2 style={{ width: 14, height: 14, color: T.accent, marginTop: 3, flexShrink: 0 }} />
                                            <span style={{ fontSize: '13px', color: T.text }}>{feature}</span>
                                        </div>
                                    ))}
                                </div>
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ─── ASSESSMENT FORM ─── */}
            <section
                id="assessment"
                style={{
                    position: 'relative',
                    zIndex: 2,
                    background: T.surface,
                    borderTop: `1px solid ${T.border}`,
                    borderBottom: `1px solid ${T.border}`,
                    padding: '60px 24px',
                }}
            >
                <div style={{ maxWidth: '480px', margin: '0 auto', textAlign: 'center' }}>
                    <Calendar style={{ width: 40, height: 40, color: T.accent, margin: '0 auto 16px' }} />
                    <h2 style={{ fontSize: '28px', fontWeight: 700, color: T.heading, marginBottom: '12px' }}>
                        Free Walmart-Readiness Assessment
                    </h2>
                    <p style={{ color: T.textMuted, fontSize: '15px', marginBottom: '32px', lineHeight: 1.6 }}>
                        I'll personally review your current traceability setup
                        and provide a detailed gap analysis — free of charge.
                    </p>

                    {!submitted ? (
                        <form onSubmit={handleAssessment} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                            <div style={{ textAlign: 'left' }}>
                                <label style={{ fontSize: '13px', fontWeight: 500, color: T.text, display: 'block', marginBottom: '6px' }}>
                                    Company Name
                                </label>
                                <Input
                                    placeholder="Acme Produce Co."
                                    value={companyName}
                                    onChange={(e) => setCompanyName(e.target.value)}
                                    required
                                    style={{
                                        background: T.bg,
                                        border: `1px solid ${T.border}`,
                                        color: T.text,
                                    }}
                                />
                            </div>
                            <div style={{ textAlign: 'left' }}>
                                <label style={{ fontSize: '13px', fontWeight: 500, color: T.text, display: 'block', marginBottom: '6px' }}>
                                    Work Email
                                </label>
                                <Input
                                    type="email"
                                    placeholder="you@company.com"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    style={{
                                        background: T.bg,
                                        border: `1px solid ${T.border}`,
                                        color: T.text,
                                    }}
                                />
                            </div>
                            <Button
                                type="submit"
                                style={{
                                    background: T.accent,
                                    color: '#000',
                                    fontWeight: 600,
                                    padding: '14px 24px',
                                    width: '100%',
                                }}
                            >
                                Get Free Assessment
                                <ArrowRight style={{ marginLeft: 8, width: 16, height: 16 }} />
                            </Button>
                            <p style={{ fontSize: '12px', color: T.textDim, textAlign: 'center' }}>
                                No commitment required. Assessment delivered within 24 hours.
                            </p>
                        </form>
                    ) : (
                        <div
                            style={{
                                background: T.bg,
                                border: `1px solid ${T.border}`,
                                borderRadius: '12px',
                                padding: '32px',
                            }}
                        >
                            <CheckCircle2 style={{ width: 40, height: 40, color: T.accent, margin: '0 auto 16px' }} />
                            <h3 style={{ fontSize: '20px', fontWeight: 600, color: T.heading, marginBottom: '8px' }}>
                                Assessment Requested!
                            </h3>
                            <p style={{ color: T.textMuted, fontSize: '14px', marginBottom: '20px' }}>
                                We'll send your Walmart-readiness assessment to {email} within 24 hours.
                            </p>
                            <Link href="/ftl-checker">
                                <Button
                                    variant="outline"
                                    style={{
                                        background: 'transparent',
                                        color: T.text,
                                        border: `1px solid ${T.border}`,
                                    }}
                                >
                                    Check Your FTL Coverage While You Wait
                                </Button>
                            </Link>
                        </div>
                    )}
                </div>
            </section>

            {/* ─── TRUST BADGES ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    padding: '48px 24px',
                }}
            >
                <div style={{ maxWidth: '900px', margin: '0 auto', textAlign: 'center' }}>
                    <p style={{ fontSize: '13px', color: T.textDim, marginBottom: '24px', letterSpacing: '0.05em' }}>
                        BUILT FOR SUPPLIERS TO MAJOR RETAILERS
                    </p>
                    <div
                        style={{
                            display: 'flex',
                            flexWrap: 'wrap',
                            justifyContent: 'center',
                            gap: '32px',
                        }}
                    >
                        {[
                            { icon: Package, label: 'FSMA 204 Compliant' },
                            { icon: Shield, label: '23 FDA Categories' },
                            { icon: FileCheck, label: 'SHA-256 Audit Trail' },
                            { icon: Zap, label: '24-Hour FDA Response' },
                        ].map((item, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                                <item.icon style={{ width: 18, height: 18, color: T.textDim }} />
                                <span style={{ fontSize: '13px', color: T.textMuted }}>{item.label}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* Inline keyframes */}
            <style>{`
                input::placeholder { color: ${T.textDim}; }
                * { box-sizing: border-box; margin: 0; }
            `}</style>
        </div>
    );
}
