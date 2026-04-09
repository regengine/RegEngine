'use client';

import Link from 'next/link';
import { T } from './constants';

export interface StickyCTAProps {
    showSticky: boolean;
    trackEvent: (event: string, data?: Record<string, unknown>) => void;
}

export default function StickyCTA({ showSticky, trackEvent }: StickyCTAProps) {
    return (
        <div style={{
            position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 9998,
            background: 'var(--re-sticky-bg, rgba(6,9,15,0.92))', backdropFilter: 'blur(12px)',
            WebkitBackdropFilter: 'blur(12px)',
            borderTop: `1px solid ${T.border}`,
            padding: 'clamp(10px, 2vw, 12px) clamp(12px, 4vw, 24px)',
            paddingBottom: 'calc(clamp(10px, 2vw, 12px) + env(safe-area-inset-bottom, 0px))',
            transform: showSticky ? 'translateY(0)' : 'translateY(100%)',
            transition: 'transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)',
        }}>
            <div style={{
                maxWidth: 1120, margin: '0 auto',
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                gap: 12, flexWrap: 'wrap',
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
                    <span style={{
                        fontSize: 'clamp(14px, 3vw, 16px)', fontWeight: 600, color: T.accent,
                        flexShrink: 0,
                    }}>
                        Recall response in minutes, not days
                    </span>
                    <span className="hidden sm:inline text-[12px] text-re-text-muted" style={{ lineHeight: 1.3 }}>— FSMA 204 ready</span>
                </div>
                <Link href="/tools/recall-readiness">
                    <button
                        onClick={() => trackEvent('sticky_cta_click')}
                        style={{
                            background: T.accent, color: '#fff',
                            fontWeight: 600, padding: '10px 20px', fontSize: 14,
                            border: 'none', borderRadius: 8, cursor: 'pointer',
                            boxShadow: `0 4px 16px ${T.accent}40`,
                            transition: 'all 0.2s',
                            minHeight: 44, whiteSpace: 'nowrap',
                        }}
                    >
                        Get Free Assessment →
                    </button>
                </Link>
            </div>
        </div>
    );
}
