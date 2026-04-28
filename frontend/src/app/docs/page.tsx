import type { Metadata } from 'next';
import Link from 'next/link';
import {
  ArrowRight,
  Key,
  BookOpen,
  Shield,
  FileSearch,
  Activity,
  Database,
  Send,
  AlertTriangle,
  Gauge,
  Zap,
  Code2,
  Terminal,
  FileCode,
  Webhook,
  Clock,
  Package,
  FileText,
} from 'lucide-react';
import { T as _T } from '@/lib/design-tokens';

// Wrap design tokens to use theme-aware CSS variables for text/heading colors,
// while keeping accent/border tokens that work across themes.
const T = {
  ..._T,
  heading: 'var(--re-text-primary)',
  text: 'var(--re-text-secondary)',
  textMuted: 'var(--re-text-muted)',
  textDim: 'var(--re-text-muted)',
  surface: 'var(--re-surface-card)',
  border: 'var(--re-surface-border)',
};

export const metadata: Metadata = {
  title: 'API Documentation | RegEngine',
  description:
    'RegEngine API documentation for FSMA 204 food traceability compliance. Ingest CTE/KDE records, evaluate compliance rules, and export FDA-ready audit packages.',
  openGraph: {
    title: 'API Documentation | RegEngine',
    description:
      'RegEngine API documentation for FSMA 204 food traceability compliance. Ingest CTE/KDE records, evaluate compliance rules, and export FDA-ready audit packages.',
    type: 'website',
    url: 'https://regengine.co/docs',
    siteName: 'RegEngine',
  },
};

/* ─── Data ─────────────────────────────────────────────────── */

const API_BASE = 'https://api.regengine.co/api/v1';

const endpoints = [
  {
    method: 'POST' as const,
    path: '/records/ingest',
    title: 'Ingest Records',
    description: 'Ingest traceability records with CTE/KDE data. Each record is hash-chained for tamper evidence.',
    icon: Database,
  },
  {
    method: 'GET' as const,
    path: '/records',
    title: 'Query Records',
    description: 'Query canonical records with filters by CTE type, lot code, date range, and location.',
    icon: FileSearch,
  },
  {
    method: 'POST' as const,
    path: '/compliance/evaluate',
    title: 'Evaluate Compliance',
    description: 'Run FSMA 204 rule evaluation against your records. Returns pass/fail with specific citations.',
    icon: Shield,
  },
  {
    method: 'GET' as const,
    path: '/fda-export/{request_id}',
    title: 'FDA Export',
    description: 'Export an FDA-ready audit package for a specific compliance request, including all supporting records.',
    icon: Send,
  },
  {
    method: 'GET' as const,
    path: '/readiness/assessment',
    title: 'Readiness Score',
    description: 'Get your current compliance readiness score with a breakdown by CTE coverage and KDE completeness.',
    icon: Activity,
  },
];

const METHOD_COLORS: Record<string, { bg: string; text: string }> = {
  GET: { bg: 'rgba(59,130,246,0.15)', text: '#60a5fa' },
  POST: { bg: 'rgba(16,185,129,0.15)', text: '#34d399' },
};

const subPages = [
  { title: 'Quickstart', href: '/docs/quickstart', icon: Zap, description: 'Your first API call in under 60 seconds' },
  { title: 'Authentication', href: '/docs/authentication', icon: Key, description: 'API keys, tenant headers, and security' },
  { title: 'API Reference', href: '/docs/api', icon: Code2, description: 'Full endpoint reference with schemas' },
  { title: 'Webhooks', href: '/docs/webhooks', icon: Webhook, description: 'Real-time event notifications' },
  { title: 'Inflow Lab', href: '/docs/connectors/inflow-lab', icon: Terminal, description: 'Simulator setup and source tagging' },
  { title: 'Error Codes', href: '/docs/errors', icon: AlertTriangle, description: 'Error responses and troubleshooting' },
  { title: 'Rate Limits', href: '/docs/rate-limits', icon: Clock, description: 'Request limits and throttling policies' },
  { title: 'SDKs', href: '/docs/sdks', icon: Package, description: 'Client libraries for Python, Node.js, and more' },
  { title: 'FSMA 204 Guide', href: '/docs/fsma-204', icon: FileText, description: 'FSMA 204 regulation reference and implementation' },
];

/* ─── Helpers ──────────────────────────────────────────────── */

function MethodBadge({ method }: { method: string }) {
  const colors = METHOD_COLORS[method] ?? METHOD_COLORS.GET;
  return (
    <span
      className="font-mono text-[11px] font-bold px-2 py-0.5 rounded"
      style={{ background: colors.bg, color: colors.text }}
    >
      {method}
    </span>
  );
}

