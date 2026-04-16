'use client';

import { T, COMPETITORS } from './constants';

export interface CompetitorComparisonProps {
    revealRef: React.RefObject<HTMLDivElement>;
    visible: boolean;
}

export default function CompetitorComparison({ revealRef, visible }: CompetitorComparisonProps) {
    return (
        <section ref={revealRef} style={{
            position: 'relative', zIndex: 2,
            maxWidth: 900, margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) 16px',
            opacity: visible ? 1 : 0,
            transform: visible ? 'translateY(0)' : 'translateY(30px)',
            transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
            <div className="text-center mb-10">
                <p className="re-section-label">
                    How We Compare
                </p>
                <h2 className="re-section-title">
                    RegEngine vs. Legacy Platforms
                </h2>
            </div>
            <div style={{
                background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                overflow: 'hidden',
            }}>
              <div style={{ overflowX: 'auto' }} className="scrollbar-none">
                {/* Table header */}
                <div className="competitor-row" style={{
                    display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr', minWidth: 520,
                    padding: '16px 20px', borderBottom: `1px solid ${T.border}`,
                    background: `${T.accent}08`,
                }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: T.heading, textTransform: 'uppercase', letterSpacing: '0.04em' }}>Feature</span>
                    <span style={{ fontSize: 12, color: T.accent, fontWeight: 700 }}>RegEngine</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: T.textDim }}>Trustwell</span>
                    <span style={{ fontSize: 12, fontWeight: 600, color: T.textDim }}>TraceLink</span>
                </div>
                {COMPETITORS.map((row, i) => (
                    <div key={i} className="competitor-row" style={{
                        display: 'grid', gridTemplateColumns: '1.5fr 1fr 1fr 1fr', minWidth: 520,
                        padding: '14px 20px',
                        borderBottom: i < COMPETITORS.length - 1 ? `1px solid ${T.border}` : 'none',
                        background: i % 2 === 1 ? `${T.surfaceHover}` : 'transparent',
                    }}>
                        <span style={{ fontSize: 13, color: T.text, fontWeight: 500 }}>{row.feature}</span>
                        <span style={{ fontSize: 13, color: T.accent, fontWeight: 600 }}>{row.regengine}</span>
                        <span style={{ fontSize: 13, color: T.textDim }}>{row.foodlogiq}</span>
                        <span style={{ fontSize: 13, color: T.textDim }}>{row.tracelink}</span>
                    </div>
                ))}
              </div>
            </div>
        </section>
    );
}
