import type { Metadata } from "next";
import Link from "next/link";
import { Archive, Terminal } from "lucide-react";
import { Container } from "@/components/layout/container";
import { PageHeader } from "@/components/layout/page-header";
import { Section } from "@/components/layout/section";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";

export const metadata: Metadata = {
    title: "Proof | RegEngine",
    description:
        "No public proof artifacts are published yet. Verify an audit bundle exported from your own RegEngine workspace with the open-source verifier.",
    openGraph: {
        title: "Verify RegEngine bundles yourself",
        description:
            "No public proof artifacts are published yet. Use the open-source verifier on your own exported bundle.",
        url: "https://regengine.co/proof",
        type: "website",
    },
};

export default function ProofPage() {
    return (
        <div className="re-page min-h-screen">
            <Container className="pb-10 pt-12 md:pt-16">
                <PageHeader
                    size="hero"
                    eyebrow={<span className="font-mono uppercase">Proof</span>}
                    title="Verify RegEngine bundles yourself."
                    description="RegEngine doesn't publish its own artifacts here. To check RegEngine's output, export an audit bundle from your own workspace and run the open-source verifier on it."
                    className="mb-0 border-b-0 pb-0"
                />
            </Container>

            <Section id="artifacts" width="marketing">
                <EmptyState
                    icon={Archive}
                    title="No public artifacts are published yet."
                    titleAs="h2"
                    description="When real, reviewable artifacts are available they will be listed here. Until then, verify a bundle you exported yourself."
                    action={
                        <Button asChild variant="secondary">
                            <Link href="/verify">Verify your own bundle</Link>
                        </Button>
                    }
                />
            </Section>

            <Section width="marketing">
                <div>
                    <p className="mb-4 font-mono text-label uppercase text-re-text-muted">Run it yourself</p>
                    <h2 className="font-display text-heading-lg text-re-text-primary">Inspect the Python verifier.</h2>
                    <p className="mt-5 max-w-[68ch] text-ui text-re-text-secondary">
                        <code className="font-mono text-[0.8125rem]">verify_chain.py</code> reads the manifest, recomputes each declared file&apos;s SHA-256, and rebuilds the Merkle root using the same algorithm RegEngine ships in <code className="font-mono text-[0.8125rem]">services/shared/merkle_tree.py</code>. If those values disagree with the included manifest, the script exits non-zero. These checks establish internal consistency; they do not authenticate the issuer or establish that the source data is accurate.
                    </p>
                    <Button asChild variant="secondary" size="lg" className="mt-6">
                        <Link href="/sdk/verify_chain.py">
                            <Terminal aria-hidden="true" strokeWidth={1.75} /> Open verify_chain.py
                        </Link>
                    </Button>
                </div>
            </Section>
        </div>
    );
}
