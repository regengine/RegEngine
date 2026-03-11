import Link from 'next/link';
import { ArrowLeft, Zap, Terminal, CheckCircle, Key, FileText, Code, ArrowRight } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function QuickstartPage() {
    return (
        <div className="re-page">
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
                        <ArrowLeft className="w-4 h-4" />
                        Back to Docs
                    </Link>

                    <div className="flex items-center gap-3 mb-3">
                        <Zap className="w-7 h-7 text-re-brand" />
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

                    <h1 className="re-heading-xl">
                        Quickstart
                    </h1>
                    <p className="text-re-text-muted text-base">
                        Create your first tamper-evident compliance record in under 5 minutes
                    </p>
                </div>
            </div>

            {/* Content */}
            <div style={{ maxWidth: '800px', margin: '0 auto', padding: '48px 24px' }}>

                {/* Step 1: Get API Key */}
                <section className="mb-12">
                    <div className="flex items-start gap-4">
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
                        <div className="flex-1">
                            <h2 className="re-heading-sm">
                                Get your API key
                            </h2>
                            <p className="re-body">
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
                                <Key className="w-4 h-4" />
                                Get API Key
                            </Link>
                        </div>
                    </div>
                </section>

                {/* Step 2: Set Environment */}
                <section className="mb-12">
                    <div className="flex items-start gap-4">
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
                        <div className="flex-1">
                            <h2 className="re-heading-sm">
                                Set your environment variable
                            </h2>
                            <p className="re-body">
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
                                    <span className="text-xs text-re-text-muted">Terminal</span>
                                </div>
                                <pre className="re-code-block">
                                    <code>{`export REGENGINE_API_KEY="rge_your_key_here"
export REGENGINE_TENANT_ID="11111111-1111-1111-1111-111111111111"`}</code>
                                </pre>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Step 3: Create Record */}
                <section className="mb-12">
                    <div className="flex items-start gap-4">
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
                        <div className="flex-1">
                            <h2 className="re-heading-sm">
                                Create your first compliance record
                            </h2>
                            <p className="re-body">
                                Use the <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px' }}>/api/v1/webhooks/ingest</code> endpoint
                                to create a compliant traceability event:
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
                                    <span className="text-xs text-re-text-muted">POST /api/v1/webhooks/ingest</span>
                                    <span className="text-xs text-re-brand">bash</span>
                                </div>
                                <pre style={{
                                    padding: '20px',
                                    margin: 0,
                                    fontSize: '13px',
                                    lineHeight: 1.6,
                                    overflowX: 'auto',
                                    color: 'var(--re-text-primary)',
                                }}>
                                    <code>{`curl -X POST https://www.regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: $REGENGINE_API_KEY" \\
  -H "X-Tenant-ID: $REGENGINE_TENANT_ID" \\
  -H "Content-Type: application/json" \\
  -d '{
    "source": "erp",
    "events": [
      {
        "cte_type": "receiving",
        "traceability_lot_code": "00012345678901-LOT-2026-001",
        "product_description": "Romaine Lettuce",
        "quantity": 500,
        "unit_of_measure": "cases",
        "location_name": "Distribution Center #4",
        "timestamp": "2026-02-05T14:23:00Z",
        "kdes": {
          "receive_date": "2026-02-05",
          "receiving_location": "Distribution Center #4"
        }
      }
    ]
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
                                    <div className="w-2 h-2 rounded-full bg-re-brand" />
                                    <span className="text-xs text-re-brand">201 Created</span>
                                </div>
                                <pre className="re-code-block">
                                    <code>{`{
  "accepted": 1,
  "rejected": 0,
  "total": 1,
  "events": [
    {
      "traceability_lot_code": "00012345678901-LOT-2026-001",
      "cte_type": "receiving",
      "status": "accepted",
      "event_id": "a1b2c3d4-...",
      "sha256_hash": "a3f2b891c4d5e6f7...",
      "chain_hash": "7f6e5d4c3b2a1908..."
    }
  ]
}`}</code>
                                </pre>
                            </div>
                        </div>
                    </div>
                </section>

                {/* Step 4: Verify */}
                <section className="mb-12">
                    <div className="flex items-start gap-4">
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
                        <div className="flex-1">
                            <h2 className="re-heading-sm">
                                Verify your record
                            </h2>
                            <p className="re-body">
                                Every ingested event is cryptographically hashed. Verify integrity independently from an export file:
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
                                    <span className="text-xs text-re-text-muted">Terminal</span>
                                </div>
                                <pre className="re-code-block">
                                    <code>{`python verify_chain.py --file export_2026_02.json --offline

# Output:
# ✓ Chain integrity verified
# ✓ 1847 records validated
# ✓ No hash mismatches detected`}</code>
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
                    <div className="flex items-start gap-4">
                        <CheckCircle style={{ width: 24, height: 24, color: T.accent, flexShrink: 0 }} />
                        <div>
                            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '8px' }}>
                                You&apos;re all set!
                            </h3>
                            <p className="text-re-text-secondary text-sm m-0">
                                You&apos;ve created your first tamper-evident compliance record. The record is now
                                part of an immutable chain that can be independently verified by auditors.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Next Steps */}
                <section>
                    <h2 className="re-heading-md">
                        Next Steps
                    </h2>

                    <div className="grid gap-3">
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
                                    <item.icon className="w-5 h-5 text-re-brand" />
                                    <div className="flex-1">
                                        <div style={{ fontWeight: 600, color: 'var(--re-text-primary)', marginBottom: '2px' }}>{item.title}</div>
                                        <div className="text-[13px] text-re-text-muted">{item.desc}</div>
                                    </div>
                                    <ArrowRight className="w-4 h-4 text-re-text-muted" />
                                </div>
                            </Link>
                        ))}
                    </div>
                </section>
            </div>
        </div>
    );
}
