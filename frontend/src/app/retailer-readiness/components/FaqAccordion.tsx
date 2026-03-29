'use client';

import { T, FAQ_ITEMS } from './constants';

export interface FaqAccordionProps {
    revealRef: React.RefObject<HTMLDivElement>;
    visible: boolean;
    openFaq: number | null;
    setOpenFaq: (index: number | null) => void;
    trackEvent: (event: string, data?: Record<string, unknown>) => void;
}

export default function FaqAccordion({ revealRef, visible, openFaq, setOpenFaq, trackEvent }: FaqAccordionProps) {
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
                    FAQ
                </p>
                <h2 className="re-section-title">
                    Common Questions
                </h2>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {FAQ_ITEMS.map((faq, i) => (
                    <div key={i} style={{
                        background: T.surface, border: `1px solid ${openFaq === i ? `${T.accent}30` : T.border}`,
                        borderRadius: 12, overflow: 'hidden',
                        transition: 'border-color 0.3s',
                    }}>
                        <button
                            onClick={() => { setOpenFaq(openFaq === i ? null : i); trackEvent('faq_click', { question: faq.q }); }}
                            style={{
                                width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                                padding: 'clamp(14px, 3vw, 16px) clamp(14px, 3vw, 20px)', background: 'transparent', border: 'none',
                                color: T.heading, fontSize: 14, fontWeight: 600, cursor: 'pointer',
                                textAlign: 'left', gap: 12, minHeight: 48,
                            }}
                        >
                            <span>{faq.q}</span>
                            <span style={{
                                fontSize: 18, color: T.textDim, flexShrink: 0,
                                transform: openFaq === i ? 'rotate(45deg)' : 'rotate(0)',
                                transition: 'transform 0.3s',
                            }}>+</span>
                        </button>
                        <div style={{
                            maxHeight: openFaq === i ? 200 : 0,
                            overflow: 'hidden',
                            transition: 'max-height 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
                        }}>
                            <p style={{
                                padding: '0 20px 16px',
                                fontSize: 13, color: T.textMuted, lineHeight: 1.7,
                            }}>
                                {faq.a}
                            </p>
                        </div>
                    </div>
                ))}
            </div>
        </section>
    );
}