/* ─── Code Samples ─────────────────────────────────────────── */

const curlSample = `curl -X POST ${API_BASE}/records/ingest \\
  -H "X-RegEngine-API-Key: re_live_abc123..." \\
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
  }'`;

const pythonSample = `import requests

resp = requests.post(
    "${API_BASE}/records/ingest",
    headers={
        "X-RegEngine-API-Key": "re_live_abc123...",
        "Content-Type": "application/json",
    },
    json={
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
                "receiving_location": "Distribution Center #4",
            },
        }],
    },
)
print(resp.json())`;

const jsSample = `const resp = await fetch(
  "${API_BASE}/records/ingest",
  {
    method: "POST",
    headers: {
      "X-RegEngine-API-Key": "re_live_abc123...",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      source: "erp",
      events: [{
        cte_type: "receiving",
        traceability_lot_code: "00012345678901-LOT-2026-001",
        product_description: "Romaine Lettuce",
        quantity: 500,
        unit_of_measure: "cases",
        location_name: "Distribution Center #4",
        timestamp: "2026-02-05T08:30:00Z",
        kdes: {
          receive_date: "2026-02-05",
          receiving_location: "Distribution Center #4",
        },
      }],
    }),
  }
);
const data = await resp.json();
console.log(data);`;

const responseSample = `{
  "accepted": 1,
  "rejected": 0,
  "total": 1,
  "events": [{
    "traceability_lot_code": "00012345678901-LOT-2026-001",
    "cte_type": "receiving",
    "status": "accepted",
    "event_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "sha256_hash": "a3f2b891c4d5e6f7...",
    "chain_hash": "7f6e5d4c3b2a1908..."
  }]
}`;

const codeTabs = [
  { label: 'cURL', lang: 'bash', code: curlSample },
  { label: 'Python', lang: 'python', code: pythonSample },
  { label: 'JavaScript', lang: 'javascript', code: jsSample },
];

/* ─── Page ─────────────────────────────────────────────────── */

