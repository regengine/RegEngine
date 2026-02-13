'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    ShieldCheck,
    Terminal,
    Download,
    ExternalLink,
    CheckCircle2,
    Lock,
    FileCode,
    Github,
    Copy,
    Check,
} from 'lucide-react';

/* ─────────────────────────────────────────────────────────────
   DESIGN TOKENS (matches FTL Checker dark theme)
   ───────────────────────────────────────────────────────────── */
const T = {
    bg: 'var(--re-surface-base)',
    surface: 'rgba(255,255,255,0.02)',
    elevated: 'rgba(255,255,255,0.05)',
    border: 'rgba(255,255,255,0.06)',
    borderHover: 'rgba(255,255,255,0.12)',
    text: 'var(--re-text-primary)',
    textDim: 'var(--re-text-tertiary)',
    textMuted: 'var(--re-text-muted)',
    accent: 'var(--re-success)',
    accentDim: 'rgba(34,197,94,0.12)',
    mono: "'SF Mono', 'Fira Code', 'JetBrains Mono', Consolas, monospace",
    brand: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
};

const VERIFY_SCRIPT_URL = '/regengine/verify_chain.py';

const TERMINAL_OUTPUT = `$ python verify_chain.py --file export_2026_02.json --offline

============================================================
REGENGINE CHAIN VERIFICATION REPORT
============================================================
Verified at: 2026-02-06T20:14:33Z
------------------------------------------------------------

✓ VALID: ROM-0206-F3-001
  Expected:  sha256:a3b8d1b6e0f2c45d89ab...
  Computed:  sha256:a3b8d1b6e0f2c45d89ab...

✓ VALID: ROM-0206-F3-002
  Expected:  sha256:4f7c2e1a9d8b3f650c12...
  Computed:  sha256:4f7c2e1a9d8b3f650c12...

✓ VALID: SAL-0206-SEA-001
  Expected:  sha256:9e3d7c854b6a2f10de89...
  Computed:  sha256:9e3d7c854b6a2f10de89...

✓ VALID: KAL-0205-F1-003
  Expected:  sha256:72c4f8a1b3d9e56702af...
  Computed:  sha256:72c4f8a1b3d9e56702af...

✓ VALID: SPN-0204-PACK-007
  Expected:  sha256:5a1b9c3d7e4f8206abcd...
  Computed:  sha256:5a1b9c3d7e4f8206abcd...

------------------------------------------------------------
SUMMARY: 5 passed, 0 failed, 5 total
============================================================`;

const CODE_SAMPLE = `#!/usr/bin/env python3
"""Verify RegEngine records independently."""

from verify_chain import compute_record_hash, verify_file
from pathlib import Path

# Option 1: Verify an exported JSON file offline
results = verify_file(Path("audit_export.json"))
for r in results:
    status = "✓" if r.valid else "✗"
    print(f"{status} {r.tlc}: {r.computed_hash[:32]}...")

# Option 2: Verify a single record online
from verify_chain import verify_record_online
result = verify_record_online(
    tlc="ROM-0206-F3-001",
    api_key="rge_live_your_key_here"
)
print(f"Valid: {result.valid}")

# Option 3: Compute a hash yourself
record = {
    "tlc": "ROM-0206-F3-001",
    "cte_type": "HARVESTING",
    "location": "0614141000001",
    "quantity": 500,
    "unit_of_measure": "cases",
    "product_description": "Romaine Lettuce Hearts 12ct",
    "event_timestamp": "2026-02-06T06:00:00Z",
    "input_tlcs": [],
}
hash_val = compute_record_hash(record)
print(f"Hash: {hash_val}")
# → sha256:a3b8d1b6e0f2c45d89ab...`;

const INSTALL_STEPS = [
    {
        title: 'Download the script',
        code: 'curl -O https://regengine.co/sdk/verify_chain.py',
        desc: 'Single file, no package manager needed.',
    },
    {
        title: 'Optional: install requests',
        code: 'pip install requests',
        desc: 'Only needed for online verification against the API.',
    },
    {
        title: 'Verify your records',
        code: 'python verify_chain.py --file your_export.json --offline',
        desc: 'Works entirely offline. No RegEngine account required.',
    },
];

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);
    return (
        <button
            onClick={() => {
                navigator.clipboard.writeText(text);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
            }}
            style={{
                background: 'none',
                border: 'none',
                cursor: 'pointer',
                color: copied ? T.accent : T.textDim,
                padding: '4px',
            }}
            title="Copy to clipboard"
        >
            {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
    );
}

