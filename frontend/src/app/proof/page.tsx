import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Download, FileJson, FileSpreadsheet, Hash, Terminal } from "lucide-react";

export const metadata: Metadata = {
    title: "Proof | RegEngine",
    description:
        "Download three real RegEngine artifacts — FSMA 204 sortable spreadsheet, EPCIS 2.0 JSON-LD export, and a Merkle-rooted audit bundle — without signing up.",
    openGraph: {
        title: "Verify RegEngine without signing up",
        description:
            "Three downloadable artifacts: FSMA 204 spreadsheet, EPCIS 2.0 JSON-LD, and a Merkle-rooted audit bundle.",
        url: "https://regengine.co/proof",
        type: "website",
    },
};

type Artifact = {
    name: string;
    href: string;
    filename: string;
    sizeBytes: number;
    icon: typeof FileSpreadsheet;
    summary: string;
    why: string;
    formatLabel: string;
};

const ARTIFACTS: Artifact[] = [
    {
        name: "FSMA 204 sortable spreadsheet",
        href: "/proof/fsma-204-sample.csv",
        filename: "fsma-204-sample.csv",
        sizeBytes: 1524,
        icon: FileSpreadsheet,
        formatLabel: "CSV · sortable",
        summary:
            "A complete recall lookback for one leafy-greens lot, exported in the FDA's preferred sortable layout.",
        why: "FDA's 21 CFR 1.1455 demands a sortable spreadsheet within 24 hours of a recall request. This is the exact shape inspectors expect — every required KDE column populated for every CTE row.",
    },
    {
        name: "EPCIS 2.0 JSON-LD export",
        href: "/proof/epcis-sample.jsonld",
        filename: "epcis-sample.jsonld",
        sizeBytes: 3039,
        icon: FileJson,
        formatLabel: "EPCIS 2.0 JSON-LD",
        summary:
            "A three-event payload covering harvesting, initial packing, and shipping for one traceability lot code.",
        why: "Walmart, Kroger, Sysco, and US Foods are converging on EPCIS 2.0 for supplier ingest. Confirm that what RegEngine emits validates against your retailer's onboarding tests before you sign a contract.",
    },
    {
        name: "Merkle-rooted audit bundle",
        href: "/proof/audit-bundle.zip",
        filename: "audit-bundle.zip",
        sizeBytes: 2266,
        icon: Hash,
        formatLabel: "ZIP · SHA-256 + Merkle root",
        summary:
            "The CSV and EPCIS payload plus a manifest.json with per-file SHA-256 hashes and a Merkle root computed by production code.",
        why: "Compare each declared file's SHA-256 hash and the bundle's Merkle root with its included manifest. These checks establish internal consistency; they do not authenticate the issuer or establish that the source data is accurate.",
    },
];

function formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

