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

function KnowledgeGraphFallback() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] flex flex-col items-center justify-center gap-6 px-6 text-center">
            <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="5" r="2" strokeWidth="1.5"/><circle cx="5" cy="19" r="2" strokeWidth="1.5"/><circle cx="19" cy="19" r="2" strokeWidth="1.5"/><path d="M12 7v4M12 11l-5 6M12 11l5 6" strokeWidth="1.5" strokeLinecap="round"/></svg>
            </div>
            <div>
                <h1 className="text-xl font-bold text-[var(--re-text-primary)] mb-2">Supply Chain Knowledge Graph</h1>
                <p className="text-sm text-[var(--re-text-muted)] max-w-sm">Interactively map your FSMA 204 supply chain nodes — growers, distributors, retailers — and visualize which CTEs and KDEs each link requires.</p>
            </div>
            <div className="flex gap-2 items-center text-xs text-[var(--re-text-disabled)]">
                <div className="w-3 h-3 rounded-full border-2 border-emerald-400 border-t-transparent animate-spin" />
                Loading graph builder…
            </div>
        </div>
    );
}

export default function KnowledgeGraphPage() {
    return (
        <Suspense fallback={<KnowledgeGraphFallback />}>
            <JSONLD data={jsonLd} />
            <KnowledgeGraphClient />
        </Suspense>
    );
}
