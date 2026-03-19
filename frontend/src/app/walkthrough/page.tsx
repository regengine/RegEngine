'use client';

import Link from 'next/link';
import {
    Upload, Search, CheckCircle2, Shield, Download, ArrowRight,
    AlertTriangle, FileText, Lock, Eye, Terminal, Zap,
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
    warning: 'var(--re-warning)',
    warningDim: 'rgba(245,158,11,0.12)',
    danger: 'var(--re-danger)',
    dangerDim: 'rgba(239,68,68,0.12)',
    mono: "'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace",
};

const STEPS = [
    {
        num: '1',
        icon: Upload,
        title: 'Upload Your Messy Data',
        subtitle: 'CSV, XLSX, or JSON — whatever you have',
        before: {
            label: 'Starting State',
            items: [
                'Spreadsheet exported from QuickBooks with inconsistent column names',
                '10,000 rows across 21 columns — lot codes, facilities, dates, quantities',
                'Some rows have missing facility names, invalid event types, empty lot numbers',
                'Date formats mix ISO 8601, MM/DD/YYYY, and plain text',
            ],
        },
        after: {
            label: 'What RegEngine Does',
            items: [
                'Detects format automatically (CSV, XLSX, JSON)',
                'Maps your columns to FSMA 204 fields (facility_name, lot_number, event_type, etc.)',
                'Previews 200 rows with column detection and event type distribution',
                'Shows exactly what was found: 10 facilities, 10,000 events, 5 CTE types',
            ],
        },
        screenshot: null,
    },
    {
        num: '2',
        icon: Search,
        title: 'Validate & Auto-Clean',
        subtitle: 'Bad data gets fixed, not rejected',
        before: {
            label: 'Problems Found',
            items: [
                '47 rows with empty facility names → auto-filled as "Unnamed Facility"',
                '12 rows with invalid event types ("Z", "?", empty) → defaulted to "receiving"',
                '3 rows with lot numbers under 3 characters → flagged with warnings',
                'All issues surfaced as non-blocking warnings, not hard errors',
            ],
        },
        after: {
            label: 'Validation Result',
            items: [
                '10,000 events ready to commit (none rejected)',
                '62 auto-fill warnings displayed for review',
                '21 facilities auto-created from event data',
                'Compliance preview: 21 create / 0 update / 10,000 chain',
            ],
        },
        screenshot: null,
    },
    {
        num: '3',
        icon: Lock,
        title: 'Commit with Cryptographic Integrity',
        subtitle: 'Every record SHA-256 hashed and Merkle-chained',
        before: {
            label: 'What Happens During Commit',
            items: [
                'Events processed in 500-row batches to prevent timeouts',
                'Each record gets a SHA-256 hash of its immutable fields',
                'Hashes are linked in a Merkle chain — tamper with one, break all downstream',
                'First 100 events sync to the graph database immediately; rest deferred to background worker',
            ],
        },
        after: {
            label: 'Commit Result',
            items: [
                '10,000 events chained in ~45 seconds',
                '21 facilities created with compliance scoring',
                'Merkle chain length: 10,000 (verified)',
                'Graph sync: 100 immediate, 9,900 deferred',
            ],
        },
        screenshot: null,
    },
    {
        num: '4',
        icon: Download,
        title: 'Export: FDA-Ready Package',
        subtitle: 'One click. Four formats. Audit-ready.',
        before: {
            label: 'Export Package Contents',
            items: [
                'EPCIS 2.0 JSON-LD — GS1 standard format for trading partner interoperability',
                'FDA Sortable Spreadsheet — the exact format FDA expects during a 24-hour request',
                'Chain Verification Report — every hash recomputed and compared',
                'Export Manifest — package metadata with SHA-256 integrity',
            ],
        },
        after: {
            label: 'What the Buyer Gets',
            items: [
                'Complete traceability chain from farm to store',
                'Every CTE type covered (all 7 FSMA 204 event types)',
                'Portable: download, archive off-platform, verify independently',
                'Proof: not just data, but cryptographic evidence of integrity',
            ],
        },
        screenshot: null,
    },
    {
        num: '5',
        icon: Shield,
        title: 'Verify: Don\'t Trust, Prove',
        subtitle: 'Open-source script. No RegEngine account needed.',
        before: {
            label: 'Verification Process',
            items: [
                'Download verify_chain.py (MIT licensed, zero dependencies for offline mode)',
                'Run against your exported JSON — entirely offline',
                'Script recomputes every SHA-256 hash from raw record fields',
                'Compares computed hash to stored hash. Mismatch = tampered record.',
            ],
        },
        after: {
            label: 'Verification Output',
            items: [
                '✓ VALID: 12/12 records passed',
                '✓ Chain integrity: INTACT',
                '✓ No tampering detected',
                '✓ Manifest hash matches package contents',
            ],
        },
        screenshot: null,
    },
];

