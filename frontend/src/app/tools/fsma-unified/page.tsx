import { Metadata } from "next";
import { UnifiedDashboardClient } from "./components/UnifiedDashboardClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Unified FSMA Dashboard | Anomaly Simulation & Knowledge Graph | RegEngine",
    description: "Benchmark your facility's FSMA 204 readiness with our unified dashboard. Features high-integrity anomaly detection and supply chain knowledge graphs.",
    openGraph: {
        title: "Unified FSMA Dashboard — RegEngine",
        description: "Anomaly Simulation & Knowledge Graph technical demos.",
        type: "website",
        url: "https://regengine.vercel.app/tools/fsma-unified",
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
        <Suspense fallback={<div>Loading...</div>}>
            <JSONLD data={jsonLd} />
            <UnifiedDashboardClient />
        </Suspense>
    );
}
