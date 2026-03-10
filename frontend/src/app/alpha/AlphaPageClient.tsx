'use client';

import { useState, useRef, useEffect } from 'react';
import {
    Shield, Lock, Zap, ArrowRight, CheckCircle2,
    Clock, Users, Sparkles, ChevronRight, Mail,
    Star, TrendingUp, FileCheck, AlertTriangle,
} from 'lucide-react';
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
    purple: 'var(--re-accent-purple)',
    purpleBg: 'rgba(139,92,246,0.1)',
    fontSans: "'Instrument Sans', -apple-system, BlinkMacSystemFont, sans-serif",
    fontMono: "'JetBrains Mono', monospace",
};

const ALPHA_PERKS = [
    {
        icon: Zap,
        title: 'Priority API Access',
        description: 'Be the first to integrate with RegEngine\'s traceability API and shape the developer experience.',
    },
    {
        icon: TrendingUp,
        title: 'Locked-In Pricing',
        description: 'Alpha partners lock in founding-member pricing for the duration of their account.',
    },
    {
        icon: Users,
        title: 'Direct Founder Access',
        description: 'Weekly office hours with the founding team. Your feedback helps inform product direction.',
    },
    {
        icon: FileCheck,
        title: 'White-Glove Onboarding',
        description: 'Dedicated onboarding support to map your supply chain and configure your compliance profile.',
    },
    {
        icon: Shield,
        title: 'Compliance Head Start',
        description: 'Get FSMA 204 compliant before the July 2028 deadline while your competitors scramble.',
    },
    {
        icon: Star,
        title: 'Case Study Feature',
        description: 'Be featured as a launch partner case study — great for your brand and compliance credibility.',
    },
];

const TIMELINE = [
    { phase: 'Private Alpha', status: 'current', date: 'Current', detail: 'Invite-only · 25 companies' },
    { phase: 'Design Partner Cohort', status: 'upcoming', date: 'Rolling', detail: 'Application review · Guided onboarding' },
    { phase: 'FSMA 204 Deadline', status: 'deadline', date: 'Jul 2028', detail: 'FDA enforcement begins' },
];

