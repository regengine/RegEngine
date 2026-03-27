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
        url: "https://www.regengine.co/tools/knowledge-graph",
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
        <div className="min-h-screen bg-[var(--re-surface-base)] px-6 py-16">
            <div className="max-w-2xl mx-auto text-center mb-12">
                <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto mb-6">
                    <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><circle cx="12" cy="5" r="2" strokeWidth="1.5"/><circle cx="5" cy="19" r="2" strokeWidth="1.5"/><circle cx="19" cy="19" r="2" strokeWidth="1.5"/><path d="M12 7v4M12 11l-5 6M12 11l5 6" strokeWidth="1.5" strokeLinecap="round"/></svg>
                </div>
                <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-3">Supply Chain Knowledge Graph</h1>
                <p className="text-sm text-[var(--re-text-muted)] max-w-lg mx-auto leading-relaxed">Interactively map your FSMA 204 supply chain nodes — growers, coolers, packhouses, distributors, retailers — and visualize which Critical Tracking Events and Key Data Elements each link requires. Identify coverage gaps before they become compliance gaps.</p>
            </div>
            <div className="max-w-2xl mx-auto">
                <h2 className="text-lg font-semibold text-[var(--re-text-primary)] mb-4">Node Types You Can Map</h2>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-8">
                    {["Grower / Farm", "Cooler", "Packhouse", "Distributor / DC", "Processor", "Retailer"].map((node) => (
                        <div key={node} className="rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-3 text-center">
                            <span className="text-xs font-medium text-emerald-400">{node}</span>
                        </div>
                    ))}
                </div>
                <div className="flex gap-2 items-center justify-center text-xs text-[var(--re-text-disabled)]">
                    <div className="w-3 h-3 rounded-full border-2 border-emerald-400 border-t-transparent animate-spin" />
                    Loading graph builder…
                </div>
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
