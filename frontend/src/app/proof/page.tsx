import type { Metadata } from "next";
import { FileArchive, Terminal } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

export const metadata: Metadata = {
    title: "Proof | RegEngine",
    description:
        "Inspect the open-source Python verifier RegEngine uses to check audit bundles. Exports include FSMA 204 sortable spreadsheets and EPCIS 2.0 JSON-LD (Preview).",
    openGraph: {
        title: "Verify RegEngine without signing up",
        description:
            "Inspect the open-source Python verifier RegEngine uses to check audit bundles.",
        url: "https://regengine.co/proof",
        type: "website",
    },
};

export default function ProofPage() {
    return (
        <div className="re-page min-h-screen">
            <Container className="pb-14 pt-12 md:pb-20 md:pt-16">
                <PageHeader
                    size="hero"
                    eyebrow={<span className="font-mono uppercase">Proof</span>}
                    title="Verify RegEngine without signing up."
                    description="No email gate, no sales call. Read the verifier, run it on a bundle exported from your own workspace, and check the hashes yourself."
                    className="mb-0 border-b-0 pb-0"
                />
            </Container>

            <Section
                id="artifacts"
                width="marketing"
                eyebrow={<span className="font-mono uppercase">Downloads</span>}
                title="Public artifacts"
            >
                <EmptyState
                    icon={FileArchive}
                    titleAs="h3"
                    title="No public artifacts are published right now."
                    description="Exports from your own workspace (FSMA 204 sortable spreadsheet, EPCIS 2.0 JSON-LD (Preview), and the audit bundle) can be checked with the verifier below."
                />
            </Section>

            <Section width="marketing">
                <div className="max-w-2xl">
                    <p className="mb-4 font-mono text-label uppercase text-re-text-muted">Run it yourself</p>
                    <h2 className="font-display text-heading-lg text-re-text-primary">
                        Inspect the Python verifier.
                    </h2>
                    <p className="mt-5 text-ui text-re-text-secondary">
                        <code className="font-mono text-[0.8125rem]">verify_chain.py</code> reads the manifest, recomputes each declared file&apos;s SHA-256, and rebuilds the Merkle root using the same algorithm RegEngine ships in <code className="font-mono text-[0.8125rem]">services/shared/merkle_tree.py</code>. If those values disagree with the included manifest, the script exits non-zero.
                    </p>
                    <p className="mt-3 text-ui text-re-text-secondary">
                        These checks establish internal consistency; they do not authenticate the issuer or establish that the source data is accurate.
                    </p>
                    <Button asChild variant="secondary" size="lg" className="mt-6">
                        <a href="/sdk/verify_chain.py" download>
                            <Terminal aria-hidden="true" strokeWidth={1.75} /> Open verify_chain.py
                        </a>
                    </Button>
                </div>
            </Section>
        </div>
    );
}
