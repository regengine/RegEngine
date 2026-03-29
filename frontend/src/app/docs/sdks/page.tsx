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
        <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
            {/* Header */}
            <div className="p-6" style={{ borderBottom: `1px solid ${T.border}` }}>
                <div className="max-w-[700px] mx-auto">
                    <Link
                        href="/docs"
                        className="inline-flex items-center gap-2 text-sm no-underline mb-4"
                        style={{ color: T.accent }}
                    >
                        <ArrowLeft className="w-4 h-4" />
                        Back to Docs
                    </Link>

                    <div className="flex items-center gap-3 mb-3">
                        <Package className="w-7 h-7 text-re-brand" />
                        <span className="bg-[rgba(16,185,129,0.2)] text-[11px] font-semibold px-2.5 py-1 rounded" style={{ color: T.accent }}>
                            SDK Access
                        </span>
                    </div>

                    <h1 className="text-[1.75rem] sm:text-[2.5rem] font-bold text-[var(--re-text-primary)] mb-2">
                        SDKs & Libraries
                    </h1>
                    <p className="text-re-text-muted text-base">
                        Official client libraries for Python, Node.js, and more
                    </p>
                </div>
            </div>

            {/* Content */}
            <div className="max-w-[700px] mx-auto py-12 px-6">

                {/* SDK Preview */}
                <section className="mb-12">
                    <h2 className="text-[1.1rem] sm:text-[1.3rem] font-semibold text-[var(--re-text-primary)] mb-4">
                        Planned SDK Releases
                    </h2>

                    <div className="grid gap-3">
                        {[
                            { title: 'Python SDK', badge: 'Planned', color: '#3776ab' },
                            { title: 'Node.js SDK', badge: 'Planned', color: '#339933' },
                            { title: 'Go SDK', badge: 'Planned', color: '#00add8' },
                            { title: 'REST Client', badge: 'Available now — OpenAPI 3.0 spec', color: 'var(--re-text-muted)' },
                        ].map((item) => (
                            <div key={item.title} className="p-5 rounded-lg flex justify-between items-center" style={{
                                background: T.surface,
                                border: `1px solid ${T.border}`,
                                opacity: item.badge === 'Planned' ? 0.6 : 1,
                            }}>
                                <div className="font-semibold text-[var(--re-text-primary)]">{item.title}</div>
                                <code className="bg-black/30 px-2 py-1 rounded text-xs" style={{ color: item.color }}>{item.badge}</code>
                            </div>
                        ))}
                    </div>
                </section>

                {/* What to use now */}
                <section className="rounded-lg p-6 mb-12" style={{ background: T.surface, border: `1px solid ${T.border}` }}>
                    <h3 className="text-[1.1rem] font-semibold text-[var(--re-text-primary)] mb-3">
                        What to Use Now
                    </h3>
                    <p className="text-sm mb-4" style={{ color: T.text }}>
                        Until SDKs are released, use our REST API directly. All endpoints accept JSON and return JSON.
                    </p>
                    <Link
                        href="/docs/api"
                        className="inline-flex items-center gap-2 text-sm no-underline"
                        style={{ color: T.accent }}
                    >
                        View API Reference →
                    </Link>
                </section>

                {/* Notify CTA */}
                <section className="bg-gradient-to-br from-[rgba(16,185,129,0.1)] to-transparent border border-[rgba(16,185,129,0.3)] rounded-xl p-8 text-center">
                    <Github className="w-8 h-8 text-re-brand mx-auto mb-4" />
                    <h3 className="text-[0.95rem] sm:text-[1.1rem] font-semibold text-[var(--re-text-primary)] mb-2">
                        Get Notified on Release
                    </h3>
                    <p className="text-re-text-secondary text-sm mb-5 max-w-[400px] mx-auto">
                        Be the first to know when our official SDKs are available.
                    </p>
                    <a
                        href="mailto:sdk@regengine.co?subject=SDK%20Release%20Notification"
                        className="inline-flex items-center gap-2 text-white px-6 py-3 rounded-md font-semibold text-sm no-underline"
                        style={{ background: T.accent }}
                    >
                        <Mail className="w-4 h-4" />
                        Notify Me
                    </a>
                </section>
            </div>
        </div>
    );
}
