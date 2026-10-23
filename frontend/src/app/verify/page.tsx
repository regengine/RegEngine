'use client';

import { useCallback, useRef, useState } from 'react';
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
    FileArchive,
} from 'lucide-react';

import { Container } from '@/components/layout/container';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Callout } from '@/components/ui/callout';
import { Card, CardHeader } from '@/components/ui/card';
import { DataTable, type DataTableColumn } from '@/components/ui/data-table';
import { EmptyState } from '@/components/ui/empty-state';
import { StatusBadge } from '@/components/ui/status-badge';
import { cn } from '@/lib/utils';

const PROOF_VERIFY_ENDPOINT = '/api/ingestion/api/v1/proof/verify';

const TERMINAL_OUTPUT = `$ python verify_chain.py audit-bundle.zip
manifest: ok
files: N / N sha256 matches
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
        title: 'Export your own bundle',
        code: undefined,
        desc: 'Use the audit bundle ZIP you exported from your RegEngine workspace. It contains manifest.json plus your evidence files.',
    },
    {
        title: 'Verify the bundle',
        code: 'python verify_chain.py audit-bundle.zip',
        desc: 'Works entirely offline. No RegEngine account required.',
    },
];

const TRUST_MODEL = [
    {
        Icon: Lock,
        title: 'Deterministic File Hashing',
        desc: 'Every evidence file in the bundle is hashed with SHA-256 and compared with the manifest. Same bytes always produce the same hash.',
    },
    {
        Icon: FileCode,
        title: 'Open Source',
        desc: 'The verification script is Apache 2.0-licensed. Read every line. Fork it. Modify it. You don\'t need to trust us — you can verify the math yourself.',
    },
    {
        Icon: ShieldCheck,
        title: 'Offline Capable',
        desc: 'Download the ZIP and verify it entirely offline. No API calls, no network, no RegEngine account required.',
    },
];

const BUNDLE_CHECK_STEPS = [
    { step: '1', label: 'Read Manifest', detail: 'Load manifest.json from the audit bundle ZIP' },
    { step: '2', label: 'Hash Files', detail: 'Recompute SHA-256 for each declared evidence file' },
    { step: '3', label: 'Rebuild Merkle Root', detail: 'Use the file hashes as leaves with the published tree algorithm' },
    { step: '4', label: 'Compare', detail: 'If every file hash and the root match the manifest inside the bundle, the bundle is self-consistent. The check does not authenticate who produced it.' },
];

type ManifestField = { field: string; meaning: string };

const MANIFEST_FIELDS: ManifestField[] = [
    { field: 'files[].path', meaning: 'Evidence file inside the ZIP' },
    { field: 'files[].sha256', meaning: 'Declared SHA-256 digest for that file' },
    { field: 'files[].size', meaning: 'Declared byte length' },
    { field: 'merkle.leaves[]', meaning: 'Ordered file hashes used as tree leaves' },
    { field: 'merkle.root', meaning: 'Declared root of the evidence tree' },
    { field: 'build.commit', meaning: 'Code revision that produced the bundle' },
];

const MANIFEST_COLUMNS: DataTableColumn<ManifestField>[] = [
    { key: 'field', header: 'Field', mono: true, width: '14rem' },
    { key: 'meaning', header: 'Meaning' },
];

const PROSE_LINK =
    'text-re-brand underline underline-offset-[3px] decoration-re-border-strong hover:decoration-re-brand';

/** Terminal transcript colouring — the word on the line always carries the meaning too. */
function transcriptLineClass(line: string): string {
    if (line.startsWith('✓ VALID')) return 'text-re-success';
    if (line.startsWith('✗ INVALID')) return 'text-re-danger';
    if (line.startsWith('$')) return 'text-re-text-primary';
    if (line.startsWith('===') || line.startsWith('---')) return 'text-re-text-disabled';
    if (line.includes('SUMMARY')) return 'text-re-info';
    if (line.includes('REGENGINE')) return 'text-re-info';
    return 'text-re-text-secondary';
}

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
        (e: React.DragEvent<HTMLLabelElement>) => {
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
        <Card className="p-6 sm:p-8">
            {/* ─── Drop zone ─────────────────────────────────────── */}
            {state.kind !== 'success' && (
                <label
                    htmlFor="verify-bundle-file"
                    onDragOver={(e) => {
                        e.preventDefault();
                        setDragOver(true);
                    }}
                    onDragLeave={() => setDragOver(false)}
                    onDrop={onDrop}
                    className="block cursor-pointer"
                >
                    <input
                        id="verify-bundle-file"
                        ref={inputRef}
                        type="file"
                        accept=".zip,.json,application/zip,application/json"
                        className="sr-only"
                        onChange={(e) =>
                            handleFile(e.target.files?.[0] ?? null)
                        }
                    />
                    <EmptyState
                        icon={file ? FileArchive : Upload}
                        title={file ? file.name : 'Drop your export bundle here'}
                        description={
                            file
                                ? `${(file.size / 1024).toFixed(1)} KB — click to choose a different file`
                                : 'or click to browse — accepts .zip or .json'
                        }
                        className={cn(
                            'transition-colors duration-120 motion-reduce:transition-none',
                            dragOver && 'border-re-brand bg-re-surface-inset',
                        )}
                    />
                </label>
            )}

            {/* ─── Action row ────────────────────────────────────── */}
            {state.kind !== 'success' && (
                <div className="mt-5 flex flex-wrap items-center gap-3">
                    <Button
                        size="lg"
                        onClick={onSubmit}
                        disabled={!file}
                        loading={state.kind === 'loading'}
                        leadingIcon={<ShieldCheck strokeWidth={1.75} aria-hidden="true" />}
                    >
                        {state.kind === 'loading' ? 'Verifying…' : 'Verify bundle'}
                    </Button>
                    {file && state.kind !== 'loading' && (
                        <Button variant="secondary" size="lg" onClick={reset}>
                            Clear
                        </Button>
                    )}
                </div>
            )}

            {state.kind === 'error' && (
                <Callout tone="danger" role="alert" className="mt-4">
                    {state.message}
                </Callout>
            )}

            {/* ─── Results ───────────────────────────────────────── */}
            {state.kind === 'success' && (
                <div className="flex flex-col gap-5">
                    <div className="flex flex-wrap items-center gap-3">
                        <StatusBadge
                            state={state.data.verified ? 'compliant' : 'non-compliant'}
                            label={state.data.verified ? 'Self-consistent' : 'Failed'}
                        />
                        <p className="text-ui text-re-text-secondary">
                            {state.data.checks.filter((c) => c.passed).length}{' '}
                            of {state.data.checks.length} checks passed
                        </p>
                    </div>

                    <p className="m-0 text-ui text-re-text-secondary">
                        {state.data.verified
                            ? 'The files in this bundle match the manifest packaged alongside them. This does not authenticate who produced the bundle: the manifest and Merkle root come from the upload itself, so a bundle with replaced files and a regenerated manifest passes the same checks.'
                            : 'At least one file or the Merkle root does not match the manifest packaged inside the bundle.'}
                    </p>

                    <Card variant="outline" className="overflow-hidden">
                        {state.data.checks.map((c, i) => (
                            <div
                                key={i}
                                className="flex items-start gap-3 border-b border-re-border-subtle px-4 py-3 last:border-0"
                            >
                                <div className="mt-0.5 shrink-0">
                                    {c.passed ? (
                                        <CheckCircle2
                                            className="h-4 w-4 text-re-success"
                                            strokeWidth={1.75}
                                            aria-hidden="true"
                                        />
                                    ) : (
                                        <XCircle
                                            className="h-4 w-4 text-re-danger"
                                            strokeWidth={1.75}
                                            aria-hidden="true"
                                        />
                                    )}
                                </div>
                                <div className="min-w-0 flex-1">
                                    <div className="text-ui font-medium text-re-text-primary">
                                        {c.name}
                                    </div>
                                    {c.detail && (
                                        <div className="mt-0.5 break-all font-mono text-[0.8125rem] text-re-text-tertiary">
                                            {c.detail}
                                        </div>
                                    )}
                                </div>
                            </div>
                        ))}
                    </Card>

                    <Card variant="inset" className="p-4 font-mono text-[0.8125rem] text-re-text-tertiary">
                        <div className="break-all">
                            <span className="text-re-text-muted">
                                merkle_root_recomputed:{' '}
                            </span>
                            <span className="text-re-text-primary">
                                {state.data.merkle_root_recomputed}
                            </span>
                        </div>
                        <div className="mt-1 break-all">
                            <span className="text-re-text-muted">
                                timestamp:{' '}
                            </span>
                            <span className="text-re-text-primary">
                                {state.data.timestamp}
                            </span>
                        </div>
                    </Card>

                    <div>
                        <Button variant="secondary" size="lg" onClick={reset}>
                            Verify another bundle
                        </Button>
                    </div>
                </div>
            )}
        </Card>
    );
}

function CopyButton({ text }: { text: string }) {
    const [copied, setCopied] = useState(false);
    return (
        <Button
            type="button"
            variant="ghost"
            size="icon"
            onClick={() => {
                navigator.clipboard.writeText(text);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
            }}
            title="Copy to clipboard"
            aria-label="Copy to clipboard"
        >
            {copied ? (
                <Check className="text-re-success" strokeWidth={1.75} aria-hidden="true" />
            ) : (
                <Copy strokeWidth={1.75} aria-hidden="true" />
            )}
        </Button>
    );
}

export default function VerifyPage() {
    return (
        <div className="re-page min-h-screen">
            {/* ─── Hero ──────────────────────────────────────────────── */}
            <Container className="pb-[60px] pt-20">
                <PageHeader
                    size="hero"
                    eyebrow={
                        <Badge tone="brand">
                            <ShieldCheck className="h-3.5 w-3.5 shrink-0" strokeWidth={1.75} aria-hidden="true" />
                            Open Source • Apache 2.0 License
                        </Badge>
                    }
                    title="Verify, Don't Trust"
                    className="mb-0 border-b-0 pb-0"
                />

                <p className="mt-4 max-w-[68ch] text-body text-re-text-secondary">
                    Every public RegEngine proof bundle carries a{' '}
                    <strong className="font-medium text-re-text-primary">SHA-256 manifest and Merkle root</strong>.
                    Our open-source verification script lets you independently check that
                    the bundle is consistent with its own manifest — without relying on our servers.
                    It does not authenticate who published the bundle.
                </p>

                <div className="mt-8 flex flex-wrap gap-3">
                    <Button asChild size="lg">
                        <a href="/sdk/verify_chain.py" download>
                            <Download strokeWidth={1.75} aria-hidden="true" />
                            Download verify_chain.py
                        </a>
                    </Button>
                    <Button asChild variant="secondary" size="lg">
                        <a href="#how-it-works">
                            <Terminal strokeWidth={1.75} aria-hidden="true" />
                            See How It Works
                        </a>
                    </Button>
                </div>
            </Container>

            {/* ─── Upload widget ─────────────────────────────────────── */}
            <Container
                as="section"
                id="verify-widget"
                className="pb-10 sm:pb-[60px]"
            >
                <div className="mb-6 flex flex-col gap-3">
                    <h2 className="text-heading text-re-text-primary">
                        Verify an export bundle
                    </h2>
                    <p className="m-0 text-ui text-re-text-secondary">
                        Drop in a RegEngine export bundle (the <code className="font-mono text-[0.8125rem] text-re-text-primary">.zip</code> or{' '}
                        <code className="font-mono text-[0.8125rem] text-re-text-primary">.json</code> you exported
                        from your workspace) and we&apos;ll re-run the same self-consistency checks the public
                        verifier runs: file SHA-256 checks, Merkle root match against the bundle&apos;s own
                        manifest, and manifest consistency.
                    </p>
                    <p className="m-0 text-ui text-re-text-secondary">
                        Your file is sent to a public verifier endpoint that runs the same algorithm
                        as the export pipeline — no auth, no email capture. Want to verify entirely
                        offline?{' '}
                        <a href="/sdk/verify_chain.py" download className={PROSE_LINK}>
                            Download verify_chain.py
                        </a>{' '}
                        and run it locally — same algorithm, zero network.
                    </p>
                    <Callout tone="warning">
                        <strong className="font-medium text-re-text-primary">What this does not prove.</strong>{' '}
                        The manifest and Merkle root are read from the uploaded bundle and are treated as
                        untrusted input. A passing result means the bundle is internally self-consistent.
                        It does not verify a signature, compare against a digest RegEngine published
                        separately, or establish that RegEngine produced the bundle. Anyone can replace every
                        file, regenerate the manifest and root, and pass these checks. Do not treat a passing
                        result as proof of publisher identity or provenance.
                    </Callout>
                </div>

                <VerifyWidget />

                <Callout tone="neutral" className="mt-5 flex-wrap items-center">
                    <span className="flex flex-wrap items-center gap-1">
                        <span>Don&apos;t have a bundle yet?</span>
                        <a href="/dashboard/export-jobs" className={cn('inline-flex items-center gap-1', PROSE_LINK)}>
                            Export an audit bundle from your workspace
                            <ExternalLink className="h-3 w-3" strokeWidth={1.75} aria-hidden="true" />
                        </a>
                        <span>and verify it here.</span>
                    </span>
                </Callout>
            </Container>

            {/* ─── Trust Model ───────────────────────────────────────── */}
            <Container as="section" className="pb-10 sm:pb-[60px]">
                <div className="grid grid-cols-[repeat(auto-fit,minmax(260px,1fr))] gap-5">
                    {TRUST_MODEL.map((card) => (
                        <Card key={card.title} className="p-6">
                            <card.Icon className="mb-3 h-5 w-5 text-re-text-muted" strokeWidth={1.75} aria-hidden="true" />
                            <h3 className="mb-2 text-subheading text-re-text-primary">
                                {card.title}
                            </h3>
                            <p className="m-0 text-ui text-re-text-secondary">
                                {card.desc}
                            </p>
                        </Card>
                    ))}
                </div>
            </Container>

            {/* ─── Terminal Output ───────────────────────────────────── */}
            <Container as="section" id="how-it-works" className="pb-[60px]">
                <h2 className="mb-2 text-heading text-re-text-primary">
                    What It Looks Like
                </h2>
                <p className="mb-8 max-w-[68ch] text-ui text-re-text-secondary">
                    Run the script against an audit ZIP. Every evidence file is re-hashed and the
                    Merkle root is rebuilt.
                </p>

                <Card className="overflow-hidden">
                    <CardHeader className="items-center py-2.5">
                        <span className="font-mono text-label uppercase text-re-text-muted">
                            verify_chain.py — bash
                        </span>
                    </CardHeader>
                    <pre className="m-0 max-h-[480px] overflow-auto bg-re-surface-inset p-5 font-mono text-[0.8125rem] leading-6 text-re-text-secondary">
                        {TERMINAL_OUTPUT.split('\n').map((line, i) => (
                            <span key={i} className={transcriptLineClass(line)}>
                                {line}
                                {'\n'}
                            </span>
                        ))}
                    </pre>
                </Card>
            </Container>

            {/* ─── Installation ──────────────────────────────────────── */}
            <Container as="section" className="pb-10 sm:pb-[60px]">
                <h2 className="mb-8 text-heading text-re-text-primary">
                    Get Started in 30 Seconds
                </h2>

                <div className="flex flex-col gap-4">
                    {INSTALL_STEPS.map((step, i) => (
                        <Card key={i} className="flex items-start gap-4 p-5">
                            <span className="mt-0.5 w-5 shrink-0 font-mono text-label tabular-nums text-re-text-muted">
                                {i + 1}
                            </span>
                            <div className="min-w-0 flex-1">
                                <div className="mb-1.5 text-subheading text-re-text-primary">
                                    {step.title}
                                </div>
                                {step.code && (
                                    <Card variant="inset" className="mb-1.5 flex items-center gap-2 py-1 pl-3 pr-1">
                                        <code className="min-w-0 flex-1 overflow-x-auto whitespace-nowrap font-mono text-[0.8125rem] text-re-text-primary">
                                            {step.code}
                                        </code>
                                        <CopyButton text={step.code} />
                                    </Card>
                                )}
                                <p className="m-0 text-ui text-re-text-secondary">{step.desc}</p>
                            </div>
                        </Card>
                    ))}
                </div>
            </Container>

            {/* ─── Code Sample ──────────────────────────────────────── */}
            <Container as="section" className="pb-10 sm:pb-[60px]">
                <h2 className="mb-2 text-heading text-re-text-primary">
                    Usage Examples
                </h2>
                <p className="mb-8 max-w-[68ch] text-ui text-re-text-secondary">
                    Offline bundle verification with a non-zero exit code if anything has drifted.
                </p>

                <Card className="overflow-hidden">
                    <CardHeader className="items-center py-2.5">
                        <span className="font-mono text-label uppercase text-re-text-muted">
                            example_usage.py
                        </span>
                        <CopyButton text={CODE_SAMPLE} />
                    </CardHeader>
                    <pre className="m-0 overflow-auto bg-re-surface-inset p-5 font-mono text-[0.8125rem] leading-6 text-re-text-secondary">
                        {CODE_SAMPLE.split('\n').map((line, i) => (
                            <span
                                key={i}
                                className={
                                    line.startsWith('#') || line.startsWith('"""')
                                        ? 'text-re-text-tertiary'
                                        : 'text-re-text-secondary'
                                }
                            >
                                {line}
                                {'\n'}
                            </span>
                        ))}
                    </pre>
                </Card>
            </Container>

            {/* ─── Hash Algorithm ────────────────────────────────────── */}
            <Container as="section" className="pb-10 sm:pb-[60px]">
                <h2 className="mb-8 text-heading text-re-text-primary">
                    How the Bundle Check Works
                </h2>

                <Card className="overflow-hidden">
                    <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))]">
                        {BUNDLE_CHECK_STEPS.map((s) => (
                            <div
                                key={s.step}
                                className="border-b border-re-border-subtle p-6 last:border-b-0 sm:border-b-0 sm:border-r sm:last:border-r-0"
                            >
                                <div className="mb-3 font-mono text-label tabular-nums text-re-text-muted">
                                    {s.step}
                                </div>
                                <div className="mb-1.5 text-subheading text-re-text-primary">{s.label}</div>
                                <div className="text-ui text-re-text-secondary">{s.detail}</div>
                            </div>
                        ))}
                    </div>
                </Card>
            </Container>

            {/* ─── Canonical Fields Table ────────────────────────────── */}
            <Container as="section" className="pb-10 sm:pb-[60px]">
                <h2 className="mb-5 text-heading text-re-text-primary">
                    Manifest Fields (Hash Inputs)
                </h2>

                <DataTable
                    columns={MANIFEST_COLUMNS}
                    data={MANIFEST_FIELDS}
                    caption="Manifest Fields (Hash Inputs)"
                    rowKey={(row) => row.field}
                />
            </Container>

            {/* ─── CTA Footer ────────────────────────────────────────── */}
            <Container as="section" className="pb-20">
                <Card className="px-8 py-12">
                    <h2 className="mb-3 text-heading text-re-text-primary">
                        Math Trust &gt; Process Trust
                    </h2>
                    <p className="mb-7 max-w-[68ch] text-ui text-re-text-secondary">
                        RegEngine adds hash-based consistency checks on top of standard compliance controls.
                        SHA-256 hashing lets you confirm a bundle matches its own manifest independently —
                        whether or not you require a SOC 2 report. It is not a signature and does not
                        authenticate the publisher.
                    </p>

                    <div className="flex flex-wrap gap-3">
                        <Button asChild variant="secondary" size="lg">
                            <a href="/sdk/verify_chain.py" download>
                                <Download strokeWidth={1.75} aria-hidden="true" />
                                Download Script
                            </a>
                        </Button>
                        <Button asChild variant="ghost" size="lg">
                            <a href="/tools/ftl-checker">
                                Check Your FTL Coverage
                                <ExternalLink strokeWidth={1.75} aria-hidden="true" />
                            </a>
                        </Button>
                    </div>
                </Card>

                {/* Fine print */}
                <p className="mt-6 text-small text-re-text-tertiary">
                    verify_chain.py v1.0.0 • Apache 2.0 License • Python 3.8+ • Zero dependencies for offline mode
                </p>
            </Container>
        </div>
    );
}
