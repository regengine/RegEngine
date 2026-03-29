'use client';

import { RefObject } from 'react';
import Link from 'next/link';
import { T } from './constants';

export interface HeroSectionProps {
    heroRef: RefObject<HTMLDivElement>;
    daysCount: number;
}

export default function HeroSection({ heroRef, daysCount }: HeroSectionProps) {
    return (
        <section ref={heroRef} style={{
            position: 'relative', zIndex: 2,
            maxWidth: 1120, margin: '0 auto', padding: 'clamp(3rem, 8vw, 80px) 16px clamp(2rem, 5vw, 40px)',
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
                Retailer Supplier Compliance
            </div>

            <h1 style={{
                fontSize: 'clamp(36px, 5.5vw, 56px)', fontWeight: 700,
                color: T.heading, lineHeight: 1.08, margin: '0 0 20px',
                letterSpacing: '-0.02em',
            }}>
                Retailer-Ready<br />
                <span style={{
                    background: `linear-gradient(135deg, ${T.accent}, #34d399)`,
                    WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
                }}>In 30 Days or Less</span>
            </h1>

            <p style={{
                fontSize: 18, color: T.textMuted,
                maxWidth: 540, margin: '0 auto 16px', lineHeight: 1.7,
            }}>
                Meet major retailer traceability requirements before you lose your spot on the shelf.
                API and CSV ingest. FDA-ready export. No portal logins.
            </p>

            {/* Countdown */}
            <div style={{
                display: 'inline-flex', alignItems: 'baseline', gap: 10,
                background: T.surface, border: `2px solid ${daysCount > 600 ? T.warningBorder : 'rgba(239,68,68,0.2)'}`,
                borderRadius: 14, padding: 'clamp(12px, 3vw, 16px) clamp(16px, 5vw, 32px)', marginBottom: 32,
                boxShadow: `0 0 30px ${daysCount > 600 ? 'rgba(245,158,11,0.08)' : 'rgba(239,68,68,0.08)'}`,
            }}>
                <span style={{
                    fontSize: 'clamp(1.75rem, 5vw, 40px)', fontWeight: 700, fontFamily: "'JetBrains Mono', monospace",
                    color: daysCount > 600 ? T.warning : T.danger,
                    letterSpacing: '-0.02em',
                }}>
                    {daysCount.toLocaleString()}
                </span>
                <span className="text-sm text-re-text-muted">days until FDA&apos;s July 2028 deadline</span>
            </div>

            <div className="flex flex-col sm:flex-row gap-3 justify-center items-center">
                <Link href="/tools/recall-readiness" className="w-full sm:w-auto">
                    <button className="re-cta-primary" style={{
                        background: T.accent, color: '#fff', fontWeight: 600,
                        padding: '14px 32px', fontSize: 15,
                        border: 'none', borderRadius: 10, cursor: 'pointer',
                        boxShadow: `0 4px 16px ${T.accent}40`,
                        transition: 'all 0.2s',
                        minHeight: 48, width: '100%',
                    }}>
                        Get Free Assessment →
                    </button>
                </Link>
                <Link href="/ftl-checker" className="w-full sm:w-auto">
                    <button className="re-cta-secondary" style={{
                        background: 'transparent', color: T.text,
                        border: `1px solid ${T.border}`, padding: '14px 28px', fontSize: 15,
                        borderRadius: 10, cursor: 'pointer', transition: 'all 0.2s',
                        minHeight: 48, width: '100%',
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
    );
}