export default function ProofPage() {
    return (
        <main className="re-page min-h-screen text-[var(--re-text-secondary)]">
            <section className="re-container grid gap-10 pb-14 pt-12 md:grid-cols-[0.85fr_1fr] md:pb-20 md:pt-18">
                <div>
                    <p className="re-label mb-5">Proof</p>
                    <h1 className="max-w-[680px] text-[clamp(42px,7vw,78px)] font-semibold leading-[0.96]">
                        Verify RegEngine without signing up.
                    </h1>
                    <p className="mt-6 max-w-[590px] text-[17px] leading-7 text-[var(--re-text-muted)]">
                        Three artifacts. No email gate, no demo call. Download the files, open them in your tools, and check the hashes yourself. If the output does not match the claim, the product fails — and you have the receipts.
                    </p>
                    <div className="mt-8 flex flex-wrap gap-3">
                        <Link
                            href="#artifacts"
                            className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] bg-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-surface-base)]"
                        >
                            See the files <ArrowRight className="h-4 w-4" />
                        </Link>
                        <Link
                            href="/sdk/verify_chain.py"
                            className="inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-text-primary)]"
                        >
                            Get the verifier
                        </Link>
                    </div>
                </div>
                <div className="re-panel overflow-hidden">
                    <div className="border-b border-[var(--re-surface-border)] p-4">
                        <p className="re-label">Verifier output</p>
                    </div>
                    <div className="bg-[var(--re-text-primary)] p-5 font-mono text-[12px] leading-6 text-[var(--re-surface-base)]">
                        <p>$ unzip -p audit-bundle.zip manifest.json | jq .merkle.root</p>
                        <p className="mt-3 text-[#8fd19e]">&quot;a320428f40579ec9eaea1a640614d26649f2111a0cc6f6b379003d25278bb6d2&quot;</p>
                        <p className="mt-3">$ python verify_chain.py audit-bundle.zip</p>
                        <p className="mt-3 text-[#8fd19e]">manifest: ok</p>
                        <p className="text-[#8fd19e]">files: 2 / 2 sha256 matches</p>
                        <p className="text-[#f1c36d]">merkle: root recomputed and matched</p>
                        <p className="mt-3 text-[#d8d2c5]">result: bundle intact</p>
                    </div>
                </div>
            </section>

            <section id="artifacts" className="re-section">
                <div className="re-container">
                    <p className="re-label mb-4">Downloads</p>
                    <h2 className="max-w-[640px] text-3xl font-semibold leading-tight">
                        Three artifacts. Open them in your own tools.
                    </h2>
                    <div className="mt-10 grid gap-5 md:grid-cols-3">
                        {ARTIFACTS.map(({ name, href, filename, sizeBytes, icon: Icon, summary, why, formatLabel }) => (
                            <article
                                key={filename}
                                className="re-panel flex h-full flex-col p-6"
                            >
                                <Icon className="mb-6 h-6 w-6 text-[var(--re-text-primary)]" aria-hidden="true" />
                                <h3 className="text-lg font-semibold text-[var(--re-text-primary)]">
                                    {name}
                                </h3>
                                <p className="mt-3 text-sm leading-6 text-[var(--re-text-muted)]">
                                    {summary}
                                </p>
                                <dl className="mt-5 grid grid-cols-2 gap-3 border-t border-[var(--re-surface-border)] pt-4 font-mono text-[11px] uppercase tracking-[0.06em] text-[var(--re-text-muted)]">
                                    <div>
                                        <dt>Format</dt>
                                        <dd className="mt-1 text-[var(--re-text-secondary)] normal-case tracking-normal">{formatLabel}</dd>
                                    </div>
                                    <div>
                                        <dt>Size</dt>
                                        <dd className="mt-1 text-[var(--re-text-secondary)] normal-case tracking-normal">{formatSize(sizeBytes)}</dd>
                                    </div>
                                </dl>
                                <a
                                    href={href}
                                    download={filename}
                                    className="mt-6 inline-flex h-11 items-center justify-center gap-2 border border-[var(--re-text-primary)] bg-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-surface-base)]"
                                >
                                    <Download className="h-4 w-4" /> Download {filename}
                                </a>
                                <div className="mt-5 border-t border-[var(--re-surface-border)] pt-4">
                                    <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-[var(--re-text-muted)]">Why this matters</p>
                                    <p className="mt-2 text-sm leading-6 text-[var(--re-text-muted)]">{why}</p>
                                </div>
                            </article>
                        ))}
                    </div>
                </div>
            </section>

            <section className="re-section">
                <div className="re-container grid gap-8 md:grid-cols-[0.75fr_1fr]">
                    <div>
                        <p className="re-label mb-4">Run it yourself</p>
                        <h2 className="text-3xl font-semibold leading-tight">
                            Inspect the Python verifier.
                        </h2>
                        <p className="mt-5 text-sm leading-6 text-[var(--re-text-muted)]">
                            <code className="font-mono text-[12px]">verify_chain.py</code> reads the manifest, recomputes each declared file&apos;s SHA-256, and rebuilds the Merkle root using the same algorithm RegEngine ships in <code className="font-mono text-[12px]">services/shared/merkle_tree.py</code>. If those values disagree with the included manifest, the script exits non-zero.
                        </p>
                        <Link
                            href="/sdk/verify_chain.py"
                            className="mt-6 inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-text-primary)]"
                        >
                            <Terminal className="h-4 w-4" /> Open verify_chain.py
                        </Link>
                    </div>
                    <div className="re-panel overflow-hidden">
                        <div className="border-b border-[var(--re-surface-border)] p-4">
                            <p className="re-label">Three-step verify</p>
                        </div>
                        <div className="bg-[var(--re-text-primary)] p-5 font-mono text-[12px] leading-6 text-[var(--re-surface-base)]">
                            <p className="text-[#8fd19e]"># 1. Download the bundle and the verifier</p>
                            <p>curl -O https://regengine.co/proof/audit-bundle.zip</p>
                            <p>curl -O https://regengine.co/sdk/verify_chain.py</p>
                            <p className="mt-3 text-[#8fd19e]"># 2. Run it</p>
                            <p>python verify_chain.py audit-bundle.zip</p>
                            <p className="mt-3 text-[#8fd19e]"># 3. (Optional) Recompute the leaf yourself</p>
                            <p>shasum -a 256 fsma-204-sample.csv</p>
                        </div>
                    </div>
                </div>
            </section>

            <section className="re-section">
                <div className="re-container grid gap-8 md:grid-cols-[0.75fr_1fr]">
                    <div>
                        <p className="re-label mb-4">Watch it fail</p>
                        <h2 className="text-3xl font-semibold leading-tight">
                            A tampered bundle is published next to the real one.
                        </h2>
                        <p className="mt-5 text-sm leading-6 text-[var(--re-text-muted)]">
                            <code className="font-mono text-[12px]">audit-bundle-tampered.zip</code> contains a changed CSV while the manifest&apos;s declared hash remains unchanged. Run the verifier against it and watch it exit non-zero. This demonstrates detection of changed file bytes against an unchanged manifest; replacing both the file and manifest is outside this check.
                        </p>
                        <Link
                            href="/proof/audit-bundle-tampered.zip"
                            className="mt-6 inline-flex h-11 items-center gap-2 border border-[var(--re-text-primary)] px-5 text-[13px] font-semibold text-[var(--re-text-primary)]"
                        >
                            <Download className="h-4 w-4" /> Download audit-bundle-tampered.zip
                        </Link>
                    </div>
                    <div className="re-panel overflow-hidden">
                        <div className="border-b border-[var(--re-surface-border)] p-4">
                            <p className="re-label">Tampered output</p>
                        </div>
                        <div className="bg-[var(--re-text-primary)] p-5 font-mono text-[12px] leading-6 text-[var(--re-surface-base)]">
                            <p>$ python verify_chain.py audit-bundle-tampered.zip</p>
                            <p className="mt-3 text-[#8fd19e]">manifest: ok</p>
                            <p className="text-[#e58c8c]">verify: FAILED — fsma-204-sample.csv: sha256 mismatch</p>
                            <p className="text-[#e58c8c]">result: bundle TAMPERED</p>
                            <p className="mt-3 text-[#d8d2c5]">$ echo $?</p>
                            <p className="text-[#d8d2c5]">1</p>
                        </div>
                    </div>
                </div>
            </section>

            <section className="re-section">
                <div className="re-container">
                    <p className="re-label mb-4">Changelog</p>
                    <div className="re-panel p-6 text-sm leading-6 text-[var(--re-text-muted)]">
                        <p className="font-mono text-[11px] uppercase tracking-[0.06em] text-[var(--re-text-secondary)]">2026-05-09 — verifier mismatch found and fixed</p>
                        <p className="mt-3">
                            A reader running the recipe on this page got an argparse error instead of a verification. The verifier we&apos;d shipped didn&apos;t match the bundle we&apos;d shipped — the hashes were correct, but the script next to them read JSON, not the zip the page describes.
                        </p>
                        <p className="mt-3">
                            Replaced with a verifier that opens the zip, recomputes every per-file SHA-256, and rebuilds the Merkle root using the same algorithm RegEngine ships in <code className="font-mono text-[12px]">services/shared/merkle_tree.py</code>. Added the EPCIS payload to <code className="font-mono text-[12px]">manifest.json</code>, added a <code className="font-mono text-[12px]">build</code> block (commit, generated_at, release), and published <code className="font-mono text-[12px]">audit-bundle-tampered.zip</code> so anyone can watch the new verifier fail closed.
                        </p>
                        <p className="mt-3">
                            If you found the original bug before we did — thank you. That&apos;s the system working.
                        </p>
                    </div>
                </div>
            </section>

            <div className="sticky bottom-0 z-[3] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)]/95 backdrop-blur">
                <div className="re-container flex flex-wrap items-center justify-between gap-3 py-3 text-[12px] text-[var(--re-text-muted)]">
                    <span>
                        All artifacts are synthetic. They are regenerated by production code on every release.
                    </span>
                    <code className="font-mono text-[11px] text-[var(--re-text-secondary)]">
                        python verify_chain.py audit-bundle.zip
                    </code>
                </div>
            </div>
        </main>
    );
}
