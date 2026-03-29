'use client';

import Link from 'next/link';
import { T, PRICING_TIERS } from './constants';

export interface PricingSectionProps {
    revealRef: React.RefObject<HTMLDivElement>;
    visible: boolean;
}

export default function PricingSection({ revealRef, visible }: PricingSectionProps) {
    return (
        <section ref={revealRef} style={{
            position: 'relative', zIndex: 2,
            maxWidth: 1000, margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) 16px',
            opacity: visible ? 1 : 0,
            transform: visible ? 'translateY(0)' : 'translateY(30px)',
            transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
            <div className="text-center mb-10">
                <p className="re-section-label">
                    Pricing
                </p>
                <h2 className="re-section-title">
                    Simple, Transparent Pricing
                </h2>
                <p style={{ fontSize: 15, color: T.textMuted }}>
                    Based on company size. No hidden fees. Cancel anytime.
                </p>
            </div>

            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))',
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
                                {tier.revenue}
                            </p>
                            <p style={{ fontSize: 'clamp(28px, 5vw, 36px)', fontWeight: 700, color: T.heading, marginBottom: 24 }}>
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
                                    width: '100%', marginTop: 24, padding: '14px 12px',
                                    background: tier.highlighted ? `linear-gradient(135deg, ${T.accent}, ${T.accentHover})` : 'transparent',
                                    color: tier.highlighted ? '#000' : T.text,
                                    border: tier.highlighted ? 'none' : `1px solid ${T.border}`,
                                    borderRadius: 10, fontSize: 14, fontWeight: 600, cursor: 'pointer',
                                    transition: 'all 0.2s', minHeight: 48,
                                }}>
                                    {tier.price === 'Custom' ? 'Contact Us' : 'Get Started'}
                                </button>
                            </Link>
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}
