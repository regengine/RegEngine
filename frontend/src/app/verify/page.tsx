'use client';

import { useCallback, useRef, useState } from 'react';
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
    Upload,
    XCircle,
    Loader2,
    FileArchive,
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

const PROOF_VERIFY_ENDPOINT = '/api/ingestion/api/v1/proof/verify';

const TERMINAL_OUTPUT = `$ python verify_chain.py audit-bundle.zip
manifest: ok
files: 2 / 2 sha256 matches
merkle: root recomputed and matched
result: bundle intact`;

const CODE_SAMPLE = `#!/usr/bin/env python3
"""Run the public RegEngine bundle verifier from Python."""

from pathlib import Path
import subprocess
import sys

bundle = Path("audit-bundle.zip")
result = subprocess.run(
    [sys.executable, "verify_chain.py", str(bundle)],
    check=False,
    text=True,
    capture_output=True,
)

print(result.stdout, end="")
if result.stderr:
    print(result.stderr, file=sys.stderr, end="")

raise SystemExit(result.returncode)`;

const INSTALL_STEPS = [
    {
        title: 'Download the script',
        code: 'curl -O https://regengine.co/sdk/verify_chain.py',
        desc: 'Single file, no package manager needed.',
    },
    {
        title: 'Download a sample bundle',
        code: 'curl -O https://regengine.co/proof/audit-bundle.zip',
        desc: 'The ZIP contains manifest.json plus synthetic FSMA/EPCIS evidence files.',
    },
    {
        title: 'Verify the bundle',
        code: 'python verify_chain.py audit-bundle.zip',
        desc: 'Works entirely offline. No RegEngine account required.',
    },
];

/* ─────────────────────────────────────────────────────────────
   VerifyWidget — drop-and-verify export bundle
   ───────────────────────────────────────────────────────────── */
type VerifyCheck = { name: string; passed: boolean; detail?: string };
type VerifyResponse = {
    verified: boolean;
    checks: VerifyCheck[];
    merkle_root_recomputed: string;
    timestamp: string;
};

type VerifyState =
    | { kind: 'idle' }
    | { kind: 'loading' }
    | { kind: 'success'; data: VerifyResponse }
    | { kind: 'error'; message: string };

