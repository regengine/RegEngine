import Link from 'next/link';
import { ArrowLeft, Zap, Terminal, CheckCircle, Key, FileText, Code, ArrowRight } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function QuickstartPage() {
    return (
        <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.fontSans }}>
            {/* Header */}
            <div style={{
                borderBottom: `1px solid ${T.border}`,
                padding: '24px',
            }}>
                <div style={{ maxWidth: '800px', margin: '0 auto' }}>
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
                        <Zap style={{ width: 28, height: 28, color: T.accent }} />
                        <span style={{
                            background: 'rgba(16,185,129,0.2)',
                            color: T.accent,
                            fontSize: '11px',
                            fontWeight: 600,
                            padding: '4px 10px',
                            borderRadius: '4px',
                        }}>
                            5 min setup
                        </span>
                    </div>

                    <h1 style={{ fontSize: '2.5rem', fontWeight: 700, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                        Quickstart
                    </h1>
                    <p style={{ color: T.textMuted, fontSize: '16px' }}>
                        Create your first tamper-evident compliance record in under 5 minutes
                    </p>
                </div>
            </div>

            {/* Content */}
            <div style={{ maxWidth: '800px', margin: '0 auto', padding: '48px 24px' }}>

                {/* Step 1: Get API Key */}
                <section style={{ marginBottom: '48px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
                        <div style={{
                            width: 32,
                            height: 32,
                            borderRadius: '50%',
                            background: T.accent,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 700,
                            fontSize: '14px',
                            color: 'white',
                            flexShrink: 0,
                        }}>1</div>
                        <div style={{ flex: 1 }}>
                            <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '12px' }}>
                                Get your API key
                            </h2>
                            <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
                                Sign up for a RegEngine account and generate an API key from your dashboard.
                            </p>
                            <Link
                                href="/api-keys"
                                style={{
                                    display: 'inline-flex',
                                    alignItems: 'center',
                                    gap: '8px',
                                    background: T.accent,
                                    color: 'white',
                                    padding: '10px 20px',
                                    borderRadius: '6px',
                                    fontWeight: 600,
                                    fontSize: '14px',
                                    textDecoration: 'none',
                                }}
                            >
                                <Key style={{ width: 16, height: 16 }} />
                                Get API Key
                            </Link>
                        </div>
                    </div>
                </section>

                {/* Step 2: Set Environment */}
                <section style={{ marginBottom: '48px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
                        <div style={{
                            width: 32,
                            height: 32,
                            borderRadius: '50%',
                            background: T.accent,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 700,
                            fontSize: '14px',
                            color: 'white',
                            flexShrink: 0,
                        }}>2</div>
                        <div style={{ flex: 1 }}>
                            <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '12px' }}>
                                Set your environment variable
                            </h2>
                            <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
                                Store your API key securely. Never commit it to version control.
                            </p>
                            <div style={{
                                background: 'rgba(0,0,0,0.6)',
                                borderRadius: '8px',
                                overflow: 'hidden',
                                border: `1px solid ${T.border}`,
                            }}>
                                <div style={{
                                    background: 'rgba(255,255,255,0.05)',
                                    padding: '8px 16px',
                                    borderBottom: `1px solid ${T.border}`,
                                }}>
                                    <span style={{ fontSize: '12px', color: T.textMuted }}>Terminal</span>
                                </div>
                                <pre style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: 'var(--re-text-tertiary)' }}>
                                    <code>{`export REGENGINE_API_KEY="rk_live_your_key_here"`}</code>
                                </pre>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Step 3: Create Record */}
                <section style={{ marginBottom: '48px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
                        <div style={{
                            width: 32,
                            height: 32,
                            borderRadius: '50%',
                            background: T.accent,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 700,
                            fontSize: '14px',
                            color: 'white',
                            flexShrink: 0,
                        }}>3</div>
                        <div style={{ flex: 1 }}>
                            <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '12px' }}>
                                Create your first compliance record
                            </h2>
                            <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
                                Use the <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px' }}>/v1/records</code> endpoint
                                to create a tamper-evident compliance event:
                            </p>

                            <div style={{
                                background: 'rgba(0,0,0,0.6)',
                                borderRadius: '8px',
                                overflow: 'hidden',
                                border: `1px solid ${T.border}`,
                                marginBottom: '16px',
                            }}>
                                <div style={{
                                    background: 'rgba(255,255,255,0.05)',
                                    padding: '8px 16px',
                                    borderBottom: `1px solid ${T.border}`,
                                    display: 'flex',
                                    justifyContent: 'space-between',
                                }}>
                                    <span style={{ fontSize: '12px', color: T.textMuted }}>POST /v1/records</span>
                                    <span style={{ fontSize: '12px', color: T.accent }}>bash</span>
                                </div>
                                <pre style={{
                                    padding: '20px',
                                    margin: 0,
                                    fontSize: '13px',
                                    lineHeight: 1.6,
                                    overflowX: 'auto',
                                    color: 'var(--re-text-primary)',
                                }}>
                                    <code>{`curl -X POST https://api.regengine.co/v1/records \\
  -H "Authorization: Bearer $REGENGINE_API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "type": "compliance_event",
    "framework": "FSMA_204",
    "data": {
      "event_type": "receiving",
      "lot_code": "LOT-2026-001",
      "product": "Romaine Lettuce",
      "quantity": 500,
      "unit": "cases"
    }
  }'`}</code>
                                </pre>
                            </div>

                            {/* Response */}
                            <div style={{
                                background: 'rgba(0,0,0,0.4)',
                                borderRadius: '8px',
                                overflow: 'hidden',
                                border: `1px solid ${T.border}`,
                            }}>
                                <div style={{
                                    background: 'rgba(16,185,129,0.15)',
                                    padding: '8px 16px',
                                    borderBottom: `1px solid ${T.border}`,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '8px',
                                }}>
                                    <div style={{ width: 8, height: 8, borderRadius: '50%', background: T.accent }} />
                                    <span style={{ fontSize: '12px', color: T.accent }}>201 Created</span>
                                </div>
                                <pre style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: 'var(--re-text-tertiary)' }}>
                                    <code>{`{
  "id": "rec_3x7Kp9mN2vL",
  "record_hash": "a3f2b891c4d5e6f78901a2b3c4d5e6f7...",
  "prev_hash": "7f6e5d4c3b2a19087f6e5d4c3b2a1908...",
  "chain_position": 1847,
  "created_at": "2026-02-05T14:23:01Z",
  "signature": "MEUCIQC7...base64...==",
  "public_key_id": "regengine-prod-2026-02"
}`}</code>
                                </pre>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Step 4: Verify */}
                <section style={{ marginBottom: '48px' }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
                        <div style={{
                            width: 32,
                            height: 32,
                            borderRadius: '50%',
                            background: T.accent,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontWeight: 700,
                            fontSize: '14px',
                            color: 'white',
                            flexShrink: 0,
                        }}>4</div>
                        <div style={{ flex: 1 }}>
                            <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '12px' }}>
                                Verify your record
                            </h2>
                            <p style={{ color: T.text, lineHeight: 1.7, marginBottom: '16px' }}>
                                Every record is cryptographically hashed. Verify the integrity independently:
                            </p>

                            <div style={{
                                background: 'rgba(0,0,0,0.6)',
                                borderRadius: '8px',
                                overflow: 'hidden',
                                border: `1px solid ${T.border}`,
                            }}>
                                <div style={{
                                    background: 'rgba(255,255,255,0.05)',
                                    padding: '8px 16px',
                                    borderBottom: `1px solid ${T.border}`,
                                }}>
                                    <span style={{ fontSize: '12px', color: T.textMuted }}>Terminal</span>
                                </div>
                                <pre style={{ padding: '16px 20px', margin: 0, fontSize: '13px', lineHeight: 1.5, color: 'var(--re-text-tertiary)' }}>
                                    <code>{`python verify_chain.py --record rec_3x7Kp9mN2vL

# Output:
# ✓ Record rec_3x7Kp9mN2vL verified
# ✓ Record hash: a3f2b891c4d5e6f78901a2b3c4d5e6f7...
# ✓ Prev hash: 7f6e5d4c3b2a19087f6e5d4c3b2a1908...
# ✓ Chain position: 1847
# ✓ Signature valid (key: regengine-prod-2026-02)`}</code>
                                </pre>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Success Box */}
                <div style={{
                    background: 'rgba(16,185,129,0.1)',
                    border: `1px solid rgba(16,185,129,0.3)`,
                    borderRadius: '8px',
                    padding: '24px',
                    marginBottom: '48px',
                }}>
                    <div style={{ display: 'flex', alignItems: 'flex-start', gap: '16px' }}>
                        <CheckCircle style={{ width: 24, height: 24, color: T.accent, flexShrink: 0 }} />
                        <div>
                            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                                You&apos;re all set!
                            </h3>
                            <p style={{ color: T.text, fontSize: '14px', margin: 0 }}>
                                You&apos;ve created your first tamper-evident compliance record. The record is now
                                part of an immutable chain that can be independently verified by auditors.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Next Steps */}
                <section>
                    <h2 style={{ fontSize: '1.3rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '16px' }}>
                        Next Steps
                    </h2>

                    <div style={{ display: 'grid', gap: '12px' }}>
                        {[
                            { title: 'FSMA 204 Guide', desc: 'Learn about CTEs, KDEs, and FDA Request Mode', href: '/docs/fsma-204', icon: FileText },
                            { title: 'API Reference', desc: 'Explore all available endpoints', href: '/docs/api', icon: Code },
                            { title: 'Authentication', desc: 'Learn about API key management', href: '/docs/authentication', icon: Key },
                        ].map((item) => (
                            <Link key={item.href} href={item.href} style={{ textDecoration: 'none' }}>
                                <div style={{
                                    padding: '16px 20px',
                                    background: T.surface,
                                    borderRadius: '8px',
                                    border: `1px solid ${T.border}`,
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: '16px',
                                }}>
                                    <item.icon style={{ width: 20, height: 20, color: T.accent }} />
                                    <div style={{ flex: 1 }}>
                                        <div style={{ fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '2px' }}>{item.title}</div>
                                        <div style={{ fontSize: '13px', color: T.textMuted }}>{item.desc}</div>
                                    </div>
                                    <ArrowRight style={{ width: 16, height: 16, color: T.textMuted }} />
                                </div>
                            </Link>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    );
}
