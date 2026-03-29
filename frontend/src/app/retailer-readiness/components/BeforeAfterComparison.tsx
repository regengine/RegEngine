'use client';

import { T } from './constants';

export interface BeforeAfterComparisonProps {
    revealRef: React.RefObject<HTMLDivElement>;
    visible: boolean;
}

export default function BeforeAfterComparison({ revealRef, visible }: BeforeAfterComparisonProps) {
    return (
        <section ref={revealRef} style={{
            position: 'relative', zIndex: 2,
            maxWidth: 1000, margin: '0 auto', padding: 'clamp(2.5rem, 6vw, 60px) 16px',
            opacity: visible ? 1 : 0,
            transform: visible ? 'translateY(0)' : 'translateY(30px)',
            transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
            <div className="text-center mb-12">
                <p className="re-section-label">
                    Why Switch?
                </p>
                <h2 className="re-section-title">
                    Your Current Setup vs. RegEngine
                </h2>
            </div>

            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 340px), 1fr))',
                gap: 20,
            }}>
                {/* BEFORE */}
                <div style={{
                    background: T.dangerBg, border: `1px solid rgba(239,68,68,0.12)`,
                    borderRadius: 16, padding: 'clamp(20px, 4vw, 28px) clamp(16px, 3vw, 24px)',
                }}>
                    <div style={{
                        display: 'inline-flex', alignItems: 'center', gap: 8,
                        background: 'rgba(239,68,68,0.1)', borderRadius: 8, padding: '6px 14px',
                        marginBottom: 24, fontSize: 12, fontWeight: 600, color: T.danger,
                        textTransform: 'uppercase', letterSpacing: '0.05em',
                    }}>
                        ✗ Without RegEngine
                    </div>
                    <div className="flex flex-col gap-4">
                        {[
                            { label: 'Record keeping', value: 'Excel spreadsheets' },
                            { label: 'Trace response time', value: '3–5 business days' },
                            { label: 'Data format', value: 'PDFs, emails, paper' },
                            { label: 'Supply chain visibility', value: 'One hop upstream' },
                            { label: 'FDA audit readiness', value: 'Hope for the best' },
                            { label: 'Team workflow', value: 'Manual portal logins' },
                        ].map((item, i) => (
                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 12, borderBottom: `1px solid ${T.border}`, gap: 8 }}>
                                <span className="text-xs sm:text-sm text-re-text-muted" style={{ flexShrink: 0 }}>{item.label}</span>
                                <span style={{ fontSize: 'clamp(12px, 2.5vw, 14px)', color: T.danger, fontWeight: 500, textAlign: 'right' }}>{item.value}</span>
                            </div>
                        ))}
                    </div>
                </div>

                {/* AFTER */}
                <div style={{
                    background: `${T.accent}05`, border: `1px solid ${T.accent}18`,
                    borderRadius: 16, padding: 'clamp(20px, 4vw, 28px) clamp(16px, 3vw, 24px)',
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
                    <div className="flex flex-col gap-4">
                        {[
                            { label: 'Record keeping', value: 'Automated API capture' },
                            { label: 'Trace response time', value: '< 5 seconds' },
                            { label: 'Data format', value: 'FDA sortable spreadsheet' },
                            { label: 'Supply chain visibility', value: 'Full chain, farm to store' },
                            { label: 'FDA audit readiness', value: 'Click. Export. Done.' },
                            { label: 'Team workflow', value: 'Zero portal logins' },
                        ].map((item, i) => (
                            <div key={i} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingBottom: 12, borderBottom: `1px solid ${T.accent}08`, gap: 8 }}>
                                <span className="text-xs sm:text-sm text-re-text-muted" style={{ flexShrink: 0 }}>{item.label}</span>
                                <span style={{ fontSize: 'clamp(12px, 2.5vw, 14px)', color: T.accent, fontWeight: 600, textAlign: 'right' }}>{item.value}</span>
                            </div>
                        ))}
                    </div>
                </div>
            </div>
        </section>
    );
}
