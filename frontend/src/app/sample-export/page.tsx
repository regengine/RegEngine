'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
    Download, FileText, FileCode, Shield, ExternalLink,
    CheckCircle2, Copy, Check, Archive, Lock, Eye,
} from 'lucide-react';

const T = {
    bg: 'var(--re-surface-base)',
    surface: 'rgba(255,255,255,0.02)',
    elevated: 'rgba(255,255,255,0.05)',
    border: 'rgba(255,255,255,0.06)',
    text: 'var(--re-text-primary)',
    textDim: 'var(--re-text-tertiary)',
    textMuted: 'var(--re-text-muted)',
    accent: 'var(--re-success)',
    accentDim: 'rgba(34,197,94,0.12)',
    brand: 'var(--re-brand)',
    mono: "'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace",
};

const ARTIFACTS = [
    {
        name: 'EPCIS 2.0 JSON-LD',
        file: '/samples/sample_epcis_2.0.json',
        icon: FileCode,
        description: 'GS1 EPCIS 2.0 standard format. 12 traceability events with SHA-256 integrity metadata. Interoperable with any EPCIS-compatible trading partner.',
        size: '9.8 KB',
        records: 12,
    },
    {
        name: 'FDA Sortable Spreadsheet',
        file: '/samples/sample_fda_export.csv',
        icon: FileText,
        description: 'The format FDA expects during a 24-hour records request. Sortable by lot code, facility, event type, and date. Includes hash chain for tamper evidence.',
        size: '3.8 KB',
        records: 12,
    },
    {
        name: 'Chain Verification Report',
        file: '/samples/sample_chain_verification.json',
        icon: Shield,
        description: 'Independent verification of every record in the chain. Each event\'s SHA-256 hash is recomputed and compared. Chain integrity: VALID.',
        size: '4.2 KB',
        records: 12,
    },
    {
        name: 'Export Manifest',
        file: '/samples/sample_manifest.json',
        icon: Archive,
        description: 'Package metadata: file list, record counts, chain integrity status, final Merkle hash, and retention notice. The manifest itself is SHA-256 hashed.',
        size: '1.0 KB',
        records: 12,
    },
];

const CHAIN_EVENTS = [
    { seq: 1, cte: 'Harvesting', facility: 'Green Valley Farm', location: 'Salinas, CA', hash: 'a3b8d1b6e0f2c45d' },
    { seq: 2, cte: 'Cooling', facility: 'Green Valley Cooler', location: 'Salinas, CA', hash: '4f7c2e1a9d8b3f65' },
    { seq: 3, cte: 'Initial Packing', facility: 'Valley Fresh Packhouse', location: 'Salinas, CA', hash: '9e3d7c854b6a2f10' },
    { seq: 4, cte: 'Shipping', facility: 'Valley Fresh Packhouse', location: 'Salinas, CA', hash: '72c4f8a1b3d9e567' },
    { seq: 5, cte: 'Receiving', facility: 'Metro Distribution Center', location: 'Los Angeles, CA', hash: '5a1b9c3d7e4f8206' },
    { seq: 6, cte: 'Shipping', facility: 'Metro Distribution Center', location: 'Los Angeles, CA', hash: 'b8e2f4a6c1d7930e' },
    { seq: 7, cte: 'Receiving', facility: 'SuperMart Store #145', location: 'San Diego, CA', hash: '3c9a5d7f2b8e1604' },
    { seq: 8, cte: 'First Receiver', facility: 'Pacific Import Terminal', location: 'Long Beach, CA', hash: 'e1f3b5d7a9c2840' },
    { seq: 9, cte: 'Transformation', facility: 'Fresh Cut Processing', location: 'Fresno, CA', hash: '6d8f2a4c9e1b3750' },
    { seq: 10, cte: 'Shipping', facility: 'Fresh Cut Processing', location: 'Fresno, CA', hash: '1b3d5f7a9c2e4860' },
    { seq: 11, cte: 'Receiving', facility: 'Kroger DC #7218', location: 'Phoenix, AZ', hash: '8e0a2c4d6f1b3950' },
    { seq: 12, cte: 'Shipping', facility: 'Kroger DC #7218', location: 'Phoenix, AZ', hash: '7e421cfbdb762a90' },
];

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);
    return (
        <button onClick={() => { navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: copied ? T.accent : T.textDim, padding: 4 }}
            title="Copy to clipboard"
        >
            {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
    );
}

