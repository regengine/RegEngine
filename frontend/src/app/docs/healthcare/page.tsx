import Link from 'next/link';
import { ArrowLeft, ShieldCheck, Mail, Clock, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function HealthcareDocsPage() {
    return (
        <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.fontSans }}>
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
                background: 'linear-gradient(135deg, rgba(236,72,153,0.1) 0%, transparent 50%)',
            }}>
                <div style={{ maxWidth: '700px', margin: '0 auto' }}>
                    <Link
                        href="/docs"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            color: T.accent,
                            fontSize: '14px',
                            textDecoration: 'none',
                            marginBottom: '16px',
                        }}
                    >
                        <ArrowLeft style={{ width: 16, height: 16 }} />
                        Back to Docs
                    </Link>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px' }}>
                        <ShieldCheck style={{ width: 28, height: 28, color: 'var(--re-accent-pink)' }} />
                        <span style={{
                            background: 'rgba(236,72,153,0.2)',
                            color: 'var(--re-accent-pink)',
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '4px',
                        }}>
                            Coming Q3 2026
                        </span>
                    </div>

                    <h1 style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                        Healthcare Compliance
                    </h1>
                    <p style={{ color: T.textMuted, fontSize: '16px' }}>
                        HIPAA, HITECH, and healthcare data privacy compliance
                    </p>
                </div>
            </div>

            {/* Content */}
            <div style={{ maxWidth: '700px', margin: '0 auto', padding: '48px 24px' }}>

                {/* Scope Preview */}
                <section style={{ marginBottom: '48px' }}>
                    <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        What&apos;s Coming
                    </h2>

                    <div style={{ display: 'grid', gap: '12px' }}>
                        {[
                            { title: 'HIPAA Privacy Rule', desc: 'PHI access logging and audit trails' },
                            { title: 'HIPAA Security Rule', desc: 'Administrative, physical, and technical safeguards' },
                            { title: 'Business Associate Management', desc: 'BAA tracking and compliance verification' },
                            { title: 'Breach Notification', desc: 'Incident response and HHS reporting automation' },
                        ].map((item) => (
                            <div key={item.title} style={{
                                padding: '16px 20px',
                                background: T.surface,
                                borderRadius: '8px',
                                border: `1px solid ${T.border}`,
                            }}>
                                <div style={{ fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '4px' }}>{item.title}</div>
                                <div style={{ fontSize: '14px', color: T.textMuted }}>{item.desc}</div>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Sample API Call */}
                <section style={{ marginBottom: '48px' }}>
                    <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        <Clock style={{ width: 20, height: 20, display: 'inline', verticalAlign: 'middle', marginRight: '8px' }} />
                        Preview: PHI Access Log
                    </h2>

                    <div style={{
                        background: 'rgba(0,0,0,0.6)',
                        borderRadius: '8px',
                        overflow: 'hidden',
                        border: `1px solid ${T.border}`,
                        opacity: 0.7,
                    }}>
                        <div style={{
                            background: 'rgba(255,255,255,0.05)',
                            padding: '8px 16px',
                            borderBottom: `1px solid ${T.border}`,
                        }}>
                            <span style={{ fontSize: '12px', color: T.textMuted }}>POST /v1/records (Coming Soon)</span>
                        </div>
                        <pre style={{
                            padding: '16px 20px',
                            margin: 0,
                            fontSize: '13px',
                            lineHeight: 1.5,
                            color: 'var(--re-text-muted)',
                        }}>
                            <code>{`{
  "type": "compliance_event",
  "framework": "HIPAA",
  "data": {
    "event_type": "phi_access",
    "user_id": "provider_12345",
    "patient_record": "MRN-98765",
    "access_reason": "treatment",
    "access_duration_sec": 180
  }
}`}</code>
                        </pre>
                    </div>
                </section>

                {/* Early Access CTA */}
                <section style={{
                    background: 'linear-gradient(135deg, rgba(236,72,153,0.15) 0%, rgba(236,72,153,0.05) 100%)',
                    border: `1px solid rgba(236,72,153,0.3)`,
                    borderRadius: '12px',
                    padding: '32px',
                    textAlign: 'center',
                }}>
                    <Mail style={{ width: 32, height: 32, color: 'var(--re-accent-pink)', margin: '0 auto 16px' }} />
                    <h3 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                        Get Early Access
                    </h3>
                    <p style={{ color: T.text, fontSize: '14px', marginBottom: '20px', maxWidth: '400px', margin: '0 auto 20px' }}>
                        Join the waitlist to be notified when Healthcare compliance features launch.
                    </p>
                    <a
                        href="mailto:healthcare@regengine.co?subject=Healthcare%20Early%20Access"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            background: 'var(--re-accent-pink)',
                            color: 'white',
                            padding: '12px 24px',
                            borderRadius: '6px',
                            fontWeight: 600,
                            fontSize: '14px',
                            textDecoration: 'none',
                        }}
                    >
                        <Mail style={{ width: 16, height: 16 }} />
                        Request Early Access
                    </a>
                </section>

                {/* Back Link */}
                <div style={{ marginTop: '48px', textAlign: 'center' }}>
                    <Link
                        href="/docs/fsma-204"
                        style={{
                            color: T.accent,
                            fontSize: '14px',
                            textDecoration: 'none',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                        }}
                    >
                        <FileText style={{ width: 16, height: 16 }} />
                        See FSMA 204 Guide (Live Now)
                    </Link>
                </div>
            </div>
        </div>
    );
}
