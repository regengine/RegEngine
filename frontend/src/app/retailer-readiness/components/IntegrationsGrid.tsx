'use client';

import { T, INTEGRATIONS } from './constants';

export interface IntegrationsGridProps {
    revealRef: React.RefObject<HTMLDivElement>;
    visible: boolean;
}

export default function IntegrationsGrid({ revealRef, visible }: IntegrationsGridProps) {
    return (
        <section ref={revealRef} style={{
            position: 'relative', zIndex: 2,
            maxWidth: 800, margin: '0 auto', padding: 'clamp(2rem, 5vw, 40px) clamp(1rem, 4vw, 24px) clamp(2.5rem, 6vw, 60px)',
            opacity: visible ? 1 : 0,
            transform: visible ? 'translateY(0)' : 'translateY(30px)',
            transition: 'all 0.8s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
            <div style={{ textAlign: 'center', marginBottom: 32 }}>
                <p className="re-section-label">
                    Works With Your Stack
                </p>
                <h2 style={{ fontSize: 'clamp(20px, 3vw, 28px)', fontWeight: 700, color: T.heading }}>
                    Plug Into Your Existing Systems
                </h2>
            </div>
            <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
                gap: 12,
            }}>
                {INTEGRATIONS.map((int, i) => (
                    <div key={i} style={{
                        background: T.surface, border: `1px solid ${T.border}`,
                        borderRadius: 12, padding: '20px 12px', textAlign: 'center',
                        transition: 'all 0.2s',
                        cursor: 'default',
                    }}
                        onMouseEnter={e => { e.currentTarget.style.borderColor = T.borderHover; e.currentTarget.style.transform = 'translateY(-2px)'; }}
                        onMouseLeave={e => { e.currentTarget.style.borderColor = T.border; e.currentTarget.style.transform = 'translateY(0)'; }}
                    >
                        <div style={{ fontSize: 24, marginBottom: 8 }}>{int.icon}</div>
                        <p style={{ fontSize: 12, color: T.textMuted, fontWeight: 500 }}>{int.name}</p>
                    </div>
                ))}
            </div>
        </section>
    );
}
