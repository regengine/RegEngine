import Link from 'next/link';
import { ArrowLeft, Cpu, Mail, Clock, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function TechnologyDocsPage() {
    return (
        <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.fontSans }}>
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
                background: 'linear-gradient(135deg, rgba(6,182,212,0.1) 0%, transparent 50%)',
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
                        <Cpu style={{ width: 28, height: 28, color: 'var(--re-accent-cyan)' }} />
                        <span style={{
                            background: 'rgba(6,182,212,0.2)',
                            color: 'var(--re-accent-cyan)',
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '4px',
                        }}>
                            Coming Q2 2026
                        </span>
                    </div>

                    <h1 style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                        Technology Compliance
                    </h1>
                    <p style={{ color: T.textMuted, fontSize: '16px' }}>
                        SOC 2, ISO 27001, and technology governance compliance
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
                            { title: 'SOC 2 Control Mapping', desc: 'Automated evidence collection for Type II audits' },
                            { title: 'ISO 27001 ISMS', desc: 'Information security management documentation' },
                            { title: 'Policy Version Control', desc: 'Security policy lifecycle tracking' },
                            { title: 'Vendor Security Reviews', desc: 'Third-party risk assessment automation' },
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
                        Preview: SOC 2 Control Test
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
  "framework": "SOC_2",
  "data": {
    "control_id": "CC6.1",
    "control_name": "Access Control",
    "test_type": "automated",
    "result": "operating_effectively",
    "evidence_count": 12
  }
}`}</code>
                        </pre>
                    </div>
                </section>

                {/* Early Access CTA */}
                <section style={{
                    background: 'linear-gradient(135deg, rgba(6,182,212,0.15) 0%, rgba(6,182,212,0.05) 100%)',
                    border: `1px solid rgba(6,182,212,0.3)`,
                    borderRadius: '12px',
                    padding: '32px',
                    textAlign: 'center',
                }}>
                    <Mail style={{ width: 32, height: 32, color: 'var(--re-accent-cyan)', margin: '0 auto 16px' }} />
                    <h3 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                        Get Early Access
                    </h3>
                    <p style={{ color: T.text, fontSize: '14px', marginBottom: '20px', maxWidth: '400px', margin: '0 auto 20px' }}>
                        Join the waitlist to be notified when Technology compliance features launch.
                    </p>
                    <a
                        href="mailto:technology@regengine.co?subject=Technology%20Early%20Access"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            background: 'var(--re-accent-cyan)',
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
