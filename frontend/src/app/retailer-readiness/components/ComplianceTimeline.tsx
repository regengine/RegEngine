'use client';

import { T } from './constants';

export interface ComplianceTimelineProps {
    revealRef: React.RefObject<HTMLDivElement>;
    visible: boolean;
}

export default function ComplianceTimeline({ revealRef, visible }: ComplianceTimelineProps) {
    return (
        <section ref={revealRef} style={{
            position: 'relative', zIndex: 2,
            maxWidth: 900, margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) 16px clamp(3rem, 6vw, 80px)',
            opacity: visible ? 1 : 0,
            transform: visible ? 'translateY(0)' : 'translateY(30px)',
            transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
            <div className="text-center mb-12">
                <p className="re-section-label">
                    Compliance Timeline
                </p>
                <h2 className="re-section-title">
                    The Clock Is Already Running
                </h2>
                <p style={{ fontSize: 15, color: T.textMuted, maxWidth: 500, margin: '0 auto' }}>
                    Major retailer internal deadlines come <strong className="text-re-warning">before</strong> the FDA mandate.
                    Suppliers who wait will be too late.
                </p>
            </div>

            {/* Timeline visualization */}
            <div style={{
                background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                padding: 'clamp(1.5rem, 5vw, 40px) clamp(1rem, 4vw, 32px)',
                borderTop: `3px solid ${T.accent}`,
                boxShadow: `0 4px 24px rgba(0,0,0,0.12), 0 0 0 1px ${T.border}`,
            }}>
                {/* Timeline bar */}
                <div style={{ position: 'relative', height: 4, background: T.border, borderRadius: 4, marginBottom: 60, marginTop: 20 }}>
                    {/* Progress fill */}
                    <div style={{
                        position: 'absolute', left: 0, top: 0, height: '100%', borderRadius: 4,
                        width: visible ? '12%' : '0%',
                        background: `linear-gradient(90deg, ${T.accent}, ${T.warning})`,
                        transition: 'width 1.5s cubic-bezier(0.16, 1, 0.3, 1) 0.5s',
                    }} />

                    {/* "You are here" marker */}
                    <div style={{
                        position: 'absolute', left: '12%', top: '50%', transform: 'translate(-50%, -50%)',
                        width: 16, height: 16, borderRadius: '50%',
                        background: T.accent,
                        boxShadow: `0 0 20px ${T.accent}80`,
                        animation: visible ? 'pulse-ring 2s infinite' : 'none',
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

                    {/* Retailer deadline */}
                    <div style={{
                        position: 'absolute', left: '55%', top: '50%', transform: 'translate(-50%, -50%)',
                        width: 14, height: 14, borderRadius: '50%',
                        background: T.warning, border: `3px solid ${T.bg}`, zIndex: 2,
                    }}>
                        <div style={{
                            position: 'absolute', top: 24, left: '50%', transform: 'translateX(-50%)',
                            textAlign: 'center', whiteSpace: 'nowrap',
                        }}>
                            <p style={{ fontSize: 13, fontWeight: 600, color: T.warning }}>Retailer Deadlines</p>
                            <p className="text-[11px] text-re-text-disabled">Walmart Aug 2025 · Kroger Jun 2025</p>
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
                            <p className="text-[11px] text-re-text-disabled">July 20, 2028</p>
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
                            Why are retailer deadlines earlier?
                        </p>
                        <p style={{ fontSize: 13, color: T.textMuted, lineHeight: 1.6 }}>
                            Major retailers are requiring suppliers to demonstrate traceability capability as a condition for continued shelf placement — well ahead of the FDA mandate.
                            Suppliers who can&apos;t show readiness risk deprioritization during the next category review.
                        </p>
                    </div>
                </div>
            </div>
        </section>
    );
}
