import Link from 'next/link';
import { ArrowLeft, ShieldCheck, Mail, Clock, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function HealthcareDocsPage() {
    return (
        <div className="re-page">
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
                background: 'linear-gradient(135deg, rgba(236,72,153,0.1) 0%, transparent 50%)',
            }}>
                <div className="max-w-[700px] mx-auto">
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
                        <ArrowLeft className="w-4 h-4" />
                        Back to Docs
                    </Link>

                    <div className="flex items-center gap-3 mb-3">
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

                    <h1 className="re-heading-xl">
                        Healthcare Compliance
                    </h1>
                    <p className="text-re-text-muted text-base">
                        HIPAA, HITECH, and healthcare data privacy compliance
                    </p>
                </div>
            </div>

            {/* Content */}
            <div className="re-page-narrow">

                {/* Scope Preview */}
                <section className="mb-12">
                    <h2 className="re-heading-md">
                        What&apos;s Coming
                    </h2>

                    <div className="grid gap-3">
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
                                <div className="font-semibold text-re-text-primary mb-1">{item.title}</div>
                                <div className="text-sm text-re-text-muted">{item.desc}</div>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Sample API Call */}
                <section className="mb-12">
                    <h2 className="re-heading-md">
                        <Clock className="w-5 h-5 inline align-middle mr-2" />
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
                            <span className="text-xs text-re-text-muted">POST /v1/records (Coming Soon)</span>
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
                    <h3 className="re-heading-sm">
                        Get Early Access
                    </h3>
                    <p className="text-re-text-secondary text-sm mb-5 max-w-[400px] mx-auto">
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
                        <Mail className="w-4 h-4" />
                        Request Early Access
                    </a>
                </section>

                {/* Back Link */}
                <div className="mt-12 text-center">
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
                        <FileText className="w-4 h-4" />
                        See FSMA 204 Guide (Live Now)
                    </Link>
                </div>
            </div>
        </div>
    );
}
