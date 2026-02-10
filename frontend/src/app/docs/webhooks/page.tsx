import Link from 'next/link';
import { ArrowLeft, Webhook, Mail, Zap, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function WebhooksDocsPage() {
    return (
        <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.fontSans }}>
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
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
                        <Webhook style={{ width: 28, height: 28, color: T.accent }} />
                        <span style={{
                            background: 'rgba(16,185,129,0.2)',
                            color: T.accent,
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '4px',
                        }}>
                            Coming Q2 2026
                        </span>
                    </div>

                    <h1 style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                        Webhooks
                    </h1>
                    <p style={{ color: T.textMuted, fontSize: '16px' }}>
                        Real-time event notifications for compliance changes
                    </p>
                </div>
            </div>

            {/* Content */}
            <div style={{ maxWidth: '700px', margin: '0 auto', padding: '48px 24px' }}>

                {/* Event Types Preview */}
                <section style={{ marginBottom: '48px' }}>
                    <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        <Zap style={{ width: 20, height: 20, display: 'inline', verticalAlign: 'middle', marginRight: '8px' }} />
                        Planned Event Types
                    </h2>

                    <div style={{ display: 'grid', gap: '12px' }}>
                        {[
                            { event: 'record.created', desc: 'New compliance record created' },
                            { event: 'record.verified', desc: 'Record independently verified' },
                            { event: 'compliance.alert', desc: 'Regulatory change detected' },
                            { event: 'document.ingested', desc: 'New document processed' },
                            { event: 'fact.extracted', desc: 'Compliance fact extracted from document' },
                        ].map((item) => (
                            <div key={item.event} style={{
                                padding: '16px 20px',
                                background: T.surface,
                                borderRadius: '8px',
                                border: `1px solid ${T.border}`,
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                opacity: 0.6,
                            }}>
                                <code style={{
                                    background: 'rgba(16,185,129,0.2)',
                                    color: T.accent,
                                    padding: '4px 8px',
                                    borderRadius: '4px',
                                    fontSize: '12px',
                                }}>{item.event}</code>
                                <span style={{ fontSize: '13px', color: T.textMuted }}>{item.desc}</span>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Payload Preview */}
                <section style={{ marginBottom: '48px' }}>
                    <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        Sample Payload
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
                            <span style={{ fontSize: '12px', color: T.textMuted }}>POST (to your endpoint)</span>
                        </div>
                        <pre style={{
                            padding: '16px 20px',
                            margin: 0,
                            fontSize: '13px',
                            lineHeight: 1.5,
                            color: 'var(--re-text-muted)',
                        }}>
                            <code>{`{
  "id": "evt_3x7Kp9mN2vL",
  "type": "compliance.alert",
  "created": "2026-03-15T14:23:01Z",
  "data": {
    "framework": "FSMA_204",
    "change_type": "enforcement_date_updated",
    "previous_value": "2026-01-20",
    "new_value": "2028-07-20",
    "source_url": "fda.gov/..."
  }
}`}</code>
                        </pre>
                    </div>
                </section>

                {/* Notify CTA */}
                <section style={{
                    background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, transparent 100%)',
                    border: `1px solid rgba(16,185,129,0.3)`,
                    borderRadius: '12px',
                    padding: '32px',
                    textAlign: 'center',
                }}>
                    <Webhook style={{ width: 32, height: 32, color: T.accent, margin: '0 auto 16px' }} />
                    <h3 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                        Get Notified on Release
                    </h3>
                    <p style={{ color: T.text, fontSize: '14px', marginBottom: '20px', maxWidth: '400px', margin: '0 auto 20px' }}>
                        Be the first to know when webhooks are available.
                    </p>
                    <a
                        href="mailto:webhooks@regengine.co?subject=Webhooks%20Interest"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            background: T.accent,
                            color: 'white',
                            padding: '12px 24px',
                            borderRadius: '6px',
                            fontWeight: 600,
                            fontSize: '14px',
                            textDecoration: 'none',
                        }}
                    >
                        <Mail style={{ width: 16, height: 16 }} />
                        Notify Me
                    </a>
                </section>
            </div>
        </div>
    );
}
