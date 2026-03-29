'use client';

import Link from 'next/link';
import { T } from './constants';

export interface AssessmentFormProps {
    email: string;
    setEmail: (email: string) => void;
    companyName: string;
    setCompanyName: (name: string) => void;
    submitted: boolean;
    handleAssessment: (e: React.FormEvent) => Promise<void>;
}

export default function AssessmentForm({
    email, setEmail, companyName, setCompanyName,
    submitted, handleAssessment,
}: AssessmentFormProps) {
    return (
        <section id="assessment" style={{
            position: 'relative', zIndex: 2,
            background: `linear-gradient(180deg, ${T.surface}, ${T.bg})`,
            borderTop: `1px solid ${T.border}`,
            padding: 'clamp(3rem, 8vw, 80px) 16px',
        }}>
            <div style={{ maxWidth: 480, margin: '0 auto', textAlign: 'center' }}>
                <div style={{
                    width: 48, height: 48, borderRadius: 14,
                    background: `linear-gradient(135deg, ${T.accent}20, ${T.accent}08)`,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    margin: '0 auto 20px', fontSize: 22,
                }}>📋</div>
                <h2 style={{ fontSize: 28, fontWeight: 700, color: T.heading, marginBottom: 12 }}>
                    Free Retailer-Readiness Assessment
                </h2>
                <p style={{ color: T.textMuted, fontSize: 15, marginBottom: 36, lineHeight: 1.7 }}>
                    I&apos;ll personally review your traceability setup and provide a detailed gap analysis — free of charge.
                </p>

                {!submitted ? (
                    <form onSubmit={handleAssessment} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                        <div className="text-left">
                            <label style={{ fontSize: 13, fontWeight: 500, color: T.text, display: 'block', marginBottom: 6 }}>
                                Company Name
                            </label>
                            <input
                                placeholder="Acme Produce Co."
                                value={companyName}
                                onChange={(e) => setCompanyName(e.target.value)}
                                required
                                style={{
                                    width: '100%', padding: '12px 14px',
                                    background: T.bg, border: `1px solid ${T.border}`,
                                    borderRadius: 10, color: T.text, fontSize: 14,
                                    outline: 'none', transition: 'border-color 0.2s',
                                }}
                                onFocus={e => e.currentTarget.style.borderColor = T.accent}
                                onBlur={e => e.currentTarget.style.borderColor = T.border}
                            />
                        </div>
                        <div className="text-left">
                            <label style={{ fontSize: 13, fontWeight: 500, color: T.text, display: 'block', marginBottom: 6 }}>
                                Work Email
                            </label>
                            <input
                                type="email"
                                placeholder="you@company.com"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                                style={{
                                    width: '100%', padding: '12px 14px',
                                    background: T.bg, border: `1px solid ${T.border}`,
                                    borderRadius: 10, color: T.text, fontSize: 14,
                                    outline: 'none', transition: 'border-color 0.2s',
                                }}
                                onFocus={e => e.currentTarget.style.borderColor = T.accent}
                                onBlur={e => e.currentTarget.style.borderColor = T.border}
                            />
                        </div>
                        <button
                            type="submit"
                            style={{
                                background: T.accent, color: '#fff',
                                fontWeight: 600, padding: '14px 24px',
                                width: '100%', border: 'none', borderRadius: 10,
                                fontSize: 15, cursor: 'pointer',
                                boxShadow: `0 4px 16px ${T.accent}40`,
                                transition: 'all 0.2s', minHeight: 48,
                            }}
                        >
                            Get Free Assessment →
                        </button>
                        <p style={{ fontSize: 12, color: T.textDim }}>
                            No commitment required. Assessment delivered within 24 hours.
                        </p>
                    </form>
                ) : (
                    <div style={{
                        background: `${T.accent}08`, border: `1px solid ${T.accent}20`,
                        borderRadius: 16, padding: 36,
                    }}>
                        <div style={{ fontSize: 40, marginBottom: 16 }}>✓</div>
                        <h3 style={{ fontSize: 20, fontWeight: 600, color: T.accent, marginBottom: 8 }}>
                            Assessment Requested!
                        </h3>
                        <p style={{ color: T.textMuted, fontSize: 14, marginBottom: 20 }}>
                            I&apos;ll send your retailer-readiness assessment to {email} within 24 hours.
                        </p>
                        <Link href="/ftl-checker">
                            <button style={{
                                background: 'transparent', color: T.text,
                                border: `1px solid ${T.border}`, padding: '10px 20px',
                                borderRadius: 8, fontSize: 14, cursor: 'pointer',
                            }}>
                                Check FTL Coverage While You Wait
                            </button>
                        </Link>
                    </div>
                )}
            </div>
        </section>
    );
}
