'use client';

import { T } from './constants';
import { PRICING } from '@/lib/marketing-claims';

export interface RiskCalculatorProps {
    revealRef: React.RefObject<HTMLDivElement>;
    visible: boolean;
    annualRevenue: number;
    setAnnualRevenue: (value: number) => void;
    retailerPercent: number;
    setRetailerPercent: (value: number) => void;
    atRisk: number;
    monthlyRisk: number;
}

export default function RiskCalculator({
    revealRef, visible,
    annualRevenue, setAnnualRevenue,
    retailerPercent, setRetailerPercent,
    atRisk, monthlyRisk,
}: RiskCalculatorProps) {
    return (
        <section ref={revealRef} style={{
            position: 'relative', zIndex: 2,
            maxWidth: 700, margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) 16px',
            opacity: visible ? 1 : 0,
            transform: visible ? 'translateY(0)' : 'translateY(30px)',
            transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
            <div className="text-center mb-10">
                <p className="re-section-label">
                    Risk Calculator
                </p>
                <h2 className="re-section-title">
                    What Does Losing a Major Retailer Cost You?
                </h2>
                <p style={{ fontSize: 15, color: T.textMuted }}>
                    Drag the sliders. See the math. Then look at the pricing below.
                </p>
            </div>

            <div style={{
                background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                padding: 'clamp(1.5rem, 4vw, 32px) clamp(1rem, 3vw, 28px)',
                borderTop: `3px solid ${T.accent}`,
                boxShadow: `0 4px 24px rgba(0,0,0,0.12), 0 0 0 1px ${T.border}`,
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

                {/* Retailer % slider */}
                <div style={{ marginBottom: 32 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 10 }}>
                        <label style={{ fontSize: 14, color: T.text, fontWeight: 500 }}>% Revenue from Top Retailer</label>
                        <span style={{ fontSize: 14, fontWeight: 600, color: T.heading, fontFamily: "'JetBrains Mono', monospace" }}>
                            {retailerPercent}%
                        </span>
                    </div>
                    <input
                        type="range" min={5} max={80} step={5}
                        value={retailerPercent}
                        onChange={e => setRetailerPercent(Number(e.target.value))}
                        style={{ width: '100%', accentColor: T.warning }}
                    />
                    <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, color: T.textDim, marginTop: 4 }}>
                        <span>5%</span><span>80%</span>
                    </div>
                </div>

                {/* Results */}
                <div style={{
                    display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 200px), 1fr))', gap: 12,
                    marginBottom: 20,
                }}>
                    <div style={{
                        background: T.dangerBg, border: `1px solid rgba(239,68,68,0.15)`,
                        borderRadius: 12, padding: 'clamp(16px, 3vw, 24px) clamp(12px, 2vw, 18px)', textAlign: 'center',
                    }}>
                        <p style={{ fontSize: 11, color: T.danger, marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Annual Revenue at Risk</p>
                        <p style={{
                            fontSize: 'clamp(1.5rem, 5vw, 34px)', fontWeight: 700, color: T.danger,
                            fontFamily: "'JetBrains Mono', monospace",
                            letterSpacing: '-0.02em',
                        }}>
                            ${(atRisk / 1_000_000).toFixed(1)}M
                        </p>
                    </div>
                    <div style={{
                        background: T.warningBg, border: `1px solid ${T.warningBorder}`,
                        borderRadius: 12, padding: 'clamp(16px, 3vw, 24px) clamp(12px, 2vw, 18px)', textAlign: 'center',
                    }}>
                        <p style={{ fontSize: 11, color: T.warning, marginBottom: 8, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em' }}>Monthly Risk</p>
                        <p style={{
                            fontSize: 'clamp(1.5rem, 5vw, 34px)', fontWeight: 700, color: T.warning,
                            fontFamily: "'JetBrains Mono', monospace",
                            letterSpacing: '-0.02em',
                        }}>
                            ${monthlyRisk >= 1_000_000 ? `${(monthlyRisk / 1_000_000).toFixed(1)}M` : `${Math.round(monthlyRisk / 1000)}K`}
                        </p>
                    </div>
                </div>

                {/* Comparison callout */}
                <div style={{
                    background: `${T.accent}08`, border: `2px solid ${T.accent}25`,
                    borderRadius: 12, padding: 'clamp(14px, 3vw, 18px) clamp(14px, 3vw, 20px)',
                    display: 'flex', alignItems: 'flex-start', gap: 12, flexWrap: 'wrap',
                }}>
                    <div style={{
                        width: 40, height: 40, borderRadius: 10, flexShrink: 0,
                        background: `${T.accent}15`, display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 18,
                    }}>💡</div>
                    <div>
                        <p style={{ fontSize: 14, color: T.heading, fontWeight: 600, marginBottom: 2 }}>
                            RegEngine: {annualRevenue <= 50 ? PRICING.starterMonthly : annualRevenue <= 200 ? PRICING.growthMonthly : PRICING.scaleMonthly}/mo (Design Partner)
                        </p>
                        <p style={{ fontSize: 13, color: T.text, lineHeight: 1.5 }}>
                            That&apos;s <strong style={{ color: T.accent, fontSize: 15 }}>
                                {((monthlyRisk / (annualRevenue <= 50 ? PRICING.starterMonthlyNum : annualRevenue <= 200 ? PRICING.growthMonthlyNum : PRICING.scaleMonthlyNum))).toLocaleString(undefined, { maximumFractionDigits: 0 })}x less
                            </strong> than what you risk losing every month.
                        </p>
                    </div>
                </div>
            </div>
        </section>
    );
}
