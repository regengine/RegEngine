import type { Metadata } from 'next';
import Link from 'next/link';

export const metadata: Metadata = {
  title: 'Documentation | RegEngine',
  description: 'RegEngine FSMA 204 API documentation. Quickstart guides, endpoint references, SDKs, and food traceability implementation guides.',
};
import { ArrowRight, Key, Code, FileText, UtensilsCrossed } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function DocsHomePage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">
      {/* Code-First Hero - Drop into code within 10 seconds */}
      <div className="bg-gradient-to-br from-[rgba(16,185,129,0.08)] to-[rgba(6,182,212,0.05)] px-6 py-12" style={{ borderBottom: `1px solid ${T.border}` }}>
        <div className="max-w-[1000px] mx-auto">
          <div className="flex items-center gap-3 mb-4">
            <div className="bg-[rgba(16,185,129,0.2)] px-3 py-1.5 rounded text-xs font-semibold uppercase tracking-wide" style={{ color: T.accent }}>
              Quickstart
            </div>
          </div>

          <h1 className="text-[2rem] font-bold text-[var(--re-text-primary)] mb-2 leading-tight">
            Create a compliance record
          </h1>
          <p className="mb-6 text-[15px]" style={{ color: T.textMuted }}>
            Your first tamper-evident record in under 60 seconds
          </p>

          {/* Code Block - The star of the show */}
          <div className="bg-black/60 rounded-lg overflow-hidden" style={{ border: `1px solid ${T.border}` }}>
            <div className="bg-white/5 px-4 py-2 flex justify-between items-center" style={{ borderBottom: `1px solid ${T.border}` }}>

              <span className="text-xs text-re-text-muted">POST /api/v1/webhooks/ingest</span>
              <span className="text-xs text-re-brand">bash</span>
            </div>
            <pre className="p-5 m-0 text-[13px] leading-relaxed overflow-x-auto text-[var(--re-text-primary)]">

              <code>{`curl -X POST https://www.regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: YOUR_API_KEY" \\
  -H "X-Tenant-ID: YOUR_TENANT_UUID" \\
  -H "Content-Type: application/json" \\
  -d '{
    "source": "erp",
    "events": [{
      "cte_type": "receiving",
      "traceability_lot_code": "00012345678901-LOT-2026-001",
      "product_description": "Romaine Lettuce",
      "quantity": 500,
      "unit_of_measure": "cases",
      "location_name": "Distribution Center #4",
      "timestamp": "2026-02-05T08:30:00Z",
      "kdes": {
        "receive_date": "2026-02-05",
        "receiving_location": "Distribution Center #4"
      }
    }]
  }'`}</code>
            </pre>
          </div>

          {/* Response Preview */}
          <div className="bg-black/40 rounded-lg mt-3 overflow-hidden" style={{ border: `1px solid ${T.border}` }}>
            <div className="bg-[rgba(16,185,129,0.1)] px-4 py-2 flex items-center gap-2" style={{ borderBottom: `1px solid ${T.border}` }}>

              <div className="w-2 h-2 rounded-full bg-re-brand" />
              <span className="text-xs text-re-brand">201 Created</span>
            </div>
            <pre className="px-5 py-4 m-0 text-xs leading-normal text-[var(--re-text-tertiary)]">

              <code>{`{
  "accepted": 1,
  "rejected": 0,
  "total": 1,
  "events": [{
    "traceability_lot_code": "00012345678901-LOT-2026-001",
    "cte_type": "receiving",
    "status": "accepted",
    "event_id": "a1b2c3d4-...",
    "sha256_hash": "a3f2b891c4d5e6f7...",
    "chain_hash": "7f6e5d4c3b2a1908..."
  }]
}`}</code>
            </pre>
          </div>

          {/* Get API Key CTA */}
          <div className="mt-6 flex gap-3 flex-wrap">
            <Link
              href="/developer/register"
              className="inline-flex items-center gap-2 text-white px-6 py-3 rounded-md font-semibold text-sm no-underline"
              style={{ background: T.accent }}
            >
              <Key className="w-4 h-4" />
              Get Developer Access
            </Link>
            <Link
              href="/docs/fsma-204"
              className="inline-flex items-center gap-2 bg-white/10 text-[var(--re-text-primary)] px-6 py-3 rounded-md font-semibold text-sm no-underline"
              style={{ border: `1px solid ${T.border}` }}
            >
              FSMA 204 Guide
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </div>
      </div>

      <div className="max-w-[1000px] mx-auto px-6 py-12">

        {/* Developer Portal CTA */}
        <section className="mb-12">
          <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: T.textMuted }}>
            Developer Resources
          </h2>
          <Link
            href="/developer/register"
            className="block p-6 rounded-lg no-underline max-w-full"
            style={{ background: T.surface, border: `1px solid ${T.border}` }}
          >
            <div className="flex items-center gap-4 flex-wrap">
              <div className="bg-[rgba(16,185,129,0.15)] rounded-lg p-3">
                <Code className="w-6 h-6" style={{ color: T.accent }} />
              </div>
              <div>
                <div className="font-semibold text-[var(--re-text-primary)] text-base mb-1">
                  Developer Portal
                </div>
                <div className="text-[13px]" style={{ color: T.textMuted }}>
                  API reference, SDKs, quickstart guides, webhooks, and API key management. Request access to get started.
                </div>
              </div>
              <ArrowRight className="w-5 h-5 ml-auto" style={{ color: T.textMuted }} />
            </div>
          </Link>
        </section>

        {/* Row 3: FSMA Guide */}
        <section className="mb-12">
          <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: T.textMuted }}>
            FSMA Guide
          </h2>
          <Link
            href="/docs/fsma-204"
            className="block p-5 rounded-lg relative bg-[rgba(16,185,129,0.1)] border border-[rgba(16,185,129,0.3)] no-underline max-w-xs"
          >
            <div className="absolute top-3 right-3 text-white text-[10px] font-semibold px-2 py-0.5 rounded uppercase" style={{ background: T.accent }}>
              Current
            </div>
            <UtensilsCrossed className="w-5 h-5 mb-3" style={{ color: T.accent }} />
            <div className="font-semibold text-[var(--re-text-primary)] text-[15px] mb-1">Food &amp; Beverage</div>
            <div className="text-[13px]" style={{ color: T.textMuted }}>FSMA 204</div>
          </Link>
        </section>

        {/* Popular Pages - only public docs */}
        <section className="mb-12">
          <h2 className="text-xs font-semibold uppercase tracking-wider mb-4" style={{ color: T.textMuted }}>
            Resources
          </h2>
          <div className="grid grid-cols-3 gap-3">
            {[
              { name: 'FSMA 204 Guide', href: '/docs/fsma-204', icon: UtensilsCrossed },
              { name: 'Developer Portal', href: '/developer/register', icon: Code },
              { name: 'Contact Support', href: 'mailto:support@regengine.co', icon: FileText },
            ].map((item) => (
              <Link
                key={item.name}
                href={item.href}
                className="px-5 py-4 bg-transparent rounded-lg no-underline flex items-center gap-3"
                style={{ border: `1px solid ${T.border}` }}
              >
                <item.icon className="w-4 h-4 text-re-text-muted" />
                <span className="text-[var(--re-text-primary)] text-sm">{item.name}</span>
              </Link>
            ))}
          </div>
        </section>

        {/* Footer: verify_chain.py tagline */}
        <footer className="pt-8 flex justify-between items-center flex-wrap gap-4" style={{ borderTop: `1px solid ${T.border}` }}>
          <div>
            <code className="bg-white/5 px-4 py-2 rounded-md text-[13px]" style={{ color: T.textMuted, fontFamily: T.fontMono }}>
              python verify_chain.py --audit
            </code>
            <span className="ml-4 text-sm" style={{ color: T.textMuted }}>
              Don&apos;t trust, verify.
            </span>
          </div>
          <div className="flex gap-6">
            <Link href="/developer/register" className="text-re-text-muted text-[13px] no-underline">
              Developer Portal
            </Link>
            <Link href="/docs/fsma-204" className="text-re-text-muted text-[13px] no-underline">
              FSMA 204
            </Link>
            <a href="mailto:support@regengine.co" className="text-re-text-muted text-[13px] no-underline">
              Support
            </a>
          </div>
        </footer>
      </div>
    </div>
  );
}
