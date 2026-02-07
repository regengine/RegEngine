import Link from 'next/link';
import { ArrowLeft, Package, Mail, Github, FileText } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function SDKsDocsPage() {
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
                        <Package style={{ width: 28, height: 28, color: T.accent }} />
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

                    <h1 style={{ fontSize: '2.5rem', fontWeight: 700, color: '#ffffff', marginBottom: '8px' }}>
                        SDKs & Libraries
                    </h1>
                    <p style={{ color: T.textMuted, fontSize: '16px' }}>
                        Official client libraries for Python, Node.js, and more
                    </p>
                </div>
            </div>

            {/* Content */}
            <div style={{ maxWidth: '700px', margin: '0 auto', padding: '48px 24px' }}>

                {/* SDK Preview */}
                <section style={{ marginBottom: '48px' }}>
                    <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: '#ffffff', marginBottom: '16px' }}>
                        Coming Soon
                    </h2>

                    <div style={{ display: 'grid', gap: '12px' }}>
                        {[
                            { title: 'Python SDK', badge: 'pip install regengine', color: '#3776ab' },
                            { title: 'Node.js SDK', badge: 'npm install @regengine/sdk', color: '#339933' },
                            { title: 'Go SDK', badge: 'go get regengine.co/sdk', color: '#00add8' },
                            { title: 'REST Client', badge: 'OpenAPI 3.0 spec', color: '#6b7280' },
                        ].map((item) => (
                            <div key={item.title} style={{
                                padding: '20px',
                                background: T.surface,
                                borderRadius: '8px',
                                border: `1px solid ${T.border}`,
                                display: 'flex',
                                justifyContent: 'space-between',
                                alignItems: 'center',
                                opacity: 0.6,
                            }}>
                                <div style={{ fontWeight: 600, color: '#ffffff' }}>{item.title}</div>
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
                    <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: '#ffffff', marginBottom: '12px' }}>
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
                    <Github style={{ width: 32, height: 32, color: T.accent, margin: '0 auto 16px' }} />
                    <h3 style={{ fontSize: '1.3rem', fontWeight: 600, color: '#ffffff', marginBottom: '8px' }}>
                        Get Notified on Release
                    </h3>
                    <p style={{ color: T.text, fontSize: '14px', marginBottom: '20px', maxWidth: '400px', margin: '0 auto 20px' }}>
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
                        <Mail style={{ width: 16, height: 16 }} />
                        Notify Me
                    </a>
                </section>
            </div>
        </div>
    );
}