export default function SampleExportPage() {
    return (
        <div style={{ background: T.bg, minHeight: '100vh', color: T.text }}>
            {/* Hero */}
            <section style={{ maxWidth: 960, margin: '0 auto', padding: '80px 24px 60px', textAlign: 'center' }}>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 16px', background: T.accentDim, borderRadius: 20, fontSize: 13, color: T.accent, fontWeight: 500, marginBottom: 24 }}>
                    <Eye size={14} />
                    Inspectable Proof — Not Marketing Copy
                </div>

                <h1 style={{ fontSize: 'clamp(32px, 5vw, 48px)', fontWeight: 700, lineHeight: 1.1, margin: '0 0 16px' }}>
                    See What RegEngine Actually Produces
                </h1>

                <p style={{ fontSize: 18, color: T.textDim, maxWidth: 640, margin: '0 auto 32px', lineHeight: 1.6 }}>
                    This is a real FDA export package generated from a sample traceability chain.
                    12 events, 7 facilities, farm to store. Every record SHA-256 hashed and Merkle-chained.
                    Download it. Inspect it. Verify it yourself.
                </p>

                <div className="flex gap-3 justify-center flex-wrap">
                    <a href="/samples/sample_epcis_2.0.json" download
                        style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 24px', background: T.accent, color: '#000', borderRadius: 8, fontSize: 15, fontWeight: 600, textDecoration: 'none' }}>
                        <Download size={16} /> Download Full Package
                    </a>
                    <a href="#chain" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 24px', background: T.elevated, border: `1px solid ${T.border}`, color: T.text, borderRadius: 8, fontSize: 15, fontWeight: 500, textDecoration: 'none' }}>
                        <Shield size={16} /> View Chain Below
                    </a>
                </div>
            </section>

            {/* Artifacts Grid */}
            <section style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px 60px' }}>
                <h2 style={{ fontSize: 24, fontWeight: 600, textAlign: 'center', marginBottom: 32 }}>
                    What&apos;s in the Package
                </h2>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 16 }}>
                    {ARTIFACTS.map((a) => {
                        const Icon = a.icon;
                        return (
                            <div key={a.name} style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: 24 }}>
                                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                                    <div style={{ width: 40, height: 40, borderRadius: 10, background: T.accentDim, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                        <Icon size={18} style={{ color: T.accent }} />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: 15, fontWeight: 600 }}>{a.name}</div>
                                        <div style={{ fontSize: 11, color: T.textDim }}>{a.size} · {a.records} records</div>
                                    </div>
                                </div>
                                <p style={{ fontSize: 13, color: T.textDim, lineHeight: 1.5, marginBottom: 16 }}>{a.description}</p>
                                <a href={a.file} download style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 13, fontWeight: 600, color: T.accent, textDecoration: 'none' }}>
                                    <Download size={14} /> Download
                                </a>
                            </div>
                        );
                    })}
                </div>
            </section>

            {/* Live Chain Visualization */}
            <section id="chain" style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px 60px' }}>
                <h2 style={{ fontSize: 24, fontWeight: 600, textAlign: 'center', marginBottom: 8 }}>
                    The Traceability Chain
                </h2>
                <p style={{ textAlign: 'center', color: T.textDim, fontSize: 15, marginBottom: 32, maxWidth: 560, margin: '0 auto 32px' }}>
                    Romaine Lettuce lot ROM-2026-0312. Each row is a Critical Tracking Event.
                    Each hash links to the previous — tamper with one, break all downstream.
                </p>

                <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
                    {/* Header */}
                    <div style={{ display: 'grid', gridTemplateColumns: '50px 1.2fr 1.5fr 1fr 1fr', padding: '12px 16px', background: T.elevated, borderBottom: `1px solid ${T.border}`, fontSize: 11, fontWeight: 600, color: T.textMuted, textTransform: 'uppercase', letterSpacing: '0.04em', minWidth: 640 }}>
                        <span>#</span>
                        <span>CTE Type</span>
                        <span>Facility</span>
                        <span>Location</span>
                        <span>Merkle Hash</span>
                    </div>

                    {/* Rows */}
                    {CHAIN_EVENTS.map((e, i) => (
                        <div key={i} style={{ display: 'grid', gridTemplateColumns: '50px 1.2fr 1.5fr 1fr 1fr', padding: '10px 16px', borderBottom: i < CHAIN_EVENTS.length - 1 ? `1px solid ${T.border}` : 'none', fontSize: 13, minWidth: 640, alignItems: 'center' }}>
                            <span style={{ color: T.accent, fontWeight: 700, fontFamily: T.mono, fontSize: 12 }}>{e.seq}</span>
                            <span style={{ fontWeight: 500 }}>{e.cte}</span>
                            <span style={{ color: T.textDim }}>{e.facility}</span>
                            <span style={{ color: T.textDim, fontSize: 12 }}>{e.location}</span>
                            <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                                <code style={{ fontFamily: T.mono, fontSize: 11, color: T.accent }}>{e.hash}...</code>
                                <CheckCircle2 size={12} style={{ color: T.accent, flexShrink: 0 }} />
                            </div>
                        </div>
                    ))}

                    {/* Chain summary */}
                    <div style={{ padding: '16px', background: T.accentDim, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Lock size={16} style={{ color: T.accent }} />
                            <span style={{ fontSize: 14, fontWeight: 600, color: T.accent }}>Chain Valid · 12/12 records verified</span>
                        </div>
                        <span style={{ fontSize: 11, color: T.textDim, fontFamily: T.mono }}>
                            Final: 7e421cfb...
                        </span>
                    </div>
                </div>
            </section>

            {/* Retention Notice */}
            <section style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px 60px' }}>
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: 24, display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
                    <Archive size={24} style={{ color: T.accent, flexShrink: 0, marginTop: 2 }} />
                    <div>
                        <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8 }}>Customer-Owned Archives</h3>
                        <p style={{ fontSize: 14, color: T.textDim, lineHeight: 1.6 }}>
                            RegEngine recommends maintaining off-platform archives from week one. Every export is designed to be
                            portable and independently verifiable. You own your data. Export it in EPCIS 2.0, FDA CSV, or JSON — and
                            verify integrity offline with our <Link href="/verify" style={{ color: T.accent, textDecoration: 'underline' }}>open-source verification script</Link>.
                        </p>
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px 80px', textAlign: 'center' }}>
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16, padding: '48px 32px' }}>
                    <h2 style={{ fontSize: 28, fontWeight: 600, marginBottom: 12 }}>
                        This is what compliance evidence looks like.
                    </h2>
                    <p style={{ fontSize: 15, color: T.textDim, maxWidth: 480, margin: '0 auto 28px', lineHeight: 1.6 }}>
                        Every RegEngine customer gets this for their real data.
                        Ingest your records, and your first FDA-ready export is minutes away.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/founding-design-partners" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 24px', background: T.accent, color: '#000', borderRadius: 8, fontSize: 15, fontWeight: 600, textDecoration: 'none' }}>
                            Become a Founding Design Partner
                        </Link>
                        <Link href="/verify" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 24px', background: T.elevated, border: `1px solid ${T.border}`, color: T.text, borderRadius: 8, fontSize: 15, fontWeight: 500, textDecoration: 'none' }}>
                            Verify Script <ExternalLink size={14} />
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
