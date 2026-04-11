import { Metadata } from "next";
import { UnifiedDashboardClient } from "./components/UnifiedDashboardClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "FSMA 204 Unified Dashboard | Anomaly Detection & Knowledge Graph | RegEngine",
    description: "Unified command center for FSMA 204 compliance. Monitor supply chain anomalies, explore knowledge graphs, and benchmark readiness — all in one free dashboard.",
    alternates: {
        canonical: "https://regengine.co/tools/fsma-unified",
    },
    openGraph: {
        title: "FSMA 204 Unified Dashboard — RegEngine",
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
    "offers": {
        "@type": "Offer",
        "price": "0",
        "priceCurrency": "USD"
    },
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

export default function UnifiedDashboardPage() {
    return (
        <>
            <Suspense fallback={
                <div className="min-h-screen bg-[var(--re-surface-base)] px-6 py-16">
                    <div className="max-w-2xl mx-auto text-center">
                        <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-3">Unified FSMA Dashboard</h1>
                        <p className="text-sm text-[var(--re-text-muted)] max-w-lg mx-auto mb-4 leading-relaxed">A consolidated command center for FSMA 204 compliance. Combines anomaly detection, supply chain knowledge graphs, and compliance scoring into a single view. Monitor your traceability data integrity in real time.</p>
                        <div className="flex gap-2 items-center justify-center text-xs text-[var(--re-text-disabled)]">
                            <div className="w-3 h-3 rounded-full border-2 border-re-brand border-t-transparent animate-spin" />
                            Loading dashboard…
                        </div>
                    </div>
                </div>
            }>
                <JSONLD data={jsonLd} />
                <EmailGate toolName="fsma-unified">
                    <UnifiedDashboardClient />
                </EmailGate>
            </Suspense>
            <RelatedTools tools={[
                { href: "/tools/knowledge-graph", title: "Knowledge Graph", description: "Build an interactive visual map of your FSMA 204 supply chain nodes and coverage gaps." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Check if your food products are on the FDA Food Traceability List." },
                { href: "/tools/drill-simulator", title: "24-Hour Drill Simulator", description: "Run a scenario-based FDA outbreak drill to test your record retrieval speed." },
            ]} />
        </>
    );
}