export default function WalkthroughPage() {
    return (
        <div style={{ background: T.bg, minHeight: '100vh', color: T.text }}>
            {/* Hero */}
            <section style={{ maxWidth: 960, margin: '0 auto', padding: '80px 24px 60px', textAlign: 'center' }}>
                <div style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '6px 16px', background: T.accentDim, borderRadius: 20, fontSize: 13, color: T.accent, fontWeight: 500, marginBottom: 24 }}>
                    <Terminal size={14} />
                    Operational Walkthrough — Not Marketing
                </div>

                <h1 style={{ fontSize: 'clamp(32px, 5vw, 48px)', fontWeight: 700, lineHeight: 1.1, margin: '0 0 16px' }}>
                    From Messy CSV to Audit-Ready Export
                </h1>

                <p style={{ fontSize: 17, color: T.textDim, maxWidth: 600, margin: '0 auto 12px', lineHeight: 1.6 }}>
                    This is the complete RegEngine workflow — from raw supplier data to
                    FDA-ready evidence package — in five steps.
                </p>
                <p style={{ fontSize: 14, color: T.textMuted, maxWidth: 520, margin: '0 auto 32px' }}>
                    Not a concept. Not architecture copy. This is what actually happens when
                    a supplier uploads their data.
                </p>

                {/* Pipeline visualization */}
                <div style={{ display: 'flex', justifyContent: 'center', gap: 6, flexWrap: 'wrap', alignItems: 'center', marginBottom: 40 }}>
                    {['Upload', 'Validate', 'Commit', 'Export', 'Verify'].map((step, i) => (
                        <div key={step} style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{
                                fontSize: 13, fontWeight: 600, color: T.accent,
                                background: T.accentDim, padding: '6px 14px', borderRadius: 8,
                            }}>{step}</span>
                            {i < 4 && <ArrowRight size={14} style={{ color: T.textDim }} />}
                        </div>
                    ))}
                </div>
            </section>

            {/* Steps */}
            <section style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px 60px' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 40 }}>
                    {STEPS.map((step) => {
                        const Icon = step.icon;
                        return (
                            <div key={step.num} style={{
                                background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16,
                                overflow: 'hidden',
                            }}>
                                {/* Step header */}
                                <div style={{
                                    padding: '24px 28px', borderBottom: `1px solid ${T.border}`,
                                    display: 'flex', alignItems: 'center', gap: 16,
                                    background: T.elevated,
                                }}>
                                    <div style={{
                                        width: 44, height: 44, borderRadius: 12,
                                        background: T.accentDim, display: 'flex', alignItems: 'center', justifyContent: 'center',
                                    }}>
                                        <Icon size={20} style={{ color: T.accent }} />
                                    </div>
                                    <div>
                                        <div style={{ fontSize: 11, color: T.accent, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 2 }}>
                                            Step {step.num}
                                        </div>
                                        <div style={{ fontSize: 18, fontWeight: 700 }}>{step.title}</div>
                                        <div style={{ fontSize: 13, color: T.textDim }}>{step.subtitle}</div>
                                    </div>
                                </div>

                                {/* Before / After */}
                                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 0 }}>
                                    {/* Before / Input */}
                                    <div style={{ padding: '24px 28px', borderRight: `1px solid ${T.border}` }}>
                                        <div style={{
                                            display: 'inline-flex', alignItems: 'center', gap: 6,
                                            fontSize: 11, fontWeight: 600, color: T.warning,
                                            background: T.warningDim, padding: '3px 10px', borderRadius: 6, marginBottom: 16,
                                        }}>
                                            <Eye size={12} /> {step.before.label}
                                        </div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                            {step.before.items.map((item, i) => (
                                                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                                                    <span style={{ color: T.warning, fontSize: 12, marginTop: 2, flexShrink: 0 }}>•</span>
                                                    <span style={{ fontSize: 13, color: T.textDim, lineHeight: 1.5 }}>{item}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>

                                    {/* After / Output */}
                                    <div style={{ padding: '24px 28px' }}>
                                        <div style={{
                                            display: 'inline-flex', alignItems: 'center', gap: 6,
                                            fontSize: 11, fontWeight: 600, color: T.accent,
                                            background: T.accentDim, padding: '3px 10px', borderRadius: 6, marginBottom: 16,
                                        }}>
                                            <CheckCircle2 size={12} /> {step.after.label}
                                        </div>
                                        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                                            {step.after.items.map((item, i) => (
                                                <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'flex-start' }}>
                                                    <CheckCircle2 size={14} style={{ color: T.accent, marginTop: 2, flexShrink: 0 }} />
                                                    <span style={{ fontSize: 13, color: T.text, lineHeight: 1.5 }}>{item}</span>
                                                </div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        );
                    })}
                </div>
            </section>

            {/* Where RegEngine Fits */}
            <section style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px 60px' }}>
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 12, padding: 32 }}>
                    <h3 style={{ fontSize: 20, fontWeight: 600, marginBottom: 8, textAlign: 'center' }}>
                        Where RegEngine Fits
                    </h3>
                    <p style={{ fontSize: 14, color: T.textDim, textAlign: 'center', marginBottom: 24, maxWidth: 560, margin: '0 auto 24px' }}>
                        RegEngine is an evidence layer — not a system-of-record replacement.
                        It sits between your existing operational systems and the export formats
                        that regulators and retailers demand.
                    </p>
                    <div style={{ display: 'flex', justifyContent: 'center', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
                        {[
                            { label: 'Your ERP / WMS / Spreadsheets', color: T.textDim, bg: 'transparent', border: T.border },
                            { label: '→', color: T.textDim, bg: 'transparent', border: 'transparent' },
                            { label: 'RegEngine Evidence Layer', color: '#000', bg: T.accent, border: T.accent },
                            { label: '→', color: T.textDim, bg: 'transparent', border: 'transparent' },
                            { label: 'FDA / Walmart / Kroger', color: T.textDim, bg: 'transparent', border: T.border },
                        ].map((item, i) => (
                            <span key={i} style={{
                                fontSize: item.label === '→' ? 16 : 12,
                                fontWeight: 600,
                                color: item.color,
                                background: item.bg,
                                border: `1px solid ${item.border}`,
                                padding: item.label === '→' ? '0 4px' : '8px 16px',
                                borderRadius: 8,
                            }}>{item.label}</span>
                        ))}
                    </div>
                </div>
            </section>

            {/* CTA */}
            <section style={{ maxWidth: 960, margin: '0 auto', padding: '0 24px 80px', textAlign: 'center' }}>
                <div style={{ background: T.surface, border: `1px solid ${T.border}`, borderRadius: 16, padding: '48px 32px' }}>
                    <h2 style={{ fontSize: 28, fontWeight: 600, marginBottom: 12 }}>
                        See the output for yourself.
                    </h2>
                    <p style={{ fontSize: 15, color: T.textDim, maxWidth: 480, margin: '0 auto 28px', lineHeight: 1.6 }}>
                        Download a sample export package or try the bulk upload with your own data.
                    </p>
                    <div className="flex gap-3 justify-center flex-wrap">
                        <Link href="/sample-export" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 24px', background: T.accent, color: '#000', borderRadius: 8, fontSize: 15, fontWeight: 600, textDecoration: 'none' }}>
                            <Download size={16} /> View Sample Export
                        </Link>
                        <Link href="/onboarding/bulk-upload" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 24px', background: T.elevated, border: `1px solid ${T.border}`, color: T.text, borderRadius: 8, fontSize: 15, fontWeight: 500, textDecoration: 'none' }}>
                            <Upload size={16} /> Try Bulk Upload
                        </Link>
                        <Link href="/founding-design-partners" style={{ display: 'inline-flex', alignItems: 'center', gap: 8, padding: '12px 24px', background: T.elevated, border: `1px solid ${T.border}`, color: T.text, borderRadius: 8, fontSize: 15, fontWeight: 500, textDecoration: 'none' }}>
                            Become a Partner <ArrowRight size={14} />
                        </Link>
                    </div>
                </div>
            </section>
        </div>
    );
}
