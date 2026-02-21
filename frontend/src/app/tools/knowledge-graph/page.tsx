import { Metadata } from "next";
import { KnowledgeGraphClient } from "./components/KnowledgeGraphClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Supply Chain Knowledge Graph | RegEngine",
    description: "Visually map and trace your high-integrity FSMA 204 supply chain using our interactive graphing builder.",
    openGraph: {
        title: "Supply Chain Knowledge Graph — RegEngine",
        description: "Interactive mapping tool for FSMA 204 supply chains.",
        type: "website",
        url: "https://regengine.vercel.app/tools/knowledge-graph",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Supply Chain Knowledge Graph",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Interactive visual builder for designing FSMA 204 compliant supply chain networks.",
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

export default function KnowledgeGraphPage() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <JSONLD data={jsonLd} />
            <KnowledgeGraphClient />
        </Suspense>
    );
}
