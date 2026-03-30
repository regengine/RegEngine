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
            className="bg-transparent border-none cursor-pointer p-1"
            style={{ color: copied ? T.accent : T.textDim }}
            title="Copy to clipboard"
        >
            {copied ? <Check size={14} /> : <Copy size={14} />}
        </button>
    );
}

export default function VerifyPage() {
    return (
        <div className="min-h-screen" style={{ background: T.bg, color: T.text }}>
            {/* ─── Hero ──────────────────────────────────────────────── */}
            <section className="max-w-[960px] mx-auto text-center px-6 pt-20 pb-[60px]">

                <motion.div
                    initial={{ opacity: 0, y: 20 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5 }}
                >
                    <div
                        className="inline-flex items-center gap-2 px-4 py-1.5 rounded-[20px] text-[13px] font-medium mb-6"
                        style={{ background: T.accentDim, color: T.accent }}
                    >
                        <ShieldCheck size={14} />
                        Open Source • MIT License
                    </div>

                    <h1
                        className="text-[clamp(32px,5vw,56px)] font-bold leading-[1.1] mb-4"
                        style={{ fontFamily: T.brand }}
                    >
                        Verify, Don&apos;t Trust
                    </h1>

                    <p
                        className="text-lg max-w-[640px] mx-auto mb-8 leading-relaxed"
                        style={{ color: T.textDim }}
                    >
                        Every RegEngine traceability record is protected by a{' '}
                        <strong className="text-re-text-secondary">SHA-256 cryptographic hash</strong>.
                        Our open-source verification script lets you independently verify
                        record integrity — without relying on our servers.
                    </p>

                    <div className="flex gap-3 justify-center flex-wrap">
                        <a
                            href="/sdk/verify_chain.py"
                            download
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg text-[15px] font-semibold no-underline text-black"
                            style={{ background: T.accent }}
                        >
                            <Download size={16} />
                            Download verify_chain.py
                        </a>
                        <a
                            href="#how-it-works"
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg text-[15px] font-medium no-underline"
                            style={{ background: T.elevated, border: `1px solid ${T.border}`, color: T.text }}
                        >
                            <Terminal size={16} />
                            See How It Works
                        </a>
                    </div>
                </motion.div>
            </section>

            {/* ─── Trust Model ───────────────────────────────────────── */}
            <section className="max-w-[960px] mx-auto px-4 sm:px-6 pb-10 sm:pb-[60px]">
                <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-5">

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
                            className="rounded-xl p-6"
                            style={{ background: T.surface, border: `1px solid ${T.border}` }}
                        >
                            <div className="mb-3" style={{ color: T.accent }}>{card.icon}</div>
                            <h3 className="text-base font-semibold mb-2">
                                {card.title}
                            </h3>
                            <p className="text-sm leading-normal m-0" style={{ color: T.textDim }}>
                                {card.desc}
                            </p>
                        </motion.div>
                    ))}
                </div>
            </section>

            {/* ─── Terminal Output ───────────────────────────────────── */}
            <section
                id="how-it-works"
                className="max-w-[960px] mx-auto px-6 pb-[60px]"
            >
                <h2 className="text-[28px] font-semibold mb-2 text-center">

                    What It Looks Like
                </h2>
                <p
                    className="text-center text-[15px] mb-8"
                    style={{ color: T.textDim }}
                >
                    Run the script against an exported JSON file. Every record is independently
                    re-hashed and compared.
                </p>

                <div
                    className="rounded-xl overflow-hidden bg-[var(--re-surface-base)]"
                    style={{ border: `1px solid ${T.border}` }}
                >
                    {/* Terminal header bar */}
                    <div
                        className="flex items-center gap-2 px-4 py-2.5 bg-white/[0.03]"
                        style={{ borderBottom: `1px solid ${T.border}` }}
                    >
                        <div className="w-3 h-3 rounded-full bg-[#ff5f56]" />
                        <div className="w-3 h-3 rounded-full bg-[#ffbd2e]" />
                        <div className="w-3 h-3 rounded-full bg-[#27c93f]" />
                        <span
                            className="ml-3 text-xs"
                            style={{ color: T.textMuted, fontFamily: T.mono }}
                        >
                            verify_chain.py — bash
                        </span>
                    </div>

                    {/* Terminal content */}
                    <pre
                        className="m-0 p-5 text-xs leading-relaxed overflow-auto max-h-[480px] text-[var(--re-text-secondary)]"
                        style={{ fontFamily: T.mono }}
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
            <section className="max-w-[960px] mx-auto px-4 sm:px-6 pb-10 sm:pb-[60px]">
                <h2 className="text-[28px] font-semibold mb-8 text-center">

                    Get Started in 30 Seconds
                </h2>

                <div className="flex flex-col gap-4">
                    {INSTALL_STEPS.map((step, i) => (
                        <div
                            key={i}
                            className="rounded-xl p-5 flex items-start gap-4"
                            style={{ background: T.surface, border: `1px solid ${T.border}` }}
                        >
                            <div
                                className="w-7 h-7 rounded-full flex items-center justify-center text-sm font-bold shrink-0"
                                style={{ background: T.accentDim, color: T.accent }}
                            >
                                {i + 1}
                            </div>
                            <div className="flex-1">
                                <div className="text-[15px] font-semibold mb-1.5">
                                    {step.title}
                                </div>
                                <div className="flex items-center gap-2 bg-[var(--re-surface-base)] rounded-md px-3 py-2 mb-1.5">
                                    <code
                                        className="text-[13px] text-[var(--re-success)] flex-1"
                                        style={{ fontFamily: T.mono }}
                                    >
                                        {step.code}
                                    </code>
                                    <CopyButton text={step.code} />
                                </div>
                                <p className="text-[13px] m-0" style={{ color: T.textDim }}>{step.desc}</p>
                            </div>
                        </div>
                    ))}
                </div>
            </section>

            {/* ─── Code Sample ──────────────────────────────────────── */}
            <section className="max-w-[960px] mx-auto px-4 sm:px-6 pb-10 sm:pb-[60px]">
                <h2 className="text-[28px] font-semibold mb-2 text-center">
                    Usage Examples
                </h2>
                <p
                    className="text-center text-[15px] mb-8"
                    style={{ color: T.textDim }}
                >
                    Three verification modes: offline file, online API, and manual hash computation.
                </p>

                <div
                    className="rounded-xl overflow-hidden bg-[var(--re-surface-base)]"
                    style={{ border: `1px solid ${T.border}` }}
                >
                    <div
                        className="flex items-center justify-between px-4 py-2.5 bg-white/[0.03]"
                        style={{ borderBottom: `1px solid ${T.border}` }}
                    >
                        <span className="text-xs" style={{ color: T.textMuted, fontFamily: T.mono }}>
                            example_usage.py
                        </span>
                        <CopyButton text={CODE_SAMPLE} />
                    </div>
                    <pre
                        className="m-0 p-5 text-[12.5px] leading-relaxed text-[var(--re-text-secondary)] overflow-auto"
                        style={{ fontFamily: T.mono }}
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
            <section className="max-w-[960px] mx-auto px-4 sm:px-6 pb-10 sm:pb-[60px]">
                <h2 className="text-[28px] font-semibold mb-8 text-center">
                    How the Hash Works
                </h2>

                <div
                    className="rounded-xl p-8"
                    style={{ background: T.surface, border: `1px solid ${T.border}` }}
                >
                    <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-6 text-center">

                        {[
                            { step: '1', label: 'Extract Immutable Fields', detail: 'TLC, CTE type, location, quantity, UOM, product, timestamp, input TLCs' },
                            { step: '2', label: 'Canonicalize', detail: 'Sort keys, remove whitespace, deterministic JSON' },
                            { step: '3', label: 'SHA-256 Hash', detail: 'Standard cryptographic hash — same input → same output, always' },
                            { step: '4', label: 'Compare', detail: 'Your computed hash matches the stored hash? Record is untampered.' },
                        ].map((s, i) => (
                            <div key={i}>
                                <div
                                    className="w-9 h-9 rounded-full flex items-center justify-center text-base font-bold mx-auto mb-3"
                                    style={{ background: T.accentDim, color: T.accent }}
                                >
                                    {s.step}
                                </div>
                                <div className="text-[15px] font-semibold mb-1.5">{s.label}</div>
                                <div className="text-[13px] leading-snug" style={{ color: T.textDim }}>{s.detail}</div>
                            </div>
                        ))}
                    </div>
                </div>
            </section>

            {/* ─── Canonical Fields Table ────────────────────────────── */}
            <section className="max-w-[960px] mx-auto px-4 sm:px-6 pb-10 sm:pb-[60px]">
                <h2 className="text-2xl font-semibold mb-5 text-center">
                    Immutable Fields (Hash Inputs)
                </h2>

                <div
                    className="rounded-xl overflow-hidden"
                    style={{ background: T.surface, border: `1px solid ${T.border}` }}
                >
                    <table className="w-full border-collapse text-sm">

                        <thead>
                            <tr style={{ background: T.elevated }}>
                                <th className="px-4 py-3 text-left font-semibold" style={{ borderBottom: `1px solid ${T.border}` }}>Field</th>
                                <th className="px-4 py-3 text-left font-semibold" style={{ borderBottom: `1px solid ${T.border}` }}>Source</th>
                                <th className="px-4 py-3 text-left font-semibold" style={{ borderBottom: `1px solid ${T.border}` }}>Example</th>
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
                                    <td className="px-4 py-2.5 text-[13px]" style={{ fontFamily: T.mono, color: T.accent }}>{field}</td>
                                    <td className="px-4 py-2.5" style={{ color: T.textDim }}>{source}</td>
                                    <td className="px-4 py-2.5 text-xs" style={{ fontFamily: T.mono, color: T.textMuted }}>{example}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>

            {/* ─── CTA Footer ────────────────────────────────────────── */}
            <section className="max-w-[960px] mx-auto px-6 pb-20 text-center">
                <div
                    className="rounded-2xl px-8 py-12"
                    style={{ background: T.surface, border: `1px solid ${T.border}` }}
                >
                    <ShieldCheck size={40} className="mb-4" style={{ color: T.accent }} />
                    <h2 className="text-[28px] font-semibold mb-3">
                        Math Trust &gt; Process Trust
                    </h2>
                    <p
                        className="text-[15px] max-w-[560px] mx-auto mb-7 leading-relaxed"
                        style={{ color: T.textDim }}
                    >
                        RegEngine adds cryptographic verification on top of standard compliance controls.
                        SHA-256 hashing lets you verify record integrity independently —
                        whether or not you require a SOC 2 report.
                    </p>

                    <div className="flex gap-3 justify-center flex-wrap">
                        <a
                            href="/sdk/verify_chain.py"
                            download
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg text-[15px] font-semibold no-underline text-black"
                            style={{ background: T.accent }}
                        >
                            <Download size={16} />
                            Download Script
                        </a>
                        <a
                            href="/ftl-checker"
                            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg text-[15px] font-medium no-underline"
                            style={{ background: T.elevated, border: `1px solid ${T.border}`, color: T.text }}
                        >
                            Check Your FTL Coverage
                            <ExternalLink size={14} />
                        </a>
                    </div>
                </div>

                {/* Fine print */}
                <p className="mt-6 text-xs" style={{ color: T.textMuted }}>
                    verify_chain.py v1.0.0 • MIT License • Python 3.8+ • Zero dependencies for offline mode
                </p>
            </section>
        </div>
    );
}