export default function VerifyPage() {
    return (
        <div style={{ background: T.bg, minHeight: '100vh', color: T.text }}>
            {/* ─── Hero ──────────────────────────────────────────────── */}
            <section
                style={{
                    maxWidth: 960,
                    margin: '0 auto',
                    padding: '80px 24px 60px',
                    textAlign: 'center',
                }}
            >
                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                >
                    <div
                        style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: 8,
                            padding: '6px 16px',
                            background: T.accentDim,
                            borderRadius: 20,
                            fontSize: 13,
                            color: T.accent,
                            fontWeight: 500,
                            marginBottom: 24,
                        }}
                    >
                        <ShieldCheck size={14} />
                        Open Source • MIT License
                    </div>

                    <h1
                        style={{
                            fontSize: 'clamp(32px, 5vw, 56px)',
                            fontWeight: 700,
                            fontFamily: T.brand,
                            lineHeight: 1.1,
                            margin: '0 0 16px',
                        }}
                    >
                        Verify, Don&apos;t Trust
                    </h1>

                    <p
                        style={{
                            fontSize: 18,
                            color: T.textDim,
                            maxWidth: 640,
                            margin: '0 auto 32px',
                            lineHeight: 1.6,
                        }}
                    >
                        Every RegEngine traceability record is protected by a{' '}
                        <strong className="text-re-text-secondary">SHA-256 cryptographic hash</strong>.
                        Our open-source verification script lets you independently verify
                        record integrity — without relying on our servers.
                    </p>

                    <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                        <a
                            href="/sdk/verify_chain.py"
                            download
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 8,
                                padding: '12px 24px',
                                background: T.accent,
                                color: '#000',
                                borderRadius: 8,
                                fontSize: 15,
                                fontWeight: 600,
                                textDecoration: 'none',
                            }}
                        >
                            <Download size={16} />
                            Download verify_chain.py
                        </a>
                        <a
                            href="#how-it-works"
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 8,
                                padding: '12px 24px',
                                background: T.elevated,
                                border: `1px solid ${T.border}`,
                                color: T.text,
                                borderRadius: 8,
                                fontSize: 15,
                                fontWeight: 500,
                                textDecoration: 'none',
                            }}
                        >
                            <Terminal size={16} />
                            See How It Works
                        </a>
                    </div>
                </motion.div>
            </section>

            {/* ─── Trust Model ───────────────────────────────────────── */}
            <section className="re-page-content">
                <div
                    style={{
                        display: 'grid',
                        gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))',
                        gap: 20,
                    }}
                >
                    {[
                        {
                            icon: <Lock size={20} />,
                            title: 'Deterministic Hashing',
                            desc: 'Each record\'s immutable fields (TLC, CTE type, location, quantity, timestamp) are canonicalized and hashed with SHA-256. Same inputs always produce the same hash.',
                        },
                        {
                            icon: <FileCode size={20} />,
                            title: 'Open Source',
                            desc: 'The verification script is MIT-licensed. Read every line. Fork it. Modify it. You don\'t need to trust us — you can verify the math yourself.',
                        },
                        {
                            icon: <ShieldCheck size={20} />,
                            title: 'Offline Capable',
                            desc: 'Export your records as JSON and verify them entirely offline. No API calls, no network, no RegEngine account required.',
                        },
                    ].map((card, i) => (
                        <motion.div
                            key={i}
                            initial={{ opacity: 0, y: 20 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{ delay: i * 0.1 + 0.3 }}
                            style={{
                                background: T.surface,
                                border: `1px solid ${T.border}`,
                                borderRadius: 12,
                                padding: 24,
                            }}
                        >
                            <div style={{ color: T.accent, marginBottom: 12 }}>{card.icon}</div>
                            <h3
                                style={{
                                    fontSize: 16,
                                    fontWeight: 600,
                                    marginBottom: 8,
                                }}
                            >
                                {card.title}
                            </h3>
                            <p style={{ fontSize: 14, color: T.textDim, lineHeight: 1.5, margin: 0 }}>
                                {card.desc}
                            </p>
                        </motion.div>
                    ))}
                </div>
            </section>

            {/* ─── Terminal Output ───────────────────────────────────── */}
            <section
                id="how-it-works"
                style={{
                    maxWidth: 960,
                    margin: '0 auto',
                    padding: '0 24px 60px',
                }}
            >
                <h2
                    style={{
                        fontSize: 28,
                        fontWeight: 600,
                        marginBottom: 8,
                        textAlign: 'center',
                    }}
                >
                    What It Looks Like
                </h2>
                <p
                    style={{
                        textAlign: 'center',
                        color: T.textDim,
                        fontSize: 15,
                        marginBottom: 32,
                    }}
                >
                    Run the script against an exported JSON file. Every record is independently
                    re-hashed and compared.
                </p>

                <div
                    style={{
                        background: 'var(--re-surface-base)',
                        border: `1px solid ${T.border}`,
                        borderRadius: 12,
                        overflow: 'hidden',
                    }}
                >
                    {/* Terminal header bar */}
                    <div
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 8,
                            padding: '10px 16px',
                            background: 'rgba(255,255,255,0.03)',
                            borderBottom: `1px solid ${T.border}`,
                        }}
                    >
                        <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#ff5f56' }} />
                        <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#ffbd2e' }} />
                        <div style={{ width: 12, height: 12, borderRadius: '50%', background: '#27c93f' }} />
                        <span
                            style={{
                                marginLeft: 12,
                                fontSize: 12,
                                color: T.textMuted,
                                fontFamily: T.mono,
                            }}
                        >
                            verify_chain.py — bash
                        </span>
                    </div>

                    {/* Terminal content */}
                    <pre
                        style={{
                            margin: 0,
                            padding: 20,
                            fontFamily: T.mono,
                            fontSize: 12,
                            lineHeight: 1.6,
                            color: 'var(--re-text-secondary)',
                            overflow: 'auto',
                            maxHeight: 480,
                        }}
                    >
                        {TERMINAL_OUTPUT.split('\n').map((line, i) => {
                            let color = 'var(--re-text-secondary)';
                            if (line.startsWith('✓ VALID')) color = 'var(--re-success)';
                            if (line.startsWith('✗ INVALID')) color = 'var(--re-danger)';
                            if (line.startsWith('$')) color = 'var(--re-success)';
                            if (line.startsWith('===') || line.startsWith('---')) color = 'var(--re-text-disabled)';
                            if (line.includes('SUMMARY')) color = 'var(--re-info)';
                            if (line.includes('REGENGINE')) color = 'var(--re-info)';
                            return (
                                <span key={i} style={{ color }}>
                                    {line}
                                    {'\n'}
                                </span>
                            );
                        })}
                    </pre>
                </div>
            </section>

            {/* ─── Installation ──────────────────────────────────────── */}
            <section className="re-page-content">
                <h2
                    style={{
                        fontSize: 28,
                        fontWeight: 600,
                        marginBottom: 32,
                        textAlign: 'center',
                    }}
                >
                    Get Started in 30 Seconds
                </h2>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                    {INSTALL_STEPS.map((step, i) => (
                        <div
                            key={i}
                            style={{
                                background: T.surface,
                                border: `1px solid ${T.border}`,
                                borderRadius: 12,
                                padding: 20,
                                display: 'flex',
                                alignItems: 'flex-start',
                                gap: 16,
                            }}
                        >
                            <div
                                style={{
                                    width: 28,
                                    height: 28,
                                    borderRadius: '50%',
                                    background: T.accentDim,
                                    color: T.accent,
                                    display: 'flex',
                                    alignItems: 'center',
                                    justifyContent: 'center',
                                    fontSize: 14,
                                    fontWeight: 700,
                                    flexShrink: 0,
                                }}
                            >
                                {i + 1}
                            </div>
                            <div className="flex-1">
                                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>
                                    {step.title}
                                </div>
                                <div
                                    style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 8,
                                        background: 'var(--re-surface-base)',
                                        borderRadius: 6,
                                        padding: '8px 12px',
                                        marginBottom: 6,
                                    }}
                                >
                                    <code
                                        style={{
                                            fontFamily: T.mono,
                                            fontSize: 13,
                                            color: 'var(--re-success)',
                                            flex: 1,
                                        }}
                                    >
                                        {step.code}
                                    </code>
                                    <CopyButton text={step.code} />
                                </div>
                                <p style={{ fontSize: 13, color: T.textDim, margin: 0 }}>{step.desc}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ─── Code Sample ──────────────────────────────────────── */}
            <section className="re-page-content">
                <h2
                    style={{
                        fontSize: 28,
                        fontWeight: 600,
                        marginBottom: 8,
                        textAlign: 'center',
                    }}
                >
                    Usage Examples
                </h2>
                <p
                    style={{
                        textAlign: 'center',
                        color: T.textDim,
                        fontSize: 15,
                        marginBottom: 32,
                    }}
                >
                    Three verification modes: offline file, online API, and manual hash computation.
                </p>

                <div
                    style={{
                        background: 'var(--re-surface-base)',
                        border: `1px solid ${T.border}`,
                        borderRadius: 12,
                        overflow: 'hidden',
                    }}
                >
                    <div
                        style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            padding: '10px 16px',
                            background: 'rgba(255,255,255,0.03)',
                            borderBottom: `1px solid ${T.border}`,
                        }}
                    >
                        <span style={{ fontSize: 12, color: T.textMuted, fontFamily: T.mono }}>
                            example_usage.py
                        </span>
                        <CopyButton text={CODE_SAMPLE} />
                    </div>
                    <pre
                        style={{
                            margin: 0,
                            padding: 20,
                            fontFamily: T.mono,
                            fontSize: 12.5,
                            lineHeight: 1.6,
                            color: 'var(--re-text-secondary)',
                            overflow: 'auto',
                        }}
                    >
                        {CODE_SAMPLE.split('\n').map((line, i) => {
                            let color = 'var(--re-text-secondary)';
                            if (line.startsWith('#') || line.startsWith('"""')) color = 'var(--re-text-tertiary)';
                            if (line.startsWith('from ') || line.startsWith('import ')) color = '#ff7b72';
                            if (line.includes('print(')) color = 'var(--re-accent-purple)';
                            if (line.includes('"') || line.includes("'")) {
                                // Strings
                                if (!line.startsWith('#') && !line.startsWith('from') && !line.startsWith('import'))
                                    color = 'var(--re-info)';
                            }
                            if (line.includes('# →')) color = 'var(--re-success)';
                            return (
                                <span key={i} style={{ color }}>
                                    {line}
                                    {'\n'}
                                </span>
                            );
                        })}
                    </pre>
                </div>
            </section>

            {/* ─── Hash Algorithm ────────────────────────────────────── */}
            <section className="re-page-content">
                <h2
                    style={{
                        fontSize: 28,
                        fontWeight: 600,
                        marginBottom: 32,
                        textAlign: 'center',
                    }}
                >
                    How the Hash Works
                </h2>

                <div
                    style={{
                        background: T.surface,
                        border: `1px solid ${T.border}`,
                        borderRadius: 12,
                        padding: 32,
                    }}
                >
                    <div
                        style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                            gap: 24,
                            textAlign: 'center',
                        }}
                    >
                        {[
                            { step: '1', label: 'Extract Immutable Fields', detail: 'TLC, CTE type, location, quantity, UOM, product, timestamp, input TLCs' },
                            { step: '2', label: 'Canonicalize', detail: 'Sort keys, remove whitespace, deterministic JSON' },
                            { step: '3', label: 'SHA-256 Hash', detail: 'Standard cryptographic hash — same input → same output, always' },
                            { step: '4', label: 'Compare', detail: 'Your computed hash matches the stored hash? Record is untampered.' },
                        ].map((s, i) => (
                            <div key={i}>
                                <div
                                    style={{
                                        width: 36,
                                        height: 36,
                                        borderRadius: '50%',
                                        background: T.accentDim,
                                        color: T.accent,
                                        display: 'flex',
                                        alignItems: 'center',
                                        justifyContent: 'center',
                                        fontSize: 16,
                                        fontWeight: 700,
                                        margin: '0 auto 12px',
                                    }}
                                >
                                    {s.step}
                                </div>
                                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 6 }}>{s.label}</div>
                                <div style={{ fontSize: 13, color: T.textDim, lineHeight: 1.4 }}>{s.detail}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ─── Canonical Fields Table ────────────────────────────── */}
            <section className="re-page-content">
                <h2
                    style={{
                        fontSize: 24,
                        fontWeight: 600,
                        marginBottom: 20,
                        textAlign: 'center',
                    }}
                >
                    Immutable Fields (Hash Inputs)
                </h2>

                <div
                    style={{
                        background: T.surface,
                        border: `1px solid ${T.border}`,
                        borderRadius: 12,
                        overflow: 'hidden',
                    }}
                >
                    <table
                        style={{
                            width: '100%',
                            borderCollapse: 'collapse',
                            fontSize: 14,
                        }}
                    >
                        <thead>
                            <tr style={{ background: T.elevated }}>
                                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: `1px solid ${T.border}` }}>Field</th>
                                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: `1px solid ${T.border}` }}>Source</th>
                                <th style={{ padding: '12px 16px', textAlign: 'left', fontWeight: 600, borderBottom: `1px solid ${T.border}` }}>Example</th>
                            </tr>
                        </thead>
                        <tbody>
                            {[
                                ['tlc', 'Traceability Lot Code', 'ROM-0206-F3-001'],
                                ['cte_type', 'Critical Tracking Event', 'HARVESTING'],
                                ['location', 'GLN of facility', '0614141000001'],
                                ['quantity', 'Amount', '500'],
                                ['unit_of_measure', 'UOM', 'cases'],
                                ['product_description', 'Product name', 'Romaine Lettuce Hearts 12ct'],
                                ['event_timestamp', 'ISO 8601 UTC', '2026-02-06T06:00:00Z'],
                                ['input_tlcs', 'Upstream lots (sorted)', '[]'],
                            ].map(([field, source, example], i) => (
                                <tr key={i} style={{ borderBottom: `1px solid ${T.border}` }}>
                                    <td style={{ padding: '10px 16px', fontFamily: T.mono, fontSize: 13, color: T.accent }}>{field}</td>
                                    <td style={{ padding: '10px 16px', color: T.textDim }}>{source}</td>
                                    <td style={{ padding: '10px 16px', fontFamily: T.mono, fontSize: 12, color: T.textMuted }}>{example}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>

            {/* ─── CTA Footer ────────────────────────────────────────── */}
            <section
                style={{
                    maxWidth: 960,
                    margin: '0 auto',
                    padding: '0 24px 80px',
                    textAlign: 'center',
                }}
            >
                <div
                    style={{
                        background: T.surface,
                        border: `1px solid ${T.border}`,
                        borderRadius: 16,
                        padding: '48px 32px',
                    }}
                >
                    <ShieldCheck size={40} style={{ color: T.accent, marginBottom: 16 }} />
                    <h2 style={{ fontSize: 28, fontWeight: 600, marginBottom: 12 }}>
                        Math Trust &gt; Process Trust
                    </h2>
                    <p
                        style={{
                            fontSize: 15,
                            color: T.textDim,
                            maxWidth: 560,
                            margin: '0 auto 28px',
                            lineHeight: 1.6,
                        }}
                    >
                        Traditional compliance relies on SOC 2 attestations and auditor opinions.
                        RegEngine gives you a SHA-256 hash you can verify yourself.
                        No trust required.
                    </p>

                    <div style={{ display: 'flex', gap: 12, justifyContent: 'center', flexWrap: 'wrap' }}>
                        <a
                            href="/sdk/verify_chain.py"
                            download
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 8,
                                padding: '12px 24px',
                                background: T.accent,
                                color: '#000',
                                borderRadius: 8,
                                fontSize: 15,
                                fontWeight: 600,
                                textDecoration: 'none',
                            }}
                        >
                            <Download size={16} />
                            Download Script
                        </a>
                        <a
                            href="/ftl-checker"
                            style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: 8,
                                padding: '12px 24px',
                                background: T.elevated,
                                border: `1px solid ${T.border}`,
                                color: T.text,
                                borderRadius: 8,
                                fontSize: 15,
                                fontWeight: 500,
                                textDecoration: 'none',
                            }}
                        >
                            Check Your FTL Coverage
                            <ExternalLink size={14} />
                        </a>
                    </div>
                </div>

                {/* Fine print */}
                <p style={{ marginTop: 24, fontSize: 12, color: T.textMuted }}>
                    verify_chain.py v1.0.0 • MIT License • Python 3.8+ • Zero dependencies for offline mode
                </p>
            </section>
        </div>
    );
}
