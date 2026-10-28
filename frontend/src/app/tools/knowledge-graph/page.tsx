import { Metadata } from "next";
import { KnowledgeGraphClient } from "./components/KnowledgeGraphClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { FeatureNotEnabled } from "@/components/experimental/FeatureNotEnabled";
import { isExperimentalToolEnabled } from "@/lib/experimental-features";
import { Container } from "@/components/layout/container";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "Supply Chain Knowledge Graph | FSMA 204 Network Mapper | RegEngine",
    description: "Build an interactive visual map of your FSMA 204 supply chain. Connect growers, coolers, packhouses, and distributors to identify Critical Tracking Event (CTE) and Key Data Element (KDE) coverage gaps. Free.",
    alternates: {
        canonical: "https://regengine.co/tools/knowledge-graph",
    },
    openGraph: {
        title: "Supply Chain Knowledge Graph | RegEngine",
        description: "Interactively map your FSMA 204 supply chain nodes and identify Critical Tracking Event (CTE) and Key Data Element (KDE) coverage gaps. Free tool.",
        type: "website",
        url: "https://regengine.co/tools/knowledge-graph",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Supply Chain Knowledge Graph",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Interactive visual builder for mapping supply chain networks for FSMA 204 recordkeeping.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

function KnowledgeGraphFallback() {
    return (
        <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
            <Container width="tool">
                <div className="border-b border-re-border-subtle pb-5">
                    <h1 className="text-title text-re-text-primary">Supply Chain Knowledge Graph</h1>
                    <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">Interactively map your FSMA 204 supply chain nodes, including growers, coolers, packhouses, distributors, and retailers, and visualize which Critical Tracking Event (CTE) and Key Data Element (KDE) requirements each link has. Identify coverage gaps before they become compliance gaps.</p>
                </div>
                <h2 className="mt-6 text-heading text-re-text-primary">Node Types You Can Map</h2>
                <div className="mt-4 flex flex-wrap gap-2">
                    {["Grower / Farm", "Cooler", "Packhouse", "First Land-Based Receiver (Seafood)", "Distributor / DC", "Processor", "Retailer"].map((node) => (
                        <Badge key={node} tone="neutral">{node}</Badge>
                    ))}
                </div>
                <div className="mt-6 space-y-3" role="status" aria-live="polite">
                    <Skeleton className="h-64 w-full" />
                    <p className="pt-2 text-small text-re-text-muted">Loading graph builder…</p>
                </div>
            </Container>
        </div>
    );
}

export default function KnowledgeGraphPage() {
    if (!isExperimentalToolEnabled("knowledge-graph")) {
        return (
            <FeatureNotEnabled
                featureName="Supply Chain Knowledge Graph"
                backHref="/tools"
                backLabel="Back to free tools"
            />
        );
    }
    return (
        <>
            <Suspense fallback={<KnowledgeGraphFallback />}>
                <JSONLD data={jsonLd} />
                <EmailGate toolName="knowledge-graph">
                    <KnowledgeGraphClient />
                </EmailGate>
            </Suspense>
            <RelatedTools tools={[
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Map Critical Tracking Events across your supply chain nodes for FSMA 204 compliance." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Check which food products in your network are on the FDA Traceability List." },
                { href: "/tools/fsma-unified", title: "Unified Dashboard", description: "Combine anomaly detection and knowledge graph views in one compliance dashboard." },
            ]} />
        </>
    );
}
