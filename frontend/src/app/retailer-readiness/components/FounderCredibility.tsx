'use client';

import { T } from './constants';

export interface FounderCredibilityProps {
    revealRef: React.RefObject<HTMLDivElement>;
    visible: boolean;
}

export default function FounderCredibility({ revealRef, visible }: FounderCredibilityProps) {
    return (
        <section ref={revealRef} style={{
            position: 'relative', zIndex: 2,
            maxWidth: 700, margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) 16px',
            opacity: visible ? 1 : 0,
            transform: visible ? 'translateY(0)' : 'translateY(30px)',
            transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
            <div style={{
                background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                padding: 'clamp(1.5rem, 5vw, 36px) clamp(1rem, 4vw, 32px)',
                display: 'flex', gap: 'clamp(16px, 3vw, 24px)', alignItems: 'flex-start',
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
                        Family restaurant kid. Organic farm hand. AmeriCorps volunteer. U.S. Senate staff. Startup closer.
                        I built RegEngine because compliance shouldn&apos;t require a six-figure platform and a twelve-month implementation.
                        Your traceability data should be verified, exportable, and ready before anyone asks for it.
                        Every Retailer Readiness Assessment is scored automatically against the current FDA rule model and retailer-specific benchmarks reflected in RegEngine. Results in minutes, not weeks.
                    </p>
                    <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
                        {[
                            { value: '10+', label: 'Years across compliance & policy' },
                            { value: '23', label: 'FDA categories covered' },
                            { value: '< 24hr', label: 'Assessment turnaround' },
                        ].map((stat, i) => (
                            <div key={i}>
                                <p style={{ fontSize: 18, fontWeight: 700, color: T.heading, fontFamily: "'JetBrains Mono', monospace" }}>
                                    {stat.value}
                                </p>
                                <p className="text-[11px] text-re-text-disabled">{stat.label}</p>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
}
