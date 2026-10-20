import { Metadata } from "next";
import { UnifiedDashboardClient } from "./components/UnifiedDashboardClient";
import { Suspense } from "react";
import { Container } from "@/components/layout/container";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Skeleton } from "@/components/ui/skeleton";
import { filterExperimentalToolLinks } from "@/lib/experimental-features";

export const metadata: Metadata = {
    title: "FSMA 204 Unified Dashboard | Anomaly Detection & Knowledge Graph | RegEngine",
    description: "Unified command center for FSMA 204 compliance. Monitor supply chain anomalies and explore knowledge graphs in one free dashboard.",
    alternates: {
        canonical: "https://regengine.co/tools/fsma-unified",
    },
    openGraph: {
        title: "FSMA 204 Unified Dashboard | RegEngine",
        description: "Monitor FSMA 204 supply chain anomalies and explore knowledge graphs from one free compliance dashboard.",
        type: "website",
        url: "https://regengine.co/tools/fsma-unified",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Unified FSMA Dashboard",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Consolidated FSMA 204 command center for anomaly detection and supply chain mapping.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

function UnifiedDashboardFallback() {
    return (
        <div className="min-h-screen bg-re-surface-base py-6 sm:py-8" aria-busy="true">
            <Container width="tool">
                <div className="mx-auto max-w-2xl text-center">
                    <h1 className="text-title text-re-text-primary">Unified FSMA Dashboard</h1>
                    <p className="mx-auto mt-3 max-w-[70ch] text-ui text-re-text-secondary">A consolidated command center for FSMA 204 compliance. Combines anomaly detection, supply chain knowledge graphs, and compliance scoring into a single view. Monitor your traceability data integrity in real time.</p>
                </div>
                <div className="mt-8 space-y-4">
                    <Skeleton className="h-10 w-1/3 rounded-md" />
                    <Skeleton className="h-64 w-full rounded-lg" />
                </div>
                <p className="mt-4 text-center text-small text-re-text-muted">
                    Loading dashboard…
                </p>
            </Container>
        </div>
    );
}

export default function UnifiedDashboardPage() {
    return (
        <>
            <Suspense fallback={<UnifiedDashboardFallback />}>
                <JSONLD data={jsonLd} />
                <EmailGate toolName="fsma-unified">
                    <UnifiedDashboardClient />
                </EmailGate>
            </Suspense>
            <RelatedTools tools={filterExperimentalToolLinks([
                { href: "/tools/knowledge-graph", title: "Knowledge Graph", description: "Build an interactive visual map of your FSMA 204 supply chain nodes and coverage gaps." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Check if your food products are on the FDA Food Traceability List." },
                { href: "/tools/drill-simulator", title: "24 Hour Drill Simulator", description: "Run a scenario-based FDA outbreak drill to test your record retrieval speed." },
            ])} />
        </>
    );
}
