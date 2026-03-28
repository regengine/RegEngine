import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'SDKs & Libraries | RegEngine',
  description: 'Official RegEngine client libraries for Python, Node.js, and Go, plus REST API usage guidance.',
};
import { ArrowLeft, Package, Mail, Github, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function SDKsDocsPage() {
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
                        <Package className="w-7 h-7 text-re-brand" />
                        <span style={{
                            background: 'rgba(16,185,129,0.2)',
                            color: T.accent,
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '4px',
                        }}>
                            SDK Access
                        </span>
                    </div>

                    <h1 className="re-heading-xl">
                        SDKs & Libraries
                    </h1>
                    <p className="text-re-text-muted text-base">
                        Official client libraries for Python, Node.js, and more
                    </p>
                </div>
            </div>

            {/* Content */}
            <div className="re-page-narrow">

                {/* SDK Preview */}
                <section className="mb-12">
                    <h2 className="re-heading-md">
                        Planned SDK Releases
                    </h2>

                    <div className="grid gap-3">
                        {[
                            { title: 'Python SDK', badge: 'Planned', color: '#3776ab' },
                            { title: 'Node.js SDK', badge: 'Planned', color: '#339933' },
                            { title: 'Go SDK', badge: 'Planned', color: '#00add8' },
                            { title: 'REST Client', badge: 'Available now — OpenAPI 3.0 spec', color: 'var(--re-text-muted)' },
                        ].map((item) => (
                            <div key={item.title} style={{
                                padding: '20px',
                                background: T.surface,
                                borderRadius: '8px',
                                border: `1px solid ${T.border}`,
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                opacity: item.badge === 'Planned' ? 0.6 : 1,
                            }}>
                                <div style={{ fontWeight: 600, color: 'var(--re-text-primary)' }}>{item.title}</div>
                                <code style={{
                                    background: 'rgba(0,0,0,0.3)',
                                    padding: '4px 8px',
                                    borderRadius: '4px',
                                    fontSize: '12px',
                                    color: item.color,
                                }}>{item.badge}</code>
                            </div>
                        ))}
                    </div>
                </section>

                {/* What to use now */}
                <section style={{
                    background: T.surface,
                    border: `1px solid ${T.border}`,
                    borderRadius: '8px',
                    padding: '24px',
                    marginBottom: '48px',
                }}>
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '12px' }}>
                        What to Use Now
                    </h3>
                    <p style={{ color: T.text, fontSize: '14px', marginBottom: '16px' }}>
                        Until SDKs are released, use our REST API directly. All endpoints accept JSON and return JSON.
                    </p>
                    <Link
                        href="/docs/api"
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '8px',
                            color: T.accent,
                            fontSize: '14px',
                            textDecoration: 'none',
                        }}
                    >
                        View API Reference →
                    </Link>
                </section>

                {/* Notify CTA */}
                <section style={{
                    background: 'linear-gradient(135deg, rgba(16,185,129,0.1) 0%, transparent 100%)',
                    border: `1px solid rgba(16,185,129,0.3)`,
                    borderRadius: '12px',
                    padding: '32px',
                    textAlign: 'center',
                }}>
                    <Github className="w-8 h-8 text-re-brand mx-auto mb-4" />
                    <h3 className="re-heading-sm">
                        Get Notified on Release
                    </h3>
                    <p className="text-re-text-secondary text-sm mb-5 max-w-[400px] mx-auto">
                        Be the first to know when our official SDKs are available.
                    </p>
                    <a
                        href="mailto:sdk@regengine.co?subject=SDK%20Release%20Notification"
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