function VerifyWidget() {
    const [state, setState] = useState<VerifyState>({ kind: 'idle' });
    const [file, setFile] = useState<File | null>(null);
    const [dragOver, setDragOver] = useState(false);
    const inputRef = useRef<HTMLInputElement>(null);

    const handleFile = useCallback((f: File | null) => {
        if (!f) return;
        setFile(f);
        setState({ kind: 'idle' });
    }, []);

    const onDrop = useCallback(
        (e: React.DragEvent<HTMLDivElement>) => {
            e.preventDefault();
            setDragOver(false);
            const f = e.dataTransfer.files?.[0] ?? null;
            handleFile(f);
        },
        [handleFile],
    );

    const onSubmit = useCallback(async () => {
        if (!file) return;
        setState({ kind: 'loading' });

        const formData = new FormData();
        formData.append('bundle', file);

        try {
            const res = await fetch(PROOF_VERIFY_ENDPOINT, {
                method: 'POST',
                body: formData,
            });

            if (res.status === 429) {
                setState({
                    kind: 'error',
                    message:
                        'Rate limit reached (10/min). Try again in a minute.',
                });
                return;
            }

            if (!res.ok) {
                setState({
                    kind: 'error',
                    message: `Verification failed (HTTP ${res.status}). Try again shortly, or run verify_chain.py locally.`,
                });
                return;
            }

            const data = (await res.json()) as VerifyResponse;
            setState({ kind: 'success', data });
        } catch {
            setState({
                kind: 'error',
                message:
                    'Could not reach the verifier endpoint. Try again shortly, or run verify_chain.py locally.',
            });
        }
    }, [file]);

    const reset = useCallback(() => {
        setFile(null);
        setState({ kind: 'idle' });
        if (inputRef.current) inputRef.current.value = '';
    }, []);

    return (
        <div
            className="rounded-2xl p-6 sm:p-8"
            style={{ background: T.surface, border: `1px solid ${T.border}` }}
        >
            {/* ─── Drop zone ─────────────────────────────────────── */}
            {state.kind !== 'success' && (
                <div
                    onDragOver={(e) => {
                        e.preventDefault();
                        setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={onDrop}
                    onClick={() => inputRef.current?.click()}
                    className="rounded-xl px-6 py-10 text-center cursor-pointer transition-colors"
                    style={{
                        background: dragOver ? T.elevated : 'transparent',
                        border: `2px dashed ${dragOver ? T.accent : T.border}`,
                    }}
                >
                    <input
                        ref={inputRef}
                        type="file"
                        accept=".zip,.json,application/zip,application/json"
                        className="hidden"
                        onChange={(e) =>
                            handleFile(e.target.files?.[0] ?? null)
                        }
                    />
                    <div className="flex flex-col items-center gap-3">
                        {file ? (
                            <FileArchive size={32} style={{ color: T.accent }} />
                        ) : (
                            <Upload size={32} style={{ color: T.textDim }} />
                        )}
                        <div className="text-[15px] font-semibold">
                            {file
                                ? file.name
                                : 'Drop your export bundle here'}
                        </div>
                        <div className="text-[13px]" style={{ color: T.textDim }}>
                            {file
                                ? `${(file.size / 1024).toFixed(1)} KB — click to choose a different file`
                                : 'or click to browse — accepts .zip or .json'}
                        </div>
                    </div>
                </div>
            )}

            {/* ─── Action row ────────────────────────────────────── */}
            {state.kind !== 'success' && (
                <div className="flex flex-wrap gap-3 mt-5 items-center">
                    <button
                        onClick={onSubmit}
                        disabled={!file || state.kind === 'loading'}
                        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg text-[14px] font-semibold text-black disabled:opacity-50 disabled:cursor-not-allowed"
                        style={{ background: T.accent, border: 'none' }}
                    >
                        {state.kind === 'loading' ? (
                            <>
                                <Loader2
                                    size={14}
                                    className="animate-spin"
                                />
                                Verifying…
                            </>
                        ) : (
                            <>
                                <ShieldCheck size={14} />
                                Verify bundle
                            </>
                        )}
                    </button>
                    {file && state.kind !== 'loading' && (
                        <button
                            onClick={reset}
                            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-lg text-[14px] font-medium"
                            style={{
                                background: 'transparent',
                                border: `1px solid ${T.border}`,
                                color: T.textDim,
                            }}
                        >
                            Clear
                        </button>
                    )}
                    {state.kind === 'error' && (
                        <span
                            className="text-[13px] ml-1"
                            style={{ color: 'var(--re-danger)' }}
                        >
                            {state.message}
                        </span>
                    )}
                </div>
            )}

            {/* ─── Results ───────────────────────────────────────── */}
            {state.kind === 'success' && (
                <div className="flex flex-col gap-5">
                    <div className="flex items-center gap-3">
                        {state.data.verified ? (
                            <CheckCircle2
                                size={48}
                                style={{ color: T.accent }}
                            />
                        ) : (
                            <XCircle
                                size={48}
                                style={{ color: 'var(--re-danger)' }}
                            />
                        )}
                        <div>
                            <div
                                className="text-2xl font-bold"
                                style={{
                                    color: state.data.verified
                                        ? T.accent
                                        : 'var(--re-danger)',
                                }}
                            >
                                {state.data.verified ? 'Verified' : 'Failed'}
                            </div>
                            <div
                                className="text-[13px]"
                                style={{ color: T.textDim }}
                            >
                                {state.data.checks.filter((c) => c.passed).length}{' '}
                                of {state.data.checks.length} checks passed
                            </div>
                        </div>
                    </div>

                    <div
                        className="rounded-xl overflow-hidden"
                        style={{ border: `1px solid ${T.border}` }}
                    >
                        {state.data.checks.map((c, i) => (
                            <div
                                key={i}
                                className="flex items-start gap-3 px-4 py-3"
                                style={{
                                    borderBottom:
                                        i < state.data.checks.length - 1
                                            ? `1px solid ${T.border}`
                                            : 'none',
                                    background:
                                        i % 2 === 0 ? 'transparent' : T.surface,
                                }}
                            >
                                <div className="mt-0.5 shrink-0">
                                    {c.passed ? (
                                        <CheckCircle2
                                            size={16}
                                            style={{ color: T.accent }}
                                        />
                                    ) : (
                                        <XCircle
                                            size={16}
                                            style={{ color: 'var(--re-danger)' }}
                                        />
                                    )}
                                </div>
                                <div className="flex-1 min-w-0">
                                    <div className="text-[14px] font-medium">
                                        {c.name}
                                    </div>
                                    {c.detail && (
                                        <div
                                            className="text-[12.5px] mt-0.5 break-all"
                                            style={{
                                                color: T.textDim,
                                                fontFamily: T.mono,
                                            }}
                                        >
                                            {c.detail}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>

                    <div
                        className="rounded-lg p-4 text-[12.5px]"
                        style={{
                            background: T.bg,
                            border: `1px solid ${T.border}`,
                            fontFamily: T.mono,
                            color: T.textDim,
                        }}
                    >
                        <div className="break-all">
                            <span style={{ color: T.textMuted }}>
                                merkle_root_recomputed:{' '}
                            </span>
                            <span style={{ color: T.text }}>
                                {state.data.merkle_root_recomputed}
                            </span>
                        </div>
                        <div className="mt-1">
                            <span style={{ color: T.textMuted }}>
                                timestamp:{' '}
                            </span>
                            <span style={{ color: T.text }}>
                                {state.data.timestamp}
                            </span>
                        </div>
                    </div>

                    <div>
                        <button
                            onClick={reset}
                            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-[13px] font-medium"
                            style={{
                                background: 'transparent',
                                border: `1px solid ${T.border}`,
                                color: T.text,
                            }}
                        >
                            Verify another bundle
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}

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
                        Open Source • Apache 2.0 License
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
                        Every public RegEngine proof bundle carries a{' '}
                        <strong className="text-re-text-secondary">SHA-256 manifest and Merkle root</strong>.
                        Our open-source verification script lets you independently verify
                        bundle integrity — without relying on our servers.
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

            {/* ─── Upload widget ─────────────────────────────────────── */}
            <section
                id="verify-widget"
                className="max-w-[760px] mx-auto px-4 sm:px-6 pb-10 sm:pb-[60px]"
            >
                <div className="mb-6 flex flex-col gap-3">
                    <h2 className="text-2xl font-semibold">
                        Verify an export bundle
                    </h2>
                    <p
                        className="text-[14.5px] leading-relaxed m-0"
                        style={{ color: T.textDim }}
                    >
                        Drop in a RegEngine export bundle (the <code style={{ fontFamily: T.mono, color: T.text }}>.zip</code> or{' '}
                        <code style={{ fontFamily: T.mono, color: T.text }}>.json</code> you downloaded
                        from the proof page) and we&apos;ll re-run the same integrity checks the public
                        verifier runs: file SHA-256 checks, Merkle root match against the manifest,
                        and manifest consistency.
                    </p>
                    <p
                        className="text-[14.5px] leading-relaxed m-0"
                        style={{ color: T.textDim }}
                    >
                        Your file is sent to a public verifier endpoint that runs the same algorithm
                        as the export pipeline — no auth, no email capture. Want to verify entirely
                        offline?{' '}
                        <a
                            href="/sdk/verify_chain.py"
                            download
                            className="underline"
                            style={{ color: T.accent }}
                        >
                            Download verify_chain.py
                        </a>{' '}
                        and run it locally — same algorithm, zero network.
                    </p>
                </div>

                <VerifyWidget />

                <div
                    className="mt-5 rounded-lg px-4 py-3 text-[13px] flex items-center gap-2 flex-wrap"
                    style={{
                        background: T.surface,
                        border: `1px solid ${T.border}`,
                        color: T.textDim,
                    }}
                >
                    <span>Don&apos;t have a bundle yet?</span>
                    <a
                        href="/proof"
                        className="inline-flex items-center gap-1 underline"
                        style={{ color: T.accent }}
                    >
                        Grab a sample on the proof page
                        <ExternalLink size={12} />
                    </a>
                    <span>and feed it back in here.</span>
                </div>
            </section>

            {/* ─── Trust Model ───────────────────────────────────────── */}
            <section className="max-w-[960px] mx-auto px-4 sm:px-6 pb-10 sm:pb-[60px]">
                <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-5">

                    {[
                        {
                            icon: <Lock size={20} />,
                            title: 'Deterministic File Hashing',
                            desc: 'Every evidence file in the bundle is hashed with SHA-256 and compared with the manifest. Same bytes always produce the same hash.',
                        },
                        {
                            icon: <FileCode size={20} />,
                            title: 'Open Source',
                            desc: 'The verification script is Apache 2.0-licensed. Read every line. Fork it. Modify it. You don\'t need to trust us — you can verify the math yourself.',
                        },
                        {
                            icon: <ShieldCheck size={20} />,
                            title: 'Offline Capable',
                            desc: 'Download the ZIP and verify it entirely offline. No API calls, no network, no RegEngine account required.',
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
                    Run the script against an audit ZIP. Every evidence file is re-hashed and the
                    Merkle root is rebuilt.
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
                    Offline bundle verification with a non-zero exit code if anything has drifted.
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
                    How the Bundle Check Works
                </h2>

                <div
                    className="rounded-xl p-8"
                    style={{ background: T.surface, border: `1px solid ${T.border}` }}
                >
                    <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-6 text-center">

                        {[
                            { step: '1', label: 'Read Manifest', detail: 'Load manifest.json from the audit bundle ZIP' },
                            { step: '2', label: 'Hash Files', detail: 'Recompute SHA-256 for each declared evidence file' },
                            { step: '3', label: 'Rebuild Merkle Root', detail: 'Use the file hashes as leaves with the published tree algorithm' },
                            { step: '4', label: 'Compare', detail: 'If every file hash and the root match, the bundle is intact.' },
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
                    Manifest Fields (Hash Inputs)
                </h2>

                <div
                    className="rounded-xl overflow-hidden"
                    style={{ background: T.surface, border: `1px solid ${T.border}` }}
                >
                    <table className="w-full border-collapse text-sm">

                        <thead>
                            <tr style={{ background: T.elevated }}>
                                <th className="px-4 py-3 text-left font-semibold" style={{ borderBottom: `1px solid ${T.border}` }}>Field</th>
                                <th className="px-4 py-3 text-left font-semibold" style={{ borderBottom: `1px solid ${T.border}` }}>Meaning</th>
                                <th className="px-4 py-3 text-left font-semibold" style={{ borderBottom: `1px solid ${T.border}` }}>Example</th>
                            </tr>
                        </thead>
                        <tbody>
                            {[
                                ['files[].path', 'Evidence file inside the ZIP', 'fsma-204-sample.csv'],
                                ['files[].sha256', 'Declared SHA-256 digest for that file', 'ab250df1f9ed...'],
                                ['files[].size', 'Declared byte length', '1524'],
                                ['merkle.leaves[]', 'Ordered file hashes used as tree leaves', 'ab250df1f9ed...'],
                                ['merkle.root', 'Declared root of the evidence tree', 'a320428f4057...'],
                                ['build.commit', 'Code revision that produced the sample bundle', '64542033f908...'],
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
                        SHA-256 hashing lets you verify bundle integrity independently —
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
                            href="/tools/ftl-checker"
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
                    verify_chain.py v1.0.0 • Apache 2.0 License • Python 3.8+ • Zero dependencies for offline mode
                </p>
            </section>
        </div>
    );
}
