'use client';

import Link from 'next/link';
import { T } from './constants';

export interface ExitIntentPopupProps {
    showExitIntent: boolean;
    setShowExitIntent: (show: boolean) => void;
    trackEvent: (event: string, data?: Record<string, unknown>) => void;
}

export default function ExitIntentPopup({ showExitIntent, setShowExitIntent, trackEvent }: ExitIntentPopupProps) {
    if (!showExitIntent) return null;

    return (
        <div style={{
            position: 'fixed', inset: 0, zIndex: 10000,
            background: 'rgba(0,0,0,0.7)', backdropFilter: 'blur(4px)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            padding: 24,
        }} onClick={() => setShowExitIntent(false)}>
            <div
                onClick={e => e.stopPropagation()}
                style={{
                    background: T.bg, border: `1px solid ${T.border}`,
                    borderRadius: 20, padding: 'clamp(24px, 5vw, 40px) clamp(20px, 4vw, 36px)',
                    maxWidth: 460, width: '100%', textAlign: 'center',
                    boxShadow: `0 0 60px ${T.accent}15`,
                    animation: 'exit-popup-in 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
                }}
            >
                <div style={{ fontSize: 40, marginBottom: 16 }}>⚠️</div>
                <h3 style={{ fontSize: 22, fontWeight: 700, color: T.heading, marginBottom: 12 }}>
                    Don&apos;t leave without your free assessment
                </h3>
                <p style={{ fontSize: 14, color: T.textMuted, lineHeight: 1.7, marginBottom: 24 }}>
                    Major retailers are evaluating suppliers <strong className="text-re-warning">right now</strong>.
                    Get a personalized gap analysis before your next category review.
                </p>
                <Link href="/tools/recall-readiness">
                    <button
                        onClick={() => { setShowExitIntent(false); trackEvent('exit_intent_cta_click'); }}
                        style={{
                            background: T.accent, color: '#fff',
                            fontWeight: 600, padding: '14px 28px', fontSize: 15,
                            border: 'none', borderRadius: 10, cursor: 'pointer',
                            boxShadow: `0 4px 16px ${T.accent}40`,
                            width: '100%', marginBottom: 12, minHeight: 48,
                            transition: 'all 0.2s',
                        }}
                    >
                        Yes, Assess My Readiness →
                    </button>
                </Link>
                <button
                    onClick={() => setShowExitIntent(false)}
                    style={{
                        background: 'transparent', border: 'none',
                        color: T.textDim, fontSize: 13, cursor: 'pointer',
                        padding: '12px 16px', minHeight: 48,
                    }}
                >
                    No thanks, I&apos;ll risk it
                </button>
            </div>
        </div>
    );
}
