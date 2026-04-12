import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Quickstart | RegEngine',
  description: 'Create your first tamper-evident compliance record in under 5 minutes with the RegEngine API.',
};
import { ArrowLeft, Zap, Terminal, CheckCircle, Key, FileText, Code, ArrowRight } from 'lucide-react';
import { T as _T } from '@/lib/design-tokens';

const T = {
  ..._T,
  heading: 'var(--re-text-primary)',
  text: 'var(--re-text-secondary)',
  textMuted: 'var(--re-text-muted)',
  textDim: 'var(--re-text-muted)',
  surface: 'var(--re-surface-card)',
  border: 'var(--re-surface-border)',
};
import { CodeBlock } from '@/components/ui/code-block';

export default function QuickstartPage() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* Header */}
            <div className="p-6" style={{ borderBottom: `1px solid ${T.border}` }}>
                <div className="max-w-[800px] mx-auto">
                    <Link
                        href="/docs"
                        className="inline-flex items-center gap-2 text-sm no-underline mb-4"
                        style={{ color: T.accent }}
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Docs
                    </Link>

                    <div className="flex items-center gap-3 mb-3">
                        <Zap className="w-7 h-7 text-re-brand" />
                        <span className="bg-[rgba(16,185,129,0.2)] text-[11px] font-semibold px-2.5 py-1 rounded" style={{ color: T.accent }}>
                            5 min setup
                        </span>
                    </div>

                    <h1 className="text-[1.75rem] sm:text-[2.5rem] font-bold text-[var(--re-text-primary)] mb-2">
                        Quickstart
                    </h1>
                    <p className="text-re-text-muted text-base">
                        Create your first tamper-evident compliance record in under 5 minutes
                    </p>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-[800px] mx-auto px-6 py-12">

                {/* Step 1: Get API Key */}
                <section className="mb-12">
                    <div className="flex items-start gap-4">
                        <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm text-white shrink-0" style={{ background: T.accent }}>1</div>
                        <div className="flex-1">
                            <h2 className="text-[0.95rem] sm:text-[1.1rem] font-semibold text-[var(--re-text-primary)] mb-2">
                                Get your API key
                            </h2>
                            <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                                Sign up for a RegEngine account and generate an API key from your dashboard.
                            </p>
                            <Link
                                href="/api-keys"
                                className="inline-flex items-center gap-2 text-white px-5 py-2.5 rounded-md font-semibold text-sm no-underline"
                                style={{ background: T.accent }}
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
                        <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm text-white shrink-0" style={{ background: T.accent }}>2</div>
                        <div className="flex-1">
                            <h2 className="text-[0.95rem] sm:text-[1.1rem] font-semibold text-[var(--re-text-primary)] mb-2">
                                Set your environment variable
                            </h2>
                            <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                                Store your API key securely. Never commit it to version control.
                            </p>
                            <CodeBlock
                                code={`export REGENGINE_API_KEY="rge_your_key_here"
export REGENGINE_TENANT_ID="11111111-1111-1111-1111-111111111111"`}
                                language="bash"
                            />
                        </div>
                    </div>
                </section>

                {/* Step 3: Create Record */}
                <section className="mb-12">
                    <div className="flex items-start gap-4">
                        <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm text-white shrink-0" style={{ background: T.accent }}>3</div>
                        <div className="flex-1">
                            <h2 className="text-[0.95rem] sm:text-[1.1rem] font-semibold text-[var(--re-text-primary)] mb-2">
                                Create your first compliance record
                            </h2>
                            <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                                Use the <code className="bg-black/30 px-1.5 py-0.5 rounded">/api/v1/webhooks/ingest</code> endpoint
                                to create a compliant traceability event:
                            </p>

                            <div className="mb-4">
                                <CodeBlock
                                    code={`curl -X POST https://regengine.co/api/v1/webhooks/ingest \\
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
  }'`}
                                    language="curl"
                                />
                            </div>

                            {/* Response */}
                            <CodeBlock
                                code={`{
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
}`}
                                language="json"
                            />
                        </div>
                    </div>
                </section>

                {/* Step 4: Verify */}
                <section className="mb-12">
                    <div className="flex items-start gap-4">
                        <div className="w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm text-white shrink-0" style={{ background: T.accent }}>4</div>
                        <div className="flex-1">
                            <h2 className="text-[0.95rem] sm:text-[1.1rem] font-semibold text-[var(--re-text-primary)] mb-2">
                                Verify your record
                            </h2>
                            <p className="text-[var(--re-text-secondary)] leading-[1.7] mb-4">
                                Every ingested event is cryptographically hashed. Verify integrity independently from an export file:
                            </p>

                            <CodeBlock
                                code={`python verify_chain.py --file export_2026_02.json --offline

# Output:
# ✓ Chain integrity verified
# ✓ 1847 records validated
# ✓ No hash mismatches detected`}
                                language="bash"
                            />
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
                    <h2 className="text-[1.1rem] sm:text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">
                        Next Steps
                    </h2>

                    <div className="grid gap-3">
                        {[
                            { title: 'FSMA 204 Guide', desc: 'Learn about CTEs, KDEs, and FDA Request Mode', href: '/docs/fsma-204', icon: FileText },
                            { title: 'API Reference', desc: 'Explore all available endpoints', href: '/docs/api', icon: Code },
                            { title: 'Authentication', desc: 'Learn about API key management', href: '/docs/authentication', icon: Key },
                        ].map((item) => (
                            <Link key={item.href} href={item.href} className="no-underline">
                                <div className="px-5 py-4 rounded-lg flex items-center gap-4" style={{ background: T.surface, border: `1px solid ${T.border}` }}>
                                    <item.icon className="w-5 h-5 text-re-brand" />
                                    <div className="flex-1">
                                        <div className="font-semibold text-[var(--re-text-primary)] mb-0.5">{item.title}</div>
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
