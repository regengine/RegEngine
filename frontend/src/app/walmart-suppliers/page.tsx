'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import Link from 'next/link';
import FSMAChecklist from '@/components/fsma-checklist';

/* ─────────────────────────────────────────────────────────────
   DESIGN TOKENS
   ───────────────────────────────────────────────────────────── */
const T = {
    bg: '#06090f',
    surface: 'rgba(255,255,255,0.02)',
    surfaceHover: 'rgba(255,255,255,0.05)',
    border: 'rgba(255,255,255,0.06)',
    borderHover: 'rgba(255,255,255,0.12)',
    text: '#c8d1dc',
    textMuted: '#64748b',
    textDim: '#475569',
    heading: '#e2e8f0',
    accent: '#10b981',
    accentHover: '#059669',
    accentGlow: 'rgba(16,185,129,0.15)',
    warning: '#f59e0b',
    warningBg: 'rgba(245,158,11,0.08)',
    warningBorder: 'rgba(245,158,11,0.15)',
    danger: '#ef4444',
    dangerBg: 'rgba(239,68,68,0.08)',
    blue: '#3b82f6',
    blueBg: 'rgba(59,130,246,0.08)',
};

/* ─────────────────────────────────────────────────────────────
   SCROLL REVEAL HOOK
   ───────────────────────────────────────────────────────────── */
function useScrollReveal(threshold = 0.15) {
    const ref = useRef<HTMLDivElement>(null);
    const [visible, setVisible] = useState(false);

    useEffect(() => {
        const el = ref.current;
        if (!el) return;
        const obs = new IntersectionObserver(
            ([entry]) => { if (entry.isIntersecting) { setVisible(true); obs.disconnect(); } },
            { threshold }
        );
        obs.observe(el);
        return () => obs.disconnect();
    }, [threshold]);

    return { ref, visible };
}

/* ─────────────────────────────────────────────────────────────
   PRICING DATA
   ───────────────────────────────────────────────────────────── */
const PRICING_TIERS = [
    {
        revenue: 'Under $50M',
        price: '$999',
        period: '/mo',
        features: ['Up to 10,000 CTEs/month', '3 locations', 'Email support', 'FDA 204 export'],
    },
    {
        revenue: '$50M – $200M',
        price: '$1,999',
        period: '/mo',
        features: ['Up to 100,000 CTEs/month', '10 locations', 'Priority support', 'Mock recall drills', 'Integration support'],
        highlighted: true,
    },
    {
        revenue: 'Over $200M',
        price: 'Custom',
        period: '',
        features: ['Unlimited CTEs', 'Unlimited locations', 'Dedicated support', 'On-premise option', 'Custom SLA'],
    },
];

/* ─────────────────────────────────────────────────────────────
   TRACE ANIMATION NODES
   ───────────────────────────────────────────────────────────── */
const TRACE_NODES = [
    { label: 'Harvest', sublabel: 'Farm • Salinas, CA', icon: '🌱', kde: 'TLC-2026-0412' },
    { label: 'Cool & Pack', sublabel: 'Cooler • Salinas, CA', icon: '❄️', kde: 'TLC-2026-0412-P' },
    { label: 'Ship', sublabel: 'Truck → DC', icon: '🚛', kde: 'BOL-88421' },
    { label: 'Receive', sublabel: 'Walmart DC #7218', icon: '📦', kde: 'RCV-7218-0412' },
    { label: 'Store', sublabel: 'Walmart #4521', icon: '🏪', kde: 'STR-4521-0412' },
];

/* ═════════════════════════════════════════════════════════════
   MAIN COMPONENT
   ═════════════════════════════════════════════════════════════ */
