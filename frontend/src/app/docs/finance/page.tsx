import Link from 'next/link';
import { ArrowLeft, TrendingUp, Mail, Clock, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function FinanceDocsPage() {
    return (
        <div className="re-page">
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
                background: 'linear-gradient(135deg, rgba(59,130,246,0.1) 0%, transparent 50%)',
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
                        <TrendingUp style={{ width: 28, height: 28, color: 'var(--re-accent-blue)' }} />
                        <span style={{
                            background: 'rgba(59,130,246,0.2)',
                            color: 'var(--re-accent-blue)',
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '4px',
                        }}>
                            Coming Q2 2026
                        </span>
                    </div>

                    <h1 className="re-heading-xl">
                        Finance Compliance
                    </h1>
                    <p className="text-re-text-muted text-base">
                        SEC, SOX 404, and financial regulatory compliance automation
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
                            { title: 'SOX 404 Controls', desc: 'Automated control testing and documentation' },
                            { title: 'SEC Filing Tracking', desc: 'Monitor 10-K, 10-Q, and 8-K deadlines' },
                            { title: 'Audit Trail Export', desc: 'One-click evidence packages for external auditors' },
                            { title: 'Material Change Detection', desc: 'Real-time alerts on regulatory updates' },
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
                        Preview: SOX Control Event
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
                            <span className="text-xs text-re-text-muted">POST /v1/records (Beta Endpoint)</span>
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
  "framework": "SOX_404",
  "data": {
    "control_id": "CTRL-FIN-001",
    "control_name": "Revenue Recognition",
    "test_result": "effective",
    "tested_by": "internal_audit",
    "evidence_ref": "doc_a3f2b891"
  }
}`}</code>
                        </pre>
                    </div>
                </section>

                {/* Early Access CTA */}
                <section style={{
                    background: 'linear-gradient(135deg, rgba(59,130,246,0.15) 0%, rgba(59,130,246,0.05) 100%)',
                    border: `1px solid rgba(59,130,246,0.3)`,
                    borderRadius: '12px',
                    padding: '32px',
                    textAlign: 'center',
                }}>
                    <Mail style={{ width: 32, height: 32, color: 'var(--re-accent-blue)', margin: '0 auto 16px' }} />
                    <h3 className="re-heading-sm">
                        Get Early Access
                    </h3>
                    <p className="text-re-text-secondary text-sm mb-5 max-w-[400px] mx-auto">
                        Join the waitlist to be notified when Finance compliance features launch.
                    </p>
                    <a
                        href="mailto:finance@regengine.co?subject=Finance%20Early%20Access"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            background: 'var(--re-accent-blue)',
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
