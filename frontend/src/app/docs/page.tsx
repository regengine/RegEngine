import Link from 'next/link';
import { ArrowRight, Key, Book, Code, Webhook, Zap, TrendingUp, Cpu, Atom, ShieldCheck, AlertCircle, FileText, UtensilsCrossed } from 'lucide-react';
import { T } from '@/lib/design-tokens';

export default function DocsHomePage() {
  return (
    <div style={{ minHeight: '100vh', background: T.bg, color: T.text, fontFamily: T.fontSans }}>
      {/* Code-First Hero - Drop into code within 10 seconds */}
      <div style={{
        background: 'linear-gradient(135deg, rgba(16,185,129,0.08) 0%, rgba(6,182,212,0.05) 100%)',
        borderBottom: `1px solid ${T.border}`,
        padding: '48px 24px',
      }}>
        <div style={{ maxWidth: '1000px', margin: '0 auto' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '16px' }}>
            <div style={{
              background: 'rgba(16,185,129,0.2)',
              padding: '6px 12px',
              borderRadius: '4px',
              fontSize: '12px',
              fontWeight: 600,
              color: T.accent,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
            }}>
              Quickstart
            </div>
          </div>

          <h1 style={{
            fontSize: '2rem',
            fontWeight: 700,
            color: '#ffffff',
            marginBottom: '8px',
            lineHeight: 1.2,
          }}>
            Create a compliance record
          </h1>
          <p style={{ color: T.textMuted, marginBottom: '24px', fontSize: '15px' }}>
            Your first tamper-evident record in under 60 seconds
          </p>

          {/* Code Block - The star of the show */}
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
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
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
              color: '#e2e8f0',
            }}>
              <code>{`curl -X POST https://api.regengine.co/v1/records \\
  -H "Authorization: Bearer YOUR_API_KEY" \\
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

          {/* Response Preview */}
          <div style={{
            background: 'rgba(0,0,0,0.4)',
            borderRadius: '8px',
            marginTop: '12px',
            border: `1px solid ${T.border}`,
            overflow: 'hidden',
          }}>
            <div style={{
              background: 'rgba(16,185,129,0.1)',
              padding: '8px 16px',
              borderBottom: `1px solid ${T.border}`,
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
            }}>
              <div style={{ width: 8, height: 8, borderRadius: '50%', background: T.accent }} />
              <span style={{ fontSize: '12px', color: T.accent }}>201 Created</span>
            </div>
            <pre style={{
              padding: '16px 20px',
              margin: 0,
              fontSize: '12px',
              lineHeight: 1.5,
              color: '#94a3b8',
            }}>
              <code>{`{
  "id": "rec_3x7Kp9mN2vL",
  "record_hash": "a3f2b891c4d5e6f78901a2b3c4d5e6f7...",
  "prev_hash": "7f6e5d4c3b2a19087f6e5d4c3b2a1908...",
  "chain_position": 1847,
  "created_at": "2026-02-05T18:54:31Z",
  "signature": "MEUCIQC7...base64...==",
  "public_key_id": "regengine-prod-2026-02"
}`}</code>
            </pre>
          </div>

          {/* Get API Key CTA */}
          <div style={{ marginTop: '24px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <Link
              href="/api-keys"
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
              <Key style={{ width: 16, height: 16 }} />
              Get API Key
            </Link>
            <Link
              href="/docs/quickstart"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '8px',
                background: 'rgba(255,255,255,0.1)',
                color: '#ffffff',
                padding: '12px 24px',
                borderRadius: '6px',
                fontWeight: 600,
                fontSize: '14px',
                textDecoration: 'none',
                border: `1px solid ${T.border}`,
              }}
            >
              Full Quickstart Guide
              <ArrowRight style={{ width: 16, height: 16 }} />
            </Link>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '48px 24px' }}>

        {/* Row 2: By Task */}
        <section style={{ marginBottom: '48px' }}>
          <h2 style={{
            fontSize: '12px',
            fontWeight: 600,
            color: T.textMuted,
            textTransform: 'uppercase',
            letterSpacing: '1px',
            marginBottom: '16px',
          }}>
            By Task
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
            {[
              { name: 'Quickstart', href: '/docs/quickstart', icon: Zap, desc: '5 min setup' },
              { name: 'API Reference', href: '/docs/api', icon: Code, desc: 'Full endpoints' },
              { name: 'SDKs & Libraries', href: '/docs/sdks', icon: Book, desc: 'Python, Node, Go' },
              { name: 'Webhooks', href: '/docs/webhooks', icon: Webhook, desc: 'Real-time events' },
            ].map((item) => (
              <Link
                key={item.name}
                href={item.href}
                style={{
                  padding: '20px',
                  background: T.surface,
                  borderRadius: '8px',
                  border: `1px solid ${T.border}`,
                  textDecoration: 'none',
                  transition: 'border-color 0.2s',
                }}
              >
                <item.icon style={{ width: 20, height: 20, color: T.accent, marginBottom: '12px' }} />
                <div style={{ fontWeight: 600, color: '#ffffff', fontSize: '15px', marginBottom: '4px' }}>
                  {item.name}
                </div>
                <div style={{ color: T.textMuted, fontSize: '13px' }}>{item.desc}</div>
              </Link>
            ))}
          </div>
        </section>

        {/* Row 3: By Vertical - Food & Beverage FIRST */}
        <section style={{ marginBottom: '48px' }}>
          <h2 style={{
            fontSize: '12px',
            fontWeight: 600,
            color: T.textMuted,
            textTransform: 'uppercase',
            letterSpacing: '1px',
            marginBottom: '16px',
          }}>
            By Vertical
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
            {[
              { name: 'Food & Beverage', href: '/docs/fsma-204', icon: UtensilsCrossed, framework: 'FSMA 204', featured: true },
              { name: 'Finance', href: '/docs/finance', icon: TrendingUp, framework: 'SEC / SOX 404', featured: false },
              { name: 'Energy', href: '/docs/energy', icon: Zap, framework: 'NERC CIP-013', featured: false },
              { name: 'Nuclear', href: '/docs/nuclear', icon: Atom, framework: '10 CFR / NRC', featured: false },
              { name: 'Technology', href: '/docs/technology', icon: Cpu, framework: 'SOC 2 / ISO', featured: false },
              { name: 'Healthcare', href: '/docs/healthcare', icon: ShieldCheck, framework: 'HIPAA', featured: false },
            ].map((item) => (
              <Link
                key={item.name}
                href={item.href}
                style={{
                  padding: '20px',
                  background: item.featured ? 'rgba(16,185,129,0.1)' : T.surface,
                  borderRadius: '8px',
                  border: `1px solid ${item.featured ? 'rgba(16,185,129,0.3)' : T.border}`,
                  textDecoration: 'none',
                  position: 'relative',
                }}
              >
                {item.featured && (
                  <div style={{
                    position: 'absolute',
                    top: '12px',
                    right: '12px',
                    background: T.accent,
                    color: 'white',
                    fontSize: '10px',
                    fontWeight: 600,
                    padding: '2px 8px',
                    borderRadius: '4px',
                    textTransform: 'uppercase',
                  }}>
                    Most Complete
                  </div>
                )}
                <item.icon style={{ width: 20, height: 20, color: item.featured ? T.accent : T.textMuted, marginBottom: '12px' }} />
                <div style={{ fontWeight: 600, color: '#ffffff', fontSize: '15px', marginBottom: '4px' }}>
                  {item.name}
                </div>
                <div style={{ color: T.textMuted, fontSize: '13px' }}>{item.framework}</div>
              </Link>
            ))}
          </div>
        </section>

        {/* Row 4: Popular Pages */}
        <section style={{ marginBottom: '48px' }}>
          <h2 style={{
            fontSize: '12px',
            fontWeight: 600,
            color: T.textMuted,
            textTransform: 'uppercase',
            letterSpacing: '1px',
            marginBottom: '16px',
          }}>
            Popular Pages
          </h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px' }}>
            {[
              { name: 'Authentication', href: '/docs/authentication', icon: Key },
              { name: 'Rate Limits', href: '/docs/rate-limits', icon: AlertCircle },
              { name: 'Error Codes', href: '/docs/errors', icon: AlertCircle },
              { name: 'Changelog', href: '/docs/changelog', icon: FileText },
            ].map((item) => (
              <Link
                key={item.name}
                href={item.href}
                style={{
                  padding: '16px 20px',
                  background: 'transparent',
                  borderRadius: '8px',
                  border: `1px solid ${T.border}`,
                  textDecoration: 'none',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '12px',
                }}
              >
                <item.icon style={{ width: 16, height: 16, color: T.textMuted }} />
                <span style={{ color: '#e2e8f0', fontSize: '14px' }}>{item.name}</span>
              </Link>
            ))}
          </div>
        </section>

        {/* Footer: verify_chain.py tagline */}
        <footer style={{
          borderTop: `1px solid ${T.border}`,
          paddingTop: '32px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '16px',
        }}>
          <div>
            <code style={{
              background: 'rgba(255,255,255,0.05)',
              padding: '8px 16px',
              borderRadius: '6px',
              fontSize: '13px',
              color: T.textMuted,
              fontFamily: T.fontMono,
            }}>
              python verify_chain.py --audit
            </code>
            <span style={{ marginLeft: '16px', color: T.textMuted, fontSize: '14px' }}>
              Don&apos;t trust, verify.
            </span>
          </div>
          <div style={{ display: 'flex', gap: '24px' }}>
            <Link href="/docs/api" style={{ color: T.textMuted, fontSize: '13px', textDecoration: 'none' }}>
              API Reference
            </Link>
            <Link href="/docs/errors" style={{ color: T.textMuted, fontSize: '13px', textDecoration: 'none' }}>
              Error Codes
            </Link>
            <a href="mailto:support@regengine.co" style={{ color: T.textMuted, fontSize: '13px', textDecoration: 'none' }}>
              Support
            </a>
          </div>
        </footer>
      </div>
    </div>
  );
}