export default function WalmartSuppliersPage() {
    const [email, setEmail] = useState('');
    const [companyName, setCompanyName] = useState('');
    const [submitted, setSubmitted] = useState(false);

    // Risk calculator state
    const [annualRevenue, setAnnualRevenue] = useState(25);
    const [walmartPercent, setWalmartPercent] = useState(30);

    // Trace animation
    const [traceStep, setTraceStep] = useState(-1);
    const [traceComplete, setTraceComplete] = useState(false);
    const [traceStarted, setTraceStarted] = useState(false);
    const traceRef = useRef<HTMLDivElement>(null);

    // Scroll reveals
    const timeline = useScrollReveal();
    const trace = useScrollReveal();
    const comparison = useScrollReveal();
    const riskCalc = useScrollReveal();
    const pricing = useScrollReveal();
    const founder = useScrollReveal();

    // Animated counter
    const [daysCount, setDaysCount] = useState(0);
    const heroRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        // Calculate days until July 20, 2028
        const target = new Date('2028-07-20');
        const now = new Date();
        const days = Math.ceil((target.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
        // Animate count up
        let current = 0;
        const step = Math.ceil(days / 60);
        const interval = setInterval(() => {
            current += step;
            if (current >= days) { current = days; clearInterval(interval); }
            setDaysCount(current);
        }, 20);
        return () => clearInterval(interval);
    }, []);

    // Trace animation auto-play when visible
    const startTrace = useCallback(() => {
        if (traceStarted) return;
        setTraceStarted(true);
        setTraceStep(-1);
        setTraceComplete(false);

        TRACE_NODES.forEach((_, i) => {
            setTimeout(() => {
                setTraceStep(i);
                if (i === TRACE_NODES.length - 1) {
                    setTimeout(() => setTraceComplete(true), 600);
                }
            }, (i + 1) * 700);
        });
    }, [traceStarted]);

    useEffect(() => {
        if (trace.visible) startTrace();
    }, [trace.visible, startTrace]);

    const handleAssessment = (e: React.FormEvent) => {
        e.preventDefault();
        if (email && companyName) {
            localStorage.setItem('walmart_supplier_lead', JSON.stringify({
                email, companyName, date: new Date().toISOString()
            }));
            setSubmitted(true);
        }
    };

    const atRisk = ((annualRevenue * 1_000_000) * (walmartPercent / 100));
    const monthlyRisk = Math.round(atRisk / 12);

    return (
        <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: "'Instrument Sans', -apple-system, sans-serif" }}>
            {/* Noise overlay */}
            <div style={{
                position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 1, opacity: 0.015,
                backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
            }} />

            {/* ─── URGENCY BANNER ─── */}
            <div style={{
                background: `linear-gradient(90deg, ${T.dangerBg}, ${T.warningBg}, ${T.dangerBg})`,
                borderBottom: `1px solid ${T.warningBorder}`,
                padding: '10px 24px',
                position: 'relative', zIndex: 10,
            }}>
                <div style={{
                    maxWidth: 1120, margin: '0 auto',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10,
                }}>
                    <span style={{ fontSize: 16 }}>⚠️</span>
                    <span style={{ fontSize: 14, color: T.warning, fontWeight: 500 }}>
                        Walmart is evaluating suppliers <strong>now</strong>. Their internal deadline is earlier than FDA's July 2028.
                    </span>
                </div>
            </div>

            {/* ─── HERO ─── */}
            <section ref={heroRef} style={{
                position: 'relative', zIndex: 2,
                maxWidth: 1120, margin: '0 auto', padding: '80px 24px 40px',
                textAlign: 'center',
            }}>
                {/* Glow */}
                <div style={{
                    position: 'absolute', top: -80, left: '50%', transform: 'translateX(-50%)',
                    width: 800, height: 500,
                    background: `radial-gradient(ellipse, ${T.accentGlow} 0%, transparent 70%)`,
                    pointerEvents: 'none',
                }} />

                <div style={{
                    display: 'inline-flex', alignItems: 'center', gap: 8,
                    background: T.warningBg, border: `1px solid ${T.warningBorder}`,
                    borderRadius: 9999, padding: '6px 16px', marginBottom: 24, fontSize: 13, color: T.warning,
                }}>
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: T.warning, animation: 'pulse-dot 2s infinite' }} />
                    Walmart Supplier Compliance
                </div>

                <h1 style={{
                    fontSize: 'clamp(36px, 5.5vw, 56px)', fontWeight: 700,
                    color: T.heading, lineHeight: 1.08, margin: '0 0 20px',
                    letterSpacing: '-0.02em',
                }}>
                    Walmart-Ready<br />
                    <span style={{
                        background: `linear-gradient(135deg, ${T.accent}, #34d399)`,
                        WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
                    }}>In 30 Days or Less</span>
                </h1>

                <p style={{
                    fontSize: 18, color: T.textMuted,
                    maxWidth: 540, margin: '0 auto 16px', lineHeight: 1.7,
                }}>
                    Meet Walmart's internal traceability requirements before you lose your spot on the shelf.
                    API-first. No portal logins. No spreadsheets.
                </p>

                {/* Countdown */}
                <div style={{
                    display: 'inline-flex', alignItems: 'baseline', gap: 8,
                    background: T.surface, border: `1px solid ${T.border}`,
                    borderRadius: 12, padding: '12px 24px', marginBottom: 32,
                }}>
                    <span style={{
                        fontSize: 32, fontWeight: 700, fontFamily: "'JetBrains Mono', monospace",
                        color: daysCount > 600 ? T.warning : T.danger,
                    }}>
                        {daysCount.toLocaleString()}
                    </span>
                    <span style={{ fontSize: 14, color: T.textMuted }}>days until FDA's July 2028 deadline</span>
                </div>

                <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                    <Link href="#assessment">
                        <button style={{
                            background: `linear-gradient(135deg, ${T.accent}, ${T.accentHover})`,
                            color: '#000', fontWeight: 600, padding: '14px 28px', fontSize: 15,
                            border: 'none', borderRadius: 10, cursor: 'pointer',
                            boxShadow: `0 0 30px ${T.accentGlow}`,
                            transition: 'all 0.2s',
                        }}>
                            Get Free Assessment →
                        </button>
                    </Link>
                    <Link href="/ftl-checker">
                        <button style={{
                            background: 'transparent', color: T.text,
                            border: `1px solid ${T.border}`, padding: '14px 28px', fontSize: 15,
                            borderRadius: 10, cursor: 'pointer', transition: 'all 0.2s',
                        }}>
                            Try FTL Checker Free
                        </button>
                    </Link>
                </div>

                {/* Founder badge */}
                <div style={{
                    marginTop: 24, display: 'inline-flex', alignItems: 'center', gap: 10,
                    fontSize: 13, color: T.textDim,
                }}>
                    <div style={{
                        width: 28, height: 28, borderRadius: '50%',
                        background: `linear-gradient(135deg, ${T.accent}30, ${T.blue}30)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 14,
                    }}>CS</div>
                    <span>Founder-led early access — direct support, fast iteration</span>
                </div>
            </section>

            {/* ═══════════════════════════════════════════════════════════
               1. VISUAL DEADLINE TIMELINE
               ═══════════════════════════════════════════════════════════ */}
            <section ref={timeline.ref} style={{
                position: 'relative', zIndex: 2,
                maxWidth: 900, margin: '0 auto', padding: '60px 24px 80px',
                opacity: timeline.visible ? 1 : 0,
                transform: timeline.visible ? 'translateY(0)' : 'translateY(30px)',
                transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
            }}>
                <div style={{ textAlign: 'center', marginBottom: 48 }}>
                    <p style={{ fontSize: 12, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8, fontWeight: 600 }}>
                        Compliance Timeline
                    </p>
                    <h2 style={{ fontSize: 'clamp(24px, 4vw, 36px)', fontWeight: 700, color: T.heading, marginBottom: 12 }}>
                        The Clock Is Already Running
                    </h2>
                    <p style={{ fontSize: 15, color: T.textMuted, maxWidth: 500, margin: '0 auto' }}>
                        Walmart's internal deadline comes <strong style={{ color: T.warning }}>before</strong> the FDA mandate.
                        Suppliers who wait will be too late.
                    </p>
                </div>

                {/* Timeline visualization */}
                <div style={{
                    background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                    padding: '40px 32px',
                }}>
                    {/* Timeline bar */}
                    <div style={{ position: 'relative', height: 4, background: 'rgba(255,255,255,0.06)', borderRadius: 4, marginBottom: 60, marginTop: 20 }}>
                        {/* Progress fill */}
                        <div style={{
                            position: 'absolute', left: 0, top: 0, height: '100%', borderRadius: 4,
                            width: timeline.visible ? '12%' : '0%',
                            background: `linear-gradient(90deg, ${T.accent}, ${T.warning})`,
                            transition: 'width 1.5s cubic-bezier(0.16, 1, 0.3, 1) 0.5s',
                        }} />

                        {/* "You are here" marker */}
                        <div style={{
                            position: 'absolute', left: '12%', top: '50%', transform: 'translate(-50%, -50%)',
                            width: 16, height: 16, borderRadius: '50%',
                            background: T.accent,
                            boxShadow: `0 0 20px ${T.accent}80`,
                            animation: timeline.visible ? 'pulse-ring 2s infinite' : 'none',
                            zIndex: 2,
                        }}>
                            <div style={{
                                position: 'absolute', top: -32, left: '50%', transform: 'translateX(-50%)',
                                fontSize: 11, color: T.accent, fontWeight: 600, whiteSpace: 'nowrap',
                                background: `${T.accent}15`, padding: '3px 10px', borderRadius: 6,
                            }}>
                                TODAY
                            </div>
                        </div>

                        {/* Walmart deadline */}
                        <div style={{
                            position: 'absolute', left: '55%', top: '50%', transform: 'translate(-50%, -50%)',
                            width: 14, height: 14, borderRadius: '50%',
                            background: T.warning, border: `3px solid ${T.bg}`, zIndex: 2,
                        }}>
                            <div style={{
                                position: 'absolute', top: 24, left: '50%', transform: 'translateX(-50%)',
                                textAlign: 'center', whiteSpace: 'nowrap',
                            }}>
                                <p style={{ fontSize: 13, fontWeight: 600, color: T.warning }}>Walmart Internal</p>
                                <p style={{ fontSize: 11, color: T.textDim }}>~Q1 2027 (est.)</p>
                            </div>
                        </div>

                        {/* Danger zone */}
                        <div style={{
                            position: 'absolute', left: '55%', right: '12%', top: -8, height: 20,
                            background: `repeating-linear-gradient(135deg, transparent, transparent 6px, ${T.danger}08 6px, ${T.danger}08 12px)`,
                            borderRadius: 4,
                        }} />

                        {/* FDA deadline */}
                        <div style={{
                            position: 'absolute', left: '88%', top: '50%', transform: 'translate(-50%, -50%)',
                            width: 14, height: 14, borderRadius: '50%',
                            background: T.danger, border: `3px solid ${T.bg}`, zIndex: 2,
                        }}>
                            <div style={{
                                position: 'absolute', top: -40, left: '50%', transform: 'translateX(-50%)',
                                textAlign: 'center', whiteSpace: 'nowrap',
                            }}>
                                <p style={{ fontSize: 13, fontWeight: 600, color: T.danger }}>FDA Mandate</p>
                                <p style={{ fontSize: 11, color: T.textDim }}>July 20, 2028</p>
                            </div>
                        </div>
                    </div>

                    {/* Key insight */}
                    <div style={{
                        display: 'flex', alignItems: 'flex-start', gap: 12,
                        background: T.warningBg, border: `1px solid ${T.warningBorder}`,
                        borderRadius: 10, padding: '14px 18px',
                    }}>
                        <span style={{ fontSize: 18, marginTop: 1 }}>💡</span>
                        <div>
                            <p style={{ fontSize: 14, color: T.heading, fontWeight: 600, marginBottom: 4 }}>
                                Why is Walmart's deadline earlier?
                            </p>
                            <p style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.6 }}>
                                Walmart is requiring suppliers to demonstrate traceability capability as a condition for continued shelf placement — well ahead of the FDA mandate.
                                Suppliers who can't show readiness risk deprioritization during the next category review.
                            </p>
                        </div>
                    </div>
                </div>
            </section>

            {/* ═══════════════════════════════════════════════════════════
               2. ANIMATED SUPPLY CHAIN TRACE DEMO
               ═══════════════════════════════════════════════════════════ */}
            <section ref={trace.ref} style={{
                position: 'relative', zIndex: 2,
                maxWidth: 900, margin: '0 auto', padding: '60px 24px',
                opacity: trace.visible ? 1 : 0,
                transform: trace.visible ? 'translateY(0)' : 'translateY(30px)',
                transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
            }}>
                <div style={{ textAlign: 'center', marginBottom: 48 }}>
                    <p style={{ fontSize: 12, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8, fontWeight: 600 }}>
                        Live Trace Demo
                    </p>
                    <h2 style={{ fontSize: 'clamp(24px, 4vw, 36px)', fontWeight: 700, color: T.heading, marginBottom: 12 }}>
                        5-Second Trace. Farm to Store.
                    </h2>
                    <p style={{ fontSize: 15, color: T.textMuted, maxWidth: 480, margin: '0 auto' }}>
                        Watch a romaine lettuce lot trace across the entire supply chain in real time.
                    </p>
                </div>

                <div ref={traceRef} style={{
                    background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                    padding: '32px 24px', overflow: 'hidden',
                }}>
                    {/* Terminal header */}
                    <div style={{
                        display: 'flex', alignItems: 'center', gap: 8, marginBottom: 24,
                        paddingBottom: 16, borderBottom: `1px solid ${T.border}`,
                    }}>
                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444' }} />
                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#f59e0b' }} />
                        <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#22c55e' }} />
                        <span style={{
                            marginLeft: 12, fontSize: 12, color: T.textDim,
                            fontFamily: "'JetBrains Mono', monospace",
                        }}>
                            regengine trace --lot TLC-2026-0412 --direction forward
                        </span>
                    </div>

                    {/* Trace nodes */}
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
                        {TRACE_NODES.map((node, i) => {
                            const active = i <= traceStep;
                            const current = i === traceStep && !traceComplete;
                            return (
                                <div key={node.label}>
                                    <div style={{
                                        display: 'flex', alignItems: 'center', gap: 16, padding: '14px 16px',
                                        borderRadius: 10,
                                        background: current ? `${T.accent}08` : active ? 'rgba(255,255,255,0.01)' : 'transparent',
                                        border: current ? `1px solid ${T.accent}25` : '1px solid transparent',
                                        opacity: active ? 1 : 0.3,
                                        transform: active ? 'translateX(0)' : 'translateX(-8px)',
                                        transition: 'all 0.5s cubic-bezier(0.16, 1, 0.3, 1)',
                                    }}>
                                        {/* Step indicator */}
                                        <div style={{
                                            width: 36, height: 36, borderRadius: 10,
                                            background: active ? `${T.accent}15` : 'rgba(255,255,255,0.03)',
                                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                                            fontSize: 18, flexShrink: 0,
                                            border: current ? `1px solid ${T.accent}40` : '1px solid transparent',
                                            boxShadow: current ? `0 0 16px ${T.accent}20` : 'none',
                                        }}>
                                            {node.icon}
                                        </div>

                                        {/* Info */}
                                        <div style={{ flex: 1, minWidth: 0 }}>
                                            <p style={{
                                                fontSize: 14, fontWeight: 600,
                                                color: active ? T.heading : T.textDim,
                                                transition: 'color 0.3s',
                                            }}>
                                                {node.label}
                                            </p>
                                            <p style={{ fontSize: 12, color: T.textDim }}>{node.sublabel}</p>
                                        </div>

                                        {/* KDE */}
                                        <div style={{
                                            fontFamily: "'JetBrains Mono', monospace",
                                            fontSize: 11, color: active ? T.accent : T.textDim,
                                            opacity: active ? 1 : 0,
                                            transition: 'all 0.5s',
                                        }}>
                                            {node.kde}
                                        </div>

                                        {/* Status */}
                                        <div style={{
                                            fontSize: 12, fontWeight: 600,
                                            color: active ? T.accent : T.textDim,
                                            opacity: active ? 1 : 0,
                                            transition: 'opacity 0.3s',
                                        }}>
                                            ✓
                                        </div>
                                    </div>

                                    {/* Connector line */}
                                    {i < TRACE_NODES.length - 1 && (
                                        <div style={{
                                            width: 2, height: 16, marginLeft: 33,
                                            background: active ? `${T.accent}40` : 'rgba(255,255,255,0.04)',
                                            transition: 'background 0.5s',
                                        }} />
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {/* Completion banner */}
                    <div style={{
                        marginTop: 20, padding: '14px 18px',
                        background: traceComplete ? `${T.accent}08` : 'transparent',
                        border: `1px solid ${traceComplete ? `${T.accent}20` : 'transparent'}`,
                        borderRadius: 10,
                        opacity: traceComplete ? 1 : 0,
                        transform: traceComplete ? 'translateY(0)' : 'translateY(8px)',
                        transition: 'all 0.6s cubic-bezier(0.16, 1, 0.3, 1)',
                    }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                <span style={{ fontSize: 16 }}>⚡</span>
                                <span style={{ fontSize: 14, fontWeight: 600, color: T.accent }}>
                                    Full trace complete
                                </span>
                            </div>
                            <div style={{
                                fontFamily: "'JetBrains Mono', monospace",
                                fontSize: 13, color: T.heading, fontWeight: 600,
                            }}>
                                3.2 seconds
                            </div>
                        </div>
                        <p style={{ fontSize: 12, color: T.textMuted, marginTop: 6, marginLeft: 26 }}>
                            5 CTEs verified · All KDEs captured · SHA-256 hash chain intact
                        </p>
                    </div>

                    {/* Replay button */}
                    <button
                        onClick={() => {
                            setTraceStarted(false);
                            setTraceStep(-1);
                            setTraceComplete(false);
                            setTimeout(() => startTrace(), 100);
                        }}
                        style={{
                            display: 'block', margin: '20px auto 0', padding: '8px 20px',
                            background: 'transparent', border: `1px solid ${T.border}`,
                            borderRadius: 8, color: T.textMuted, fontSize: 13, cursor: 'pointer',
                            transition: 'all 0.2s',
                        }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = T.borderHover; e.currentTarget.style.color = T.text; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.color = T.textMuted; }}
                    >
                        ↻ Replay trace
                    </button>
                </div>
            </section>

            {/* ═══════════════════════════════════════════════════════════
               3. BEFORE / AFTER COMPARISON
               ═══════════════════════════════════════════════════════════ */}
            <section ref={comparison.ref} style={{
                position: 'relative', zIndex: 2,
                maxWidth: 1000, margin: '0 auto', padding: '60px 24px',
                opacity: comparison.visible ? 1 : 0,
                transform: comparison.visible ? 'translateY(0)' : 'translateY(30px)',
                transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
            }}>
                <div style={{ textAlign: 'center', marginBottom: 48 }}>
                    <p style={{ fontSize: 12, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8, fontWeight: 600 }}>
                        Why Switch?
                    </p>
                    <h2 style={{ fontSize: 'clamp(24px, 4vw, 36px)', fontWeight: 700, color: T.heading }}>
                        Your Current Setup vs. RegEngine
                    </h2>
                </div>

                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))',
                    gap: 20,
                }}>
                    {/* BEFORE */}
                    <div style={{
                        background: T.dangerBg, border: `1px solid rgba(239,68,68,0.12)`,
                        borderRadius: 16, padding: '28px 24px',
                    }}>
                        <div style={{
                            display: 'inline-flex', alignItems: 'center', gap: 8,
                            background: 'rgba(239,68,68,0.1)', borderRadius: 8, padding: '6px 14px',
                            marginBottom: 24, fontSize: 12, fontWeight: 600, color: T.danger,
                            textTransform: 'uppercase', letterSpacing: '0.05em',
                        }}>
                            ✗ Without RegEngine
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                            {[
                                { label: 'Record keeping', value: 'Excel spreadsheets', bad: true },
                                { label: 'Trace response time', value: '3–5 business days', bad: true },
                                { label: 'Data format', value: 'PDFs, emails, paper', bad: true },
                                { label: 'Supply chain visibility', value: 'One hop upstream', bad: true },
                                { label: 'FDA audit readiness', value: 'Hope for the best', bad: true },
                                { label: 'Team workflow', value: 'Manual portal logins', bad: true },
                            ].map((item, i) => (
                                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 12, borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                                    <span style={{ fontSize: 14, color: T.textMuted }}>{item.label}</span>
                                    <span style={{ fontSize: 14, color: T.danger, fontWeight: 500 }}>{item.value}</span>
                                </div>
                            ))}
                        </div>
                    </div>

                    {/* AFTER */}
                    <div style={{
                        background: `${T.accent}05`, border: `1px solid ${T.accent}18`,
                        borderRadius: 16, padding: '28px 24px',
                        boxShadow: `0 0 40px ${T.accent}08`,
                    }}>
                        <div style={{
                            display: 'inline-flex', alignItems: 'center', gap: 8,
                            background: `${T.accent}12`, borderRadius: 8, padding: '6px 14px',
                            marginBottom: 24, fontSize: 12, fontWeight: 600, color: T.accent,
                            textTransform: 'uppercase', letterSpacing: '0.05em',
                        }}>
                            ✓ With RegEngine
                        </div>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                            {[
                                { label: 'Record keeping', value: 'Automated API capture' },
                                { label: 'Trace response time', value: '< 5 seconds' },
                                { label: 'Data format', value: 'FDA sortable spreadsheet' },
                                { label: 'Supply chain visibility', value: 'Full chain, farm to store' },
                                { label: 'FDA audit readiness', value: 'Click. Export. Done.' },
                                { label: 'Team workflow', value: 'Zero portal logins' },
                            ].map((item, i) => (
                                <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 12, borderBottom: `1px solid ${T.accent}08` }}>
                                    <span style={{ fontSize: 14, color: T.textMuted }}>{item.label}</span>
                                    <span style={{ fontSize: 14, color: T.accent, fontWeight: 600 }}>{item.value}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* ═══════════════════════════════════════════════════════════
               4. RISK CALCULATOR
               ═══════════════════════════════════════════════════════════ */}
            <section ref={riskCalc.ref} style={{
                position: 'relative', zIndex: 2,
                maxWidth: 700, margin: '0 auto', padding: '60px 24px',
                opacity: riskCalc.visible ? 1 : 0,
                transform: riskCalc.visible ? 'translateY(0)' : 'translateY(30px)',
                transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
            }}>
                <div style={{ textAlign: 'center', marginBottom: 40 }}>
                    <p style={{ fontSize: 12, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8, fontWeight: 600 }}>
                        Risk Calculator
                    </p>
                    <h2 style={{ fontSize: 'clamp(24px, 4vw, 36px)', fontWeight: 700, color: T.heading, marginBottom: 12 }}>
                        What Does Losing Walmart Cost You?
                    </h2>
                    <p style={{ fontSize: 15, color: T.textMuted }}>
                        Drag the sliders. See the math. Then look at the pricing below.
                    </p>
                </div>

                <div style={{
                    background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                    padding: '32px 28px',
                }}>
                    {/* Revenue slider */}
                    <div style={{ marginBottom: 28 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                            <label style={{ fontSize: 14, color: T.text, fontWeight: 500 }}>Annual Revenue</label>
                            <span style={{ fontSize: 14, fontWeight: 600, color: T.heading, fontFamily: "'JetBrains Mono', monospace" }}>
                                ${annualRevenue}M
                            </span>
                        </div>
                        <input
                            type="range" min={5} max={500} step={5}
                            value={annualRevenue}
                            onChange={e => setAnnualRevenue(Number(e.target.value))}
                            style={{ width: '100%', accentColor: T.accent }}
                        />
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: T.textDim, marginTop: 4 }}>
                            <span>$5M</span><span>$500M</span>
                        </div>
                    </div>

                    {/* Walmart % slider */}
                    <div style={{ marginBottom: 32 }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                            <label style={{ fontSize: 14, color: T.text, fontWeight: 500 }}>% Revenue from Walmart</label>
                            <span style={{ fontSize: 14, fontWeight: 600, color: T.heading, fontFamily: "'JetBrains Mono', monospace" }}>
                                {walmartPercent}%
                            </span>
                        </div>
                        <input
                            type="range" min={5} max={80} step={5}
                            value={walmartPercent}
                            onChange={e => setWalmartPercent(Number(e.target.value))}
                            style={{ width: '100%', accentColor: T.warning }}
                        />
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: T.textDim, marginTop: 4 }}>
                            <span>5%</span><span>80%</span>
                        </div>
                    </div>

                    {/* Results */}
                    <div style={{
                        display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16,
                        marginBottom: 20,
                    }}>
                        <div style={{
                            background: T.dangerBg, border: `1px solid rgba(239,68,68,0.15)`,
                            borderRadius: 12, padding: '20px 18px', textAlign: 'center',
                        }}>
                            <p style={{ fontSize: 12, color: T.danger, marginBottom: 6, fontWeight: 500 }}>Annual Revenue at Risk</p>
                            <p style={{
                                fontSize: 28, fontWeight: 700, color: T.danger,
                                fontFamily: "'JetBrains Mono', monospace",
                            }}>
                                ${(atRisk / 1_000_000).toFixed(1)}M
                            </p>
                        </div>
                        <div style={{
                            background: T.warningBg, border: `1px solid ${T.warningBorder}`,
                            borderRadius: 12, padding: '20px 18px', textAlign: 'center',
                        }}>
                            <p style={{ fontSize: 12, color: T.warning, marginBottom: 6, fontWeight: 500 }}>Monthly Risk</p>
                            <p style={{
                                fontSize: 28, fontWeight: 700, color: T.warning,
                                fontFamily: "'JetBrains Mono', monospace",
                            }}>
                                ${monthlyRisk >= 1_000_000 ? `${(monthlyRisk / 1_000_000).toFixed(1)}M` : `${Math.round(monthlyRisk / 1000)}K`}
                            </p>
                        </div>
                    </div>

                    {/* Comparison callout */}
                    <div style={{
                        background: `${T.accent}06`, border: `1px solid ${T.accent}15`,
                        borderRadius: 10, padding: '14px 18px',
                        display: 'flex', alignItems: 'center', gap: 12,
                    }}>
                        <span style={{ fontSize: 18 }}>💡</span>
                        <p style={{ fontSize: 13, color: T.text, lineHeight: 1.6 }}>
                            RegEngine costs <strong style={{ color: T.accent }}>
                                {annualRevenue <= 50 ? '$999' : annualRevenue <= 200 ? '$1,999' : 'a fraction'}/mo
                            </strong> — that's <strong style={{ color: T.accent }}>
                                {((monthlyRisk / (annualRevenue <= 50 ? 999 : annualRevenue <= 200 ? 1999 : 4999)) * 100).toFixed(0)}x less
                            </strong> than what you risk losing every month.
                        </p>
                    </div>
                </div>
            </section>

            {/* ═══════════════════════════════════════════════════════════
               5. FSMA CHECKLIST (existing component)
               ═══════════════════════════════════════════════════════════ */}
            <FSMAChecklist />

            {/* ═══════════════════════════════════════════════════════════
               6. PRICING
               ═══════════════════════════════════════════════════════════ */}
            <section ref={pricing.ref} style={{
                position: 'relative', zIndex: 2,
                maxWidth: 1000, margin: '0 auto', padding: '60px 24px',
                opacity: pricing.visible ? 1 : 0,
                transform: pricing.visible ? 'translateY(0)' : 'translateY(30px)',
                transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
            }}>
                <div style={{ textAlign: 'center', marginBottom: 40 }}>
                    <p style={{ fontSize: 12, color: T.accent, textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 8, fontWeight: 600 }}>
                        Pricing
                    </p>
                    <h2 style={{ fontSize: 'clamp(24px, 4vw, 36px)', fontWeight: 700, color: T.heading, marginBottom: 12 }}>
                        Simple, Transparent Pricing
                    </h2>
                    <p style={{ fontSize: 15, color: T.textMuted }}>
                        Based on company size. No hidden fees. Cancel anytime.
                    </p>
                </div>

                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
                    gap: 16, alignItems: 'stretch',
                }}>
                    {PRICING_TIERS.map((tier) => (
                        <div
                            key={tier.revenue}
                            style={{
                                background: tier.highlighted ? `linear-gradient(180deg, ${T.accent}08, ${T.surface})` : T.surface,
                                border: tier.highlighted ? `2px solid ${T.accent}40` : `1px solid ${T.border}`,
                                borderRadius: 16, overflow: 'hidden',
                                transition: 'all 0.3s',
                                position: 'relative',
                            }}
                        >
                            {tier.highlighted && (
                                <div style={{
                                    background: `linear-gradient(90deg, ${T.accent}, ${T.accentHover})`,
                                    color: '#000', textAlign: 'center', padding: '8px',
                                    fontSize: 11, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em',
                                }}>
                                    Most Popular
                                </div>
                            )}
                            <div style={{ padding: '28px 24px' }}>
                                <p style={{
                                    fontSize: 12, color: T.textDim, textTransform: 'uppercase',
                                    letterSpacing: '0.05em', marginBottom: 12, fontWeight: 500,
                                }}>
                                    {tier.revenue} Revenue
                                </p>
                                <p style={{ fontSize: 36, fontWeight: 700, color: T.heading, marginBottom: 24 }}>
                                    {tier.price}
                                    {tier.period && <span style={{ fontSize: 14, fontWeight: 400, color: T.textMuted }}>{tier.period}</span>}
                                </p>
                                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                                    {tier.features.map((f, j) => (
                                        <div key={j} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                                            <span style={{ color: T.accent, fontSize: 14, fontWeight: 700 }}>✓</span>
                                            <span style={{ fontSize: 13, color: T.text }}>{f}</span>
                                        </div>
                                    ))}
                                </div>
                                <Link href="#assessment">
                                    <button style={{
                                        width: '100%', marginTop: 24, padding: '12px',
                                        background: tier.highlighted ? `linear-gradient(135deg, ${T.accent}, ${T.accentHover})` : 'transparent',
                                        color: tier.highlighted ? '#000' : T.text,
                                        border: tier.highlighted ? 'none' : `1px solid ${T.border}`,
                                        borderRadius: 10, fontSize: 14, fontWeight: 600, cursor: 'pointer',
                                        transition: 'all 0.2s',
                                    }}>
                                        {tier.price === 'Custom' ? 'Contact Us' : 'Get Started'}
                                    </button>
                                </Link>
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ═══════════════════════════════════════════════════════════
               7. FOUNDER CREDIBILITY
               ═══════════════════════════════════════════════════════════ */}
            <section ref={founder.ref} style={{
                position: 'relative', zIndex: 2,
                maxWidth: 700, margin: '0 auto', padding: '60px 24px',
                opacity: founder.visible ? 1 : 0,
                transform: founder.visible ? 'translateY(0)' : 'translateY(30px)',
                transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
            }}>
                <div style={{
                    background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                    padding: '36px 32px',
                    display: 'flex', gap: 24, alignItems: 'flex-start',
                    flexWrap: 'wrap',
                }}>
                    {/* Avatar */}
                    <div style={{
                        width: 72, height: 72, borderRadius: 16, flexShrink: 0,
                        background: `linear-gradient(135deg, ${T.accent}25, ${T.blue}25)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 24, fontWeight: 700, color: T.heading,
                    }}>
                        CS
                    </div>

                    <div style={{ flex: 1, minWidth: 200 }}>
                        <h3 style={{ fontSize: 20, fontWeight: 700, color: T.heading, marginBottom: 4 }}>
                            Christopher Sellers
                        </h3>
                        <p style={{ fontSize: 13, color: T.accent, fontWeight: 500, marginBottom: 16 }}>
                            Founder & CEO, RegEngine
                        </p>
                        <p style={{ fontSize: 14, color: T.textMuted, lineHeight: 1.8, marginBottom: 16 }}>
                            "I've spent 20 years in federal compliance — not selling software about it, doing it.
                            I built RegEngine because I watched companies lose contracts over traceability gaps
                            that a good API could have solved in a weekend. Every assessment I offer is personal.
                            No sales reps. No BDRs. Just a direct conversation about your supply chain."
                        </p>
                        <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                            {[
                                { value: '20+', label: 'Years in federal compliance' },
                                { value: '23', label: 'FDA categories covered' },
                                { value: '< 24hr', label: 'Assessment turnaround' },
                            ].map((stat, i) => (
                                <div key={i}>
                                    <p style={{ fontSize: 18, fontWeight: 700, color: T.heading, fontFamily: "'JetBrains Mono', monospace" }}>
                                        {stat.value}
                                    </p>
                                    <p style={{ fontSize: 11, color: T.textDim }}>{stat.label}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </section>

            {/* ═══════════════════════════════════════════════════════════
               8. ASSESSMENT FORM
               ═══════════════════════════════════════════════════════════ */}
            <section id="assessment" style={{
                position: 'relative', zIndex: 2,
                background: `linear-gradient(180deg, ${T.surface}, ${T.bg})`,
                borderTop: `1px solid ${T.border}`,
                padding: '80px 24px',
            }}>
                <div style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
                    <div style={{
                        width: 48, height: 48, borderRadius: 14,
                        background: `linear-gradient(135deg, ${T.accent}20, ${T.accent}08)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        margin: '0 auto 20px', fontSize: 22,
                    }}>📋</div>
                    <h2 style={{ fontSize: 28, fontWeight: 700, color: T.heading, marginBottom: 12 }}>
                        Free Walmart-Readiness Assessment
                    </h2>
                    <p style={{ color: T.textMuted, fontSize: 15, marginBottom: 36, lineHeight: 1.7 }}>
                        I'll personally review your traceability setup and provide a detailed gap analysis — free of charge.
                    </p>

                    {!submitted ? (
                        <form onSubmit={handleAssessment} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                            <div style={{ textAlign: 'left' }}>
                                <label style={{ fontSize: 13, fontWeight: 500, color: T.text, display: 'block', marginBottom: 6 }}>
                                    Company Name
                                </label>
                                <input
                                    placeholder="Acme Produce Co."
                                    value={companyName}
                                    onChange={(e) => setCompanyName(e.target.value)}
                                    required
                                    style={{
                                        width: '100%', padding: '12px 14px',
                                        background: T.bg, border: `1px solid ${T.border}`,
                                        borderRadius: 10, color: T.text, fontSize: 14,
                                        outline: 'none', transition: 'border-color 0.2s',
                                    }}
                                    onFocus={e => e.currentTarget.style.borderColor = T.accent}
                                    onBlur={e => e.currentTarget.style.borderColor = T.border}
                                />
                            </div>
                            <div style={{ textAlign: 'left' }}>
                                <label style={{ fontSize: 13, fontWeight: 500, color: T.text, display: 'block', marginBottom: 6 }}>
                                    Work Email
                                </label>
                                <input
                                    type="email"
                                    placeholder="you@company.com"
                                    value={email}
                                    onChange={(e) => setEmail(e.target.value)}
                                    required
                                    style={{
                                        width: '100%', padding: '12px 14px',
                                        background: T.bg, border: `1px solid ${T.border}`,
                                        borderRadius: 10, color: T.text, fontSize: 14,
                                        outline: 'none', transition: 'border-color 0.2s',
                                    }}
                                    onFocus={e => e.currentTarget.style.borderColor = T.accent}
                                    onBlur={e => e.currentTarget.style.borderColor = T.border}
                                />
                            </div>
                            <button
                                type="submit"
                                style={{
                                    background: `linear-gradient(135deg, ${T.accent}, ${T.accentHover})`,
                                    color: '#000', fontWeight: 600, padding: '14px 24px',
                                    width: '100%', border: 'none', borderRadius: 10,
                                    fontSize: 15, cursor: 'pointer',
                                    boxShadow: `0 0 30px ${T.accentGlow}`,
                                    transition: 'all 0.2s',
                                }}
                            >
                                Get Free Assessment →
                            </button>
                            <p style={{ fontSize: 12, color: T.textDim }}>
                                No commitment required. Assessment delivered within 24 hours.
                            </p>
                        </form>
                    ) : (
                        <div style={{
                            background: `${T.accent}08`, border: `1px solid ${T.accent}20`,
                            borderRadius: 16, padding: 36,
                        }}>
                            <div style={{ fontSize: 40, marginBottom: 16 }}>✓</div>
                            <h3 style={{ fontSize: 20, fontWeight: 600, color: T.accent, marginBottom: 8 }}>
                                Assessment Requested!
                            </h3>
                            <p style={{ color: T.textMuted, fontSize: 14, marginBottom: 20 }}>
                                I'll send your Walmart-readiness assessment to {email} within 24 hours.
                            </p>
                            <Link href="/ftl-checker">
                                <button style={{
                                    background: 'transparent', color: T.text,
                                    border: `1px solid ${T.border}`, padding: '10px 20px',
                                    borderRadius: 8, fontSize: 14, cursor: 'pointer',
                                }}>
                                    Check FTL Coverage While You Wait
                                </button>
                            </Link>
                        </div>
                    )}
                </div>
            </section>

            {/* ─── TRUST BADGES ─── */}
            <section style={{ position: 'relative', zIndex: 2, padding: '48px 24px' }}>
                <div style={{ maxWidth: 900, margin: '0 auto', textAlign: 'center' }}>
                    <p style={{ fontSize: 12, color: T.textDim, marginBottom: 20, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                        Built for Suppliers to Major Retailers
                    </p>
                    <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 32 }}>
                        {[
                            { icon: '📋', label: 'FSMA 204 Compliant' },
                            { icon: '🛡️', label: '23 FDA Categories' },
                            { icon: '🔐', label: 'SHA-256 Audit Trail' },
                            { icon: '⚡', label: '24-Hour FDA Response' },
                        ].map((item, i) => (
                            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                                <span style={{ fontSize: 14 }}>{item.icon}</span>
                                <span style={{ fontSize: 13, color: T.textMuted }}>{item.label}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ─── KEYFRAMES ─── */}
            <style>{`
                @keyframes pulse-dot {
                    0%, 100% { opacity: 1; }
                    50% { opacity: 0.5; }
                }
                @keyframes pulse-ring {
                    0% { box-shadow: 0 0 0 0 ${T.accent}60; }
                    70% { box-shadow: 0 0 0 10px ${T.accent}00; }
                    100% { box-shadow: 0 0 0 0 ${T.accent}00; }
                }
                input[type="range"] {
                    -webkit-appearance: none;
                    width: 100%;
                    height: 6px;
                    border-radius: 3px;
                    background: rgba(255,255,255,0.06);
                    outline: none;
                }
                input[type="range"]::-webkit-slider-thumb {
                    -webkit-appearance: none;
                    width: 20px;
                    height: 20px;
                    border-radius: 50%;
                    background: ${T.accent};
                    cursor: pointer;
                    border: 3px solid ${T.bg};
                    box-shadow: 0 0 10px ${T.accent}40;
                }
                input[type="range"]::-moz-range-thumb {
                    width: 20px;
                    height: 20px;
                    border-radius: 50%;
                    background: ${T.accent};
                    cursor: pointer;
                    border: 3px solid ${T.bg};
                }
                input::placeholder { color: ${T.textDim}; }
                * { box-sizing: border-box; margin: 0; }
            `}</style>
        </div>
    );
}