export default function DocsHomePage() {
  return (
    <div className="min-h-screen bg-[var(--re-surface-base)] text-[var(--re-text-secondary)]">

      {/* ── Hero ────────────────────────────────────────────── */}
      <section
        className="px-6 py-16"
        style={{
          background: 'linear-gradient(135deg, rgba(16,185,129,0.06) 0%, rgba(6,182,212,0.04) 100%)',
          borderBottom: `1px solid ${T.border}`,
        }}
      >
        <div className="max-w-[1000px] mx-auto">
          <div className="flex items-center gap-3 mb-5">
            <span
              className="font-mono text-[11px] font-bold uppercase tracking-widest px-3 py-1 rounded"
              style={{ background: T.accentBg, color: T.accent }}
            >
              Developer Docs
            </span>
            <span className="text-xs" style={{ color: T.textMuted }}>v1</span>
          </div>

          <h1
            className="font-display text-[2.25rem] md:text-[2.75rem] font-bold leading-tight mb-3"
            style={{ color: T.heading }}
          >
            RegEngine API Documentation
          </h1>
          <p className="text-[16px] max-w-[600px] mb-8 leading-relaxed" style={{ color: T.textMuted }}>
            Build FSMA 204 compliant traceability into any supply chain system.
            Ingest CTE/KDE records, evaluate compliance, and export FDA-ready audit packages.
          </p>

          {/* Quick start steps */}
          <div className="flex flex-wrap gap-4 mb-8">
            {[
              { step: '1', label: 'Read the docs', href: '/docs/quickstart', icon: BookOpen },
              { step: '2', label: 'Get an API key', href: '/signup', icon: Key },
              { step: '3', label: 'Make your first call', href: '/docs/quickstart', icon: Terminal },
            ].map((item) => (
              <Link
                key={item.step}
                href={item.href}
                className="flex items-center gap-3 px-5 py-3 rounded-lg no-underline group"
                style={{ background: T.surface, border: `1px solid ${T.border}` }}
              >
                <span
                  className="flex items-center justify-center w-7 h-7 rounded-full font-mono text-xs font-bold"
                  style={{ background: T.accentBg, color: T.accent }}
                >
                  {item.step}
                </span>
                <item.icon className="w-4 h-4" style={{ color: T.textMuted }} />
                <span className="text-sm font-medium" style={{ color: T.heading }}>
                  {item.label}
                </span>
                <ArrowRight
                  className="w-3.5 h-3.5 opacity-0 -translate-x-1 transition-all group-hover:opacity-100 group-hover:translate-x-0"
                  style={{ color: T.accent }}
                />
              </Link>
            ))}
          </div>

          {/* Base URL + Auth */}
          <div className="flex flex-wrap gap-6">
            <div>
              <span className="block text-[11px] font-mono uppercase tracking-wider mb-1.5" style={{ color: T.textMuted }}>
                Base URL
              </span>
              <code
                className="block text-sm px-4 py-2 rounded-md"
                style={{
                  background: 'var(--re-surface-elevated)',
                  border: `1px solid ${T.border}`,
                  color: T.accent,
                  fontFamily: T.fontMono,
                }}
              >
                {API_BASE}
              </code>
            </div>
            <div>
              <span className="block text-[11px] font-mono uppercase tracking-wider mb-1.5" style={{ color: T.textMuted }}>
                Authentication
              </span>
              <code
                className="block text-sm px-4 py-2 rounded-md"
                style={{
                  background: 'var(--re-surface-elevated)',
                  border: `1px solid ${T.border}`,
                  color: T.text,
                  fontFamily: T.fontMono,
                }}
              >
                X-RegEngine-API-Key: <span style={{ color: T.textMuted }}>re_live_...</span>
              </code>
            </div>
          </div>
        </div>
      </section>

      <div className="max-w-[1000px] mx-auto px-6 py-14">

        {/* ── Core Endpoints ────────────────────────────────── */}
        <section className="mb-16">
          <h2
            className="font-display text-[11px] font-bold uppercase tracking-widest mb-6"
            style={{ color: T.textMuted }}
          >
            Core Endpoints
          </h2>
          <div className="grid gap-3">
            {endpoints.map((ep) => (
              <div
                key={ep.path}
                className="flex items-start gap-4 px-5 py-4 rounded-lg"
                style={{ background: T.surface, border: `1px solid ${T.border}` }}
              >
                <div
                  className="flex items-center justify-center w-9 h-9 rounded-lg mt-0.5 shrink-0"
                  style={{ background: T.accentBg }}
                >
                  <ep.icon className="w-[18px] h-[18px]" style={{ color: T.accent }} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-3 mb-1 flex-wrap">
                    <MethodBadge method={ep.method} />
                    <code className="text-[13px]" style={{ color: T.heading, fontFamily: T.fontMono }}>
                      {ep.path}
                    </code>
                  </div>
                  <p className="text-[13px] leading-relaxed m-0" style={{ color: T.textMuted }}>
                    {ep.description}
                  </p>
                </div>
                <Link
                  href="/docs/api"
                  className="shrink-0 text-[12px] font-medium no-underline px-3 py-1.5 rounded-md mt-0.5"
                  style={{ color: T.accent, background: T.accentBg }}
                >
                  Reference
                </Link>
              </div>
            ))}
          </div>
        </section>

        {/* ── Code Samples ──────────────────────────────────── */}
        <section className="mb-16">
          <h2
            className="font-display text-[11px] font-bold uppercase tracking-widest mb-2"
            style={{ color: T.textMuted }}
          >
            Ingest Your First Record
          </h2>
          <p className="text-sm mb-6" style={{ color: T.textMuted }}>
            Send a traceability event to the <code className="font-mono text-[13px]" style={{ color: T.accent }}>POST /records/ingest</code> endpoint.
          </p>

          {/* Tab bar (static, no JS needed -- all samples shown with labels) */}
          <div className="space-y-4">
            {codeTabs.map((tab) => (
              <div
                key={tab.label}
                className="rounded-lg overflow-hidden"
                style={{ border: `1px solid ${T.border}` }}
              >
                <div
                  className="flex items-center justify-between px-4 py-2"
                  style={{ background: 'var(--re-surface-elevated)', borderBottom: `1px solid ${T.border}` }}
                >
                  <span className="font-mono text-xs" style={{ color: T.textMuted }}>{tab.label}</span>
                  <span className="font-mono text-[10px] uppercase tracking-wide" style={{ color: T.accent }}>{tab.lang}</span>
                </div>
                <pre
                  className="m-0 px-5 py-4 overflow-x-auto text-[13px] leading-relaxed"
                  style={{ background: 'var(--re-surface-elevated)', color: T.text }}
                >
                  <code>{tab.code}</code>
                </pre>
              </div>
            ))}
          </div>

          {/* Response */}
          <div className="mt-4 rounded-lg overflow-hidden" style={{ border: `1px solid ${T.border}` }}>
            <div
              className="flex items-center gap-2 px-4 py-2"
              style={{ background: T.accentBg, borderBottom: `1px solid ${T.border}` }}
            >
              <span className="w-2 h-2 rounded-full" style={{ background: T.accent }} />
              <span className="font-mono text-xs font-bold" style={{ color: T.accent }}>201 Created</span>
              <span className="font-mono text-[10px] ml-auto uppercase tracking-wide" style={{ color: T.textMuted }}>response</span>
            </div>
            <pre
              className="m-0 px-5 py-4 overflow-x-auto text-[13px] leading-relaxed"
              style={{ background: 'var(--re-surface-elevated)', color: T.textMuted }}
            >
              <code>{responseSample}</code>
            </pre>
          </div>
        </section>

        {/* ── Documentation Pages Grid ──────────────────────── */}
        <section className="mb-16">
          <h2
            className="font-display text-[11px] font-bold uppercase tracking-widest mb-6"
            style={{ color: T.textMuted }}
          >
            Documentation
          </h2>
          <div className="grid sm:grid-cols-2 gap-3">
            {subPages.map((page) => (
              <Link
                key={page.href}
                href={page.href}
                className="flex items-start gap-4 px-5 py-4 rounded-lg no-underline group"
                style={{ background: T.surface, border: `1px solid ${T.border}` }}
              >
                <div
                  className="flex items-center justify-center w-9 h-9 rounded-lg shrink-0 mt-0.5"
                  style={{ background: T.accentBg }}
                >
                  <page.icon className="w-[18px] h-[18px]" style={{ color: T.accent }} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-[14px] font-semibold" style={{ color: T.heading }}>
                      {page.title}
                    </span>
                    <ArrowRight
                      className="w-3.5 h-3.5 opacity-0 -translate-x-1 transition-all group-hover:opacity-100 group-hover:translate-x-0"
                      style={{ color: T.accent }}
                    />
                  </div>
                  <p className="text-[13px] leading-relaxed m-0" style={{ color: T.textMuted }}>
                    {page.description}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        </section>

        {/* ── CTA Banner ────────────────────────────────────── */}
        <section
          className="rounded-lg px-8 py-8 mb-16 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-6"
          style={{
            background: 'linear-gradient(135deg, rgba(16,185,129,0.08) 0%, rgba(6,182,212,0.06) 100%)',
            border: `1px solid ${T.accentBorder}`,
          }}
        >
          <div>
            <h3 className="text-lg font-semibold mb-1" style={{ color: T.heading }}>
              Ready to get started?
            </h3>
            <p className="text-sm m-0" style={{ color: T.textMuted }}>
              Create a free developer account and get your API key in minutes.
            </p>
          </div>
          <div className="flex gap-3 shrink-0">
            <Link
              href="/signup"
              className="inline-flex items-center gap-2 text-white px-6 py-3 rounded-md font-semibold text-sm no-underline"
              style={{ background: T.accent }}
            >
              <Key className="w-4 h-4" />
              Get API Key
            </Link>
            <Link
              href="/docs/quickstart"
              className="inline-flex items-center gap-2 px-6 py-3 rounded-md font-semibold text-sm no-underline"
              style={{ background: T.surface, border: `1px solid ${T.border}`, color: T.heading }}
            >
              Quickstart
              <ArrowRight className="w-4 h-4" />
            </Link>
          </div>
        </section>

        {/* ── Footer ────────────────────────────────────────── */}
        <footer
          className="pt-8 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4"
          style={{ borderTop: `1px solid ${T.border}` }}
        >
          <div className="flex items-center gap-4">
            <code
              className="px-4 py-2 rounded-md text-[13px]"
              style={{ background: 'var(--re-surface-elevated)', color: T.textMuted, fontFamily: T.fontMono }}
            >
              python verify_chain.py --audit
            </code>
            <span className="text-sm" style={{ color: T.textMuted }}>
              Don&apos;t trust, verify.
            </span>
          </div>
          <div className="flex gap-6">
            <Link href="/docs/quickstart" className="text-[13px] no-underline" style={{ color: T.textMuted }}>
              Quickstart
            </Link>
            <Link href="/docs/api" className="text-[13px] no-underline" style={{ color: T.textMuted }}>
              API Reference
            </Link>
            <Link href="/docs/fsma-204" className="text-[13px] no-underline" style={{ color: T.textMuted }}>
              FSMA 204
            </Link>
            <a href="mailto:support@regengine.co" className="text-[13px] no-underline" style={{ color: T.textMuted }}>
              Support
            </a>
          </div>
        </footer>
      </div>
    </div>
  );
}
