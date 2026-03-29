'use client';

import { T } from './constants';

export default function TrustBadges() {
    return (
        <section style={{ position: 'relative', zIndex: 2, padding: 'clamp(2rem, 6vw, 48px) clamp(1rem, 4vw, 24px)' }}>
            <div style={{ maxWidth: 900, margin: '0 auto', textAlign: 'center' }}>
                <p style={{ fontSize: 12, color: T.textDim, marginBottom: 20, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
                    Built for Suppliers to Major Retailers
                </p>
                <div style={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 'clamp(16px, 4vw, 32px)' }}>
                    {[
                        { icon: '📋', label: 'FSMA 204 Compliant' },
                        { icon: '🛡️', label: 'Full FTL Coverage' },
                        { icon: '🔐', label: 'SHA-256 Audit Trail' },
                        { icon: '⚡', label: '24-Hour FDA Response' },
                    ].map((item, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span style={{ fontSize: 14 }}>{item.icon}</span>
                            <span className="text-[13px] text-re-text-muted">{item.label}</span>
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}