export default function AlphaPage() {
    const [email, setEmail] = useState('');
    const [company, setCompany] = useState('');
    const [role, setRole] = useState('');
    const [submitted, setSubmitted] = useState(false);
    const [isSubmitting, setIsSubmitting] = useState(false);
    const [spotCount] = useState(Math.floor(Math.random() * 6) + 7);
    const [error, setError] = useState('');
    const formRef = useRef<HTMLFormElement>(null);

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!email) return;
        setIsSubmitting(true);
        setError('');

        try {
            const res = await fetch('/api/alpha-signup', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email, company, role }),
            });

            const data = await res.json();

            if (!res.ok) {
                setError(data.error || 'Something went wrong. Please try again.');
                setIsSubmitting(false);
                return;
            }

            setSubmitted(true);
        } catch {
            setError('Network error. Please check your connection and try again.');
        } finally {
            setIsSubmitting(false);
        }
    };

    return (
        <div
            style={{
                minHeight: '100vh',
                background: T.bg,
                color: T.text,
                fontFamily: T.fontSans,
                position: 'relative',
                overflow: 'hidden',
            }}
        >
            {/* Animated gradient orbs */}
            <div
                style={{
                    position: 'fixed',
                    top: '-20%',
                    left: '-10%',
                    width: '600px',
                    height: '600px',
                    background: `radial-gradient(circle, ${T.accent}12 0%, transparent 70%)`,
                    animation: 'float1 20s ease-in-out infinite',
                    pointerEvents: 'none',
                    zIndex: 0,
                }}
            />
            <div
                style={{
                    position: 'fixed',
                    bottom: '-20%',
                    right: '-10%',
                    width: '500px',
                    height: '500px',
                    background: `radial-gradient(circle, ${T.purple}10 0%, transparent 70%)`,
                    animation: 'float2 25s ease-in-out infinite',
                    pointerEvents: 'none',
                    zIndex: 0,
                }}
            />

            {/* Noise texture */}
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
                    maxWidth: '800px',
                    margin: '0 auto',
                    padding: '100px 24px 60px',
                    textAlign: 'center',
                }}
            >
                {/* Alpha badge */}
                <div
                    style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '8px',
                        background: T.purpleBg,
                        border: '1px solid rgba(139,92,246,0.25)',
                        borderRadius: '100px',
                        padding: '8px 20px',
                        marginBottom: '32px',
                        fontSize: '13px',
                        fontWeight: 600,
                        color: T.purple,
                    }}
                >
                    <Lock className="w-3.5 h-3.5" />
                    Design Partner Program — Private Alpha
                </div>

                <h1
                    style={{
                        fontSize: 'clamp(36px, 6vw, 56px)',
                        fontWeight: 800,
                        color: T.heading,
                        lineHeight: 1.05,
                        margin: '0 0 20px',
                        letterSpacing: '-0.03em',
                    }}
                >
                    Be First to<br />
                    <span
                        style={{
                            background: `linear-gradient(135deg, ${T.accent}, ${T.purple})`,
                            WebkitBackgroundClip: 'text',
                            WebkitTextFillColor: 'transparent',
                            backgroundClip: 'text',
                        }}
                    >
                        Solve FSMA 204
                    </span>
                </h1>

                <p
                    style={{
                        fontSize: '18px',
                        color: T.textMuted,
                        maxWidth: '560px',
                        margin: '0 auto 16px',
                        lineHeight: 1.6,
                    }}
                >
                    RegEngine is building the compliance infrastructure for food safety traceability.
                    We&apos;re hand-selecting our first 25 design partners.
                </p>

                {/* Urgency strip */}
                <div
                    style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '8px',
                        background: 'rgba(245,158,11,0.08)',
                        border: '1px solid rgba(245,158,11,0.2)',
                        borderRadius: '8px',
                        padding: '10px 20px',
                        fontSize: '14px',
                        color: 'var(--re-warning)',
                        fontWeight: 500,
                        marginBottom: '48px',
                    }}
                >
                    <AlertTriangle className="w-4 h-4" />
                    Only {spotCount} spots remaining in the Alpha cohort
                </div>

                {/* ─── SIGNUP FORM ─── */}
                {!submitted ? (
                    <form
                        ref={formRef}
                        onSubmit={handleSubmit}
                        id="alpha-signup-form"
                        style={{
                            maxWidth: '480px',
                            margin: '0 auto',
                            background: T.surface,
                            border: `1px solid ${T.border}`,
                            borderRadius: '16px',
                            padding: '32px',
                            backdropFilter: 'blur(20px)',
                        }}
                    >
                        <h2
                            style={{
                                fontSize: '20px',
                                fontWeight: 700,
                                color: T.heading,
                                marginBottom: '4px',
                            }}
                        >
                            Request Early Access
                        </h2>
                        <p style={{ fontSize: '14px', color: T.textDim, marginBottom: '24px' }}>
                            We review every application personally.
                        </p>

                        <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                            <div>
                                <label htmlFor="alpha-email" className="text-xs font-semibold text-re-text-muted uppercase tracking-wide block mb-1.5">
                                    Work Email *
                                </label>
                                <div style={{ position: 'relative' }}>
                                    <Mail style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', width: 16, height: 16, color: T.textDim }} />
                                    <input
                                        id="alpha-email"
                                        type="email"
                                        required
                                        placeholder="you@company.com"
                                        value={email}
                                        onChange={(e) => setEmail(e.target.value)}
                                        style={{
                                            width: '100%',
                                            padding: '12px 14px 12px 40px',
                                            background: 'rgba(255,255,255,0.03)',
                                            border: `1px solid ${T.border}`,
                                            borderRadius: '8px',
                                            color: T.heading,
                                            fontSize: '14px',
                                            fontFamily: T.fontSans,
                                            outline: 'none',
                                            transition: 'border-color 0.2s',
                                        }}
                                        onFocus={(e) => e.target.style.borderColor = T.accent}
                                        onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.06)'}
                                    />
                                </div>
                            </div>

                            <div>
                                <label htmlFor="alpha-company" className="text-xs font-semibold text-re-text-muted uppercase tracking-wide block mb-1.5">
                                    Company Name
                                </label>
                                <input
                                    id="alpha-company"
                                    type="text"
                                    placeholder="Acme Foods Inc."
                                    value={company}
                                    onChange={(e) => setCompany(e.target.value)}
                                    style={{
                                        width: '100%',
                                        padding: '12px 14px',
                                        background: 'rgba(255,255,255,0.03)',
                                        border: `1px solid ${T.border}`,
                                        borderRadius: '8px',
                                        color: T.heading,
                                        fontSize: '14px',
                                        fontFamily: T.fontSans,
                                        outline: 'none',
                                        transition: 'border-color 0.2s',
                                    }}
                                    onFocus={(e) => e.target.style.borderColor = T.accent}
                                    onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.06)'}
                                />
                            </div>

                            <div>
                                <label htmlFor="alpha-role" className="text-xs font-semibold text-re-text-muted uppercase tracking-wide block mb-1.5">
                                    Your Role
                                </label>
                                <select
                                    id="alpha-role"
                                    value={role}
                                    onChange={(e) => setRole(e.target.value)}
                                    style={{
                                        width: '100%',
                                        padding: '12px 14px',
                                        background: 'rgba(255,255,255,0.03)',
                                        border: `1px solid ${T.border}`,
                                        borderRadius: '8px',
                                        color: role ? T.heading : T.textDim,
                                        fontSize: '14px',
                                        fontFamily: T.fontSans,
                                        outline: 'none',
                                        appearance: 'none',
                                        transition: 'border-color 0.2s',
                                        cursor: 'pointer',
                                    }}
                                    onFocus={(e) => e.target.style.borderColor = T.accent}
                                    onBlur={(e) => e.target.style.borderColor = 'rgba(255,255,255,0.06)'}
                                >
                                    <option value="" disabled>Select your role...</option>
                                    <option value="compliance">VP / Director of Compliance</option>
                                    <option value="quality">Quality Assurance Manager</option>
                                    <option value="supply-chain">Supply Chain Director</option>
                                    <option value="engineering">Engineering / IT Lead</option>
                                    <option value="operations">Operations Manager</option>
                                    <option value="founder">Founder / CEO</option>
                                    <option value="other">Other</option>
                                </select>
                            </div>

                            <button
                                id="alpha-submit-button"
                                type="submit"
                                disabled={isSubmitting || !email}
                                style={{
                                    width: '100%',
                                    padding: '14px',
                                    marginTop: '8px',
                                    background: isSubmitting
                                        ? T.accentHover
                                        : `linear-gradient(135deg, ${T.accent}, ${T.purple})`,
                                    color: '#fff',
                                    border: 'none',
                                    borderRadius: '10px',
                                    fontSize: '15px',
                                    fontWeight: 700,
                                    fontFamily: T.fontSans,
                                    cursor: isSubmitting ? 'wait' : 'pointer',
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    gap: '8px',
                                    transition: 'all 0.3s',
                                    opacity: !email ? 0.5 : 1,
                                }}
                            >
                                {isSubmitting ? (
                                    <>
                                        <div style={{
                                            width: 18, height: 18,
                                            border: '2px solid rgba(255,255,255,0.3)',
                                            borderTopColor: '#fff',
                                            borderRadius: '50%',
                                            animation: 'spin 0.6s linear infinite',
                                        }} />
                                        Submitting...
                                    </>
                                ) : (
                                    <>
                                        Request Alpha Access
                                        <ArrowRight className="w-4 h-4" />
                                    </>
                                )}
                            </button>
                        </div>

                        {error && (
                            <p style={{ fontSize: '13px', color: 'var(--re-danger)', marginTop: '12px', textAlign: 'center' }}>
                                {error}
                            </p>
                        )}
                        <p style={{ fontSize: '11px', color: T.textDim, marginTop: '16px', lineHeight: 1.5 }}>
                            No spam. We&apos;ll reach out within 48 hours if you&apos;re a fit.
                            <br />
                            By signing up you agree to our{' '}
                            <Link href="/terms" style={{ color: T.textMuted, textDecoration: 'underline' }}>Terms</Link>
                            {' '}and{' '}
                            <Link href="/privacy" style={{ color: T.textMuted, textDecoration: 'underline' }}>Privacy Policy</Link>.
                        </p>
                    </form>
                ) : (
                    <div
                        id="alpha-success-message"
                        style={{
                            maxWidth: '480px',
                            margin: '0 auto',
                            background: T.surface,
                            border: `1px solid rgba(16,185,129,0.25)`,
                            borderRadius: '16px',
                            padding: '40px 32px',
                            textAlign: 'center',
                            animation: 'fadeIn 0.5s ease-out',
                        }}
                    >
                        <div
                            style={{
                                width: '64px',
                                height: '64px',
                                borderRadius: '50%',
                                background: T.accentBg,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                margin: '0 auto 20px',
                            }}
                        >
                            <CheckCircle2 style={{ width: 32, height: 32, color: T.accent }} />
                        </div>
                        <h2 style={{ fontSize: '22px', fontWeight: 700, color: T.heading, marginBottom: '8px' }}>
                            You&apos;re on the List!
                        </h2>
                        <p style={{ fontSize: '15px', color: T.textMuted, lineHeight: 1.6, marginBottom: '24px' }}>
                            We&apos;ll review your application and reach out to <strong className="text-re-text-primary">{email}</strong> within 48 hours.
                        </p>
                        <div
                            style={{
                                background: 'rgba(255,255,255,0.02)',
                                border: `1px solid ${T.border}`,
                                borderRadius: '10px',
                                padding: '16px',
                                fontSize: '13px',
                                color: T.textMuted,
                                lineHeight: 1.6,
                            }}
                        >
                            <strong className="text-re-text-secondary">While you wait:</strong> Check the
                            {' '}<Link href="/ftl-checker" style={{ color: T.accent, textDecoration: 'none' }}>FTL Checker</Link>{' '}
                            to see if your products are on the FDA&apos;s traceability list, or explore our
                            {' '}<Link href="/docs" style={{ color: T.accent, textDecoration: 'none' }}>API documentation</Link>.
                        </div>
                    </div>
                )}
            </section>

            {/* ─── WHAT ALPHA PARTNERS GET ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '1100px',
                    margin: '0 auto',
                    padding: '40px 24px 80px',
                }}
            >
                <h2
                    style={{
                        fontSize: 'clamp(24px, 4vw, 32px)',
                        fontWeight: 700,
                        color: T.heading,
                        textAlign: 'center',
                        marginBottom: '12px',
                    }}
                >
                    What Alpha Partners Get
                </h2>
                <p
                    style={{
                        fontSize: '16px',
                        color: T.textMuted,
                        textAlign: 'center',
                        maxWidth: '500px',
                        margin: '0 auto 48px',
                    }}
                >
                    This is a working design partner program focused on production readiness.
                </p>

                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
                        gap: '16px',
                    }}
                >
                    {ALPHA_PERKS.map((perk, i) => {
                        const Icon = perk.icon;
                        return (
                            <div
                                key={i}
                                style={{
                                    background: T.surface,
                                    border: `1px solid ${T.border}`,
                                    borderRadius: '12px',
                                    padding: '24px',
                                    transition: 'all 0.2s',
                                }}
                                onMouseEnter={(e) => {
                                    (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(16,185,129,0.2)';
                                    (e.currentTarget as HTMLDivElement).style.background = T.surfaceHover;
                                }}
                                onMouseLeave={(e) => {
                                    (e.currentTarget as HTMLDivElement).style.borderColor = 'rgba(255,255,255,0.06)';
                                    (e.currentTarget as HTMLDivElement).style.background = T.surface;
                                }}
                            >
                                <div
                                    style={{
                                        width: '40px',
                                        height: '40px',
                                        borderRadius: '10px',
                                        background: T.accentBg,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        marginBottom: '16px',
                                    }}
                                >
                                    <Icon className="w-5 h-5 text-re-brand" />
                                </div>
                                <h3 style={{ fontSize: '16px', fontWeight: 600, color: T.heading, marginBottom: '8px' }}>
                                    {perk.title}
                                </h3>
                                <p style={{ fontSize: '14px', color: T.textMuted, lineHeight: 1.6 }}>
                                    {perk.description}
                                </p>
                            </div>
                        );
                    })}
                </div>
            </section>

            {/* ─── TIMELINE ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    background: T.surface,
                    borderTop: `1px solid ${T.border}`,
                    borderBottom: `1px solid ${T.border}`,
                    padding: '80px 24px',
                }}
            >
                <div className="max-w-[700px] mx-auto">
                    <h2
                        style={{
                            fontSize: '28px',
                            fontWeight: 700,
                            color: T.heading,
                            textAlign: 'center',
                            marginBottom: '48px',
                        }}
                    >
                        Program Milestones
                    </h2>

                    <div style={{ display: 'flex', flexDirection: 'column', gap: '0' }}>
                        {TIMELINE.map((item, i) => (
                            <div
                                key={i}
                                style={{
                                    display: 'flex',
                                    gap: '20px',
                                    alignItems: 'flex-start',
                                    position: 'relative',
                                }}
                            >
                                {/* Timeline line and dot */}
                                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                                    <div
                                        style={{
                                            width: item.status === 'current' ? '16px' : '12px',
                                            height: item.status === 'current' ? '16px' : '12px',
                                            borderRadius: '50%',
                                            background: item.status === 'current'
                                                ? T.accent
                                                : item.status === 'deadline'
                                                    ? 'var(--re-danger)'
                                                    : 'rgba(255,255,255,0.1)',
                                            border: item.status === 'current'
                                                ? `3px solid ${T.accentBg}`
                                                : 'none',
                                            boxShadow: item.status === 'current'
                                                ? `0 0 20px ${T.accent}40`
                                                : 'none',
                                            flexShrink: 0,
                                            position: 'relative',
                                            zIndex: 3,
                                        }}
                                    />
                                    {i < TIMELINE.length - 1 && (
                                        <div
                                            style={{
                                                width: '2px',
                                                height: '48px',
                                                background: `linear-gradient(to bottom, ${T.border}, transparent)`,
                                            }}
                                        />
                                    )}
                                </div>

                                {/* Content */}
                                <div style={{ paddingBottom: i < TIMELINE.length - 1 ? '32px' : '0', paddingTop: '0' }}>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                                        <span
                                            style={{
                                                fontSize: '16px',
                                                fontWeight: 600,
                                                color: item.status === 'current' ? T.accent
                                                    : item.status === 'deadline' ? 'var(--re-danger)'
                                                        : T.heading,
                                            }}
                                        >
                                            {item.phase}
                                        </span>
                                        {item.status === 'current' && (
                                            <span
                                                style={{
                                                    fontSize: '11px',
                                                    fontWeight: 700,
                                                    color: T.accent,
                                                    background: T.accentBg,
                                                    padding: '2px 8px',
                                                    borderRadius: '100px',
                                                    textTransform: 'uppercase',
                                                    letterSpacing: '0.05em',
                                                }}
                                            >
                                                You are here
                                            </span>
                                        )}
                                    </div>
                                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                                        <span style={{ fontSize: '13px', color: T.textMuted, fontFamily: T.fontMono }}>{item.date}</span>
                                        <span className="text-[13px] text-re-text-disabled">·</span>
                                        <span className="text-[13px] text-re-text-disabled">{item.detail}</span>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ─── SOCIAL PROOF ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    maxWidth: '800px',
                    margin: '0 auto',
                    padding: '80px 24px',
                    textAlign: 'center',
                }}
            >
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(3, 1fr)',
                        gap: '24px',
                    }}
                >
                    {[
                        { value: '430+', label: 'CTE Records Verified' },
                        { value: '<10s', label: 'Trace Response Time' },
                        { value: '23', label: 'FDA Food Categories' },
                    ].map((stat, i) => (
                        <div key={i}>
                            <div
                                style={{
                                    fontSize: 'clamp(28px, 4vw, 40px)',
                                    fontWeight: 700,
                                    color: T.accent,
                                    fontFamily: T.fontMono,
                                    marginBottom: '4px',
                                }}
                            >
                                {stat.value}
                            </div>
                            <div className="text-[13px] text-re-text-disabled">{stat.label}</div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ─── BOTTOM CTA ─── */}
            <section
                style={{
                    position: 'relative',
                    zIndex: 2,
                    padding: '80px 24px',
                    textAlign: 'center',
                    borderTop: `1px solid ${T.border}`,
                }}
            >
                <div style={{ maxWidth: '560px', margin: '0 auto' }}>
                    <Clock style={{ width: 32, height: 32, color: T.accent, margin: '0 auto 20px' }} />
                    <h2 style={{ fontSize: '28px', fontWeight: 700, color: T.heading, marginBottom: '12px' }}>
                        Don&apos;t Wait for the Deadline
                    </h2>
                    <p style={{ fontSize: '16px', color: T.textMuted, lineHeight: 1.6, marginBottom: '32px' }}>
                        FSMA 204 enforcement starts July 2028. Companies that start now will be ready.
                        Those that wait will be scrambling.
                    </p>
                    {!submitted && (
                        <button
                            onClick={() => {
                                formRef.current?.scrollIntoView({ behavior: 'smooth' });
                                document.getElementById('alpha-email')?.focus();
                            }}
                            style={{
                                padding: '14px 32px',
                                background: `linear-gradient(135deg, ${T.accent}, ${T.purple})`,
                                color: '#fff',
                                border: 'none',
                                borderRadius: '10px',
                                fontSize: '15px',
                                fontWeight: 700,
                                fontFamily: T.fontSans,
                                cursor: 'pointer',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '8px',
                                transition: 'transform 0.2s',
                            }}
                            onMouseEnter={(e) => (e.currentTarget.style.transform = 'translateY(-2px)')}
                            onMouseLeave={(e) => (e.currentTarget.style.transform = 'translateY(0)')}
                        >
                            Request Alpha Access
                            <ChevronRight className="w-4 h-4" />
                        </button>
                    )}
                </div>
            </section>

            {/* ─── FOOTER ─── */}
            <footer
                style={{
                    position: 'relative',
                    zIndex: 2,
                    borderTop: `1px solid ${T.border}`,
                    padding: '24px',
                    textAlign: 'center',
                    fontSize: '12px',
                    color: T.textDim,
                }}
            >
                © {new Date().getFullYear()} RegEngine, Inc. · FSMA 204 Compliance Platform
                <br />
                <Link href="/privacy" style={{ color: T.textMuted, textDecoration: 'none', marginRight: '16px' }}>Privacy</Link>
                <Link href="/terms" style={{ color: T.textMuted, textDecoration: 'none', marginRight: '16px' }}>Terms</Link>
                <Link href="/security" style={{ color: T.textMuted, textDecoration: 'none' }}>Security</Link>
            </footer>

            <style>{`
                * { box-sizing: border-box; margin: 0; }

                @keyframes float1 {
                    0%, 100% { transform: translate(0, 0); }
                    33% { transform: translate(50px, -30px); }
                    66% { transform: translate(-20px, 20px); }
                }

                @keyframes float2 {
                    0%, 100% { transform: translate(0, 0); }
                    33% { transform: translate(-40px, 20px); }
                    66% { transform: translate(30px, -40px); }
                }

                @keyframes spin {
                    to { transform: rotate(360deg); }
                }

                @keyframes fadeIn {
                    from { opacity: 0; transform: translateY(10px); }
                    to { opacity: 1; transform: translateY(0); }
                }

                select option {
                    background: #1a1a2e;
                    color: #e2e8f0;
                }

                input::placeholder, select::placeholder {
                    color: #475569;
                }
            `}</style>
        </div>
    );
}
