import Link from 'next/link';
import { ArrowLeft, Zap, Mail, Clock, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function EnergyDocsPage() {
    return (
        <div className="re-page">
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
                background: 'linear-gradient(135deg, rgba(234,179,8,0.1) 0%, transparent 50%)',
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
                        <Zap style={{ width: 28, height: 28, color: 'var(--re-warning)' }} />
                        <span style={{
                            background: 'rgba(234,179,8,0.2)',
                            color: 'var(--re-warning)',
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '4px',
                        }}>
                            Coming Q2 2026
                        </span>
                    </div>

                    <h1 className="re-heading-xl">
                        Energy Compliance
                    </h1>
                    <p className="text-re-text-muted text-base">
                        NERC CIP-013, supply chain risk, and grid security compliance
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
                            { title: 'NERC CIP-013 Tracking', desc: 'Supply chain risk management evidence' },
                            { title: 'Vendor Risk Assessment', desc: 'Automated third-party security reviews' },
                            { title: 'BES Cyber System Inventory', desc: 'Critical asset compliance documentation' },
                            { title: 'Audit Evidence Export', desc: 'Regional entity audit packages' },
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
                        <Clock style={{ width: 20, height: 20, display: 'inline', verticalAlign: 'middle', marginRight: '8px' }} />
                        Preview: Vendor Assessment
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
  "framework": "NERC_CIP_013",
  "data": {
    "vendor_id": "VND-001",
    "vendor_name": "Grid Components Inc",
    "assessment_type": "annual_review",
    "risk_level": "medium",
    "mitigation_plan": "doc_ref_123"
  }
}`}</code>
                        </pre>
                    </div>
                </section>

                {/* Early Access CTA */}
                <section style={{
                    background: 'linear-gradient(135deg, rgba(234,179,8,0.15) 0%, rgba(234,179,8,0.05) 100%)',
                    border: `1px solid rgba(234,179,8,0.3)`,
                    borderRadius: '12px',
                    padding: '32px',
                    textAlign: 'center',
                }}>
                    <Mail style={{ width: 32, height: 32, color: 'var(--re-warning)', margin: '0 auto 16px' }} />
                    <h3 className="re-heading-sm">
                        Get Early Access
                    </h3>
                    <p style={{ color: T.text, fontSize: '14px', marginBottom: '20px', maxWidth: '400px', margin: '0 auto 20px' }}>
                        Join the waitlist to be notified when Energy compliance features launch.
                    </p>
                    <a
                        href="mailto:energy@regengine.co?subject=Energy%20Early%20Access"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            background: 'var(--re-warning)',
                            color: 'black',
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
