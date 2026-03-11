import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Webhooks | RegEngine',
  description: 'Real-time event notifications for compliance changes. Planned event types and payload previews.',
};
import { ArrowLeft, Webhook, Mail, Zap, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function WebhooksDocsPage() {
    return (
        <div className="re-page">
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
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
                        <Webhook className="w-7 h-7 text-re-brand" />
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

                    <h1 className="re-heading-xl">
                        Webhooks
                    </h1>
                    <p className="text-re-text-muted text-base">
                        Real-time event notifications for compliance changes
                    </p>
                </div>
            </div>

            {/* Content */}
            <div className="re-page-narrow">

                {/* Event Types Preview */}
                <section className="mb-12">
                    <h2 className="re-heading-md">
                        <Zap className="w-5 h-5 inline align-middle mr-2" />
                        Planned Event Types
                    </h2>

                    <div className="grid gap-3">
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
                                <span className="text-[13px] text-re-text-muted">{item.desc}</span>
                            </div>
                        ))}
                    </div>
                </section>

                {/* Payload Preview */}
                <section className="mb-12">
                    <h2 className="re-heading-md">
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
                            <span className="text-xs text-re-text-muted">POST (to your endpoint)</span>
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
                    <Webhook className="w-8 h-8 text-re-brand mx-auto mb-4" />
                    <h3 className="re-heading-sm">
                        Get Notified on Release
                    </h3>
                    <p className="text-re-text-secondary text-sm mb-5 max-w-[400px] mx-auto">
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
                        <Mail className="w-4 h-4" />
                        Notify Me
                    </a>
                </section>
            </div>
        </div>
    );
}
