import { Metadata } from "next";
import { Suspense } from "react";
import { CTEMapperClient } from "./components/CTEMapperClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "CTE Coverage Mapper | FSMA 204 Supply Chain Mapping | RegEngine",
    description: "Visualize your supply chain nodes to see exactly who owes whom data for every transaction under FSMA 204. Map your Critical Tracking Events (CTEs) today.",
    openGraph: {
        title: "CTE Coverage Mapper — RegEngine",
        description: "Map your FSMA 204 supply chain data flow.",
        type: "website",
        url: "https://regengine.vercel.app/tools/cte-mapper",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "CTE Coverage Mapper",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Supply chain node mapping tool for FSMA 204 Critical Tracking Events (CTE).",
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

function CTEMapperFallback() {
    return (
        <div className="flex flex-col items-center justify-center gap-6 py-32 px-6 text-center">
            <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><rect x="3" y="3" width="7" height="7" rx="1" strokeWidth="1.5"/><rect x="14" y="3" width="7" height="7" rx="1" strokeWidth="1.5"/><rect x="3" y="14" width="7" height="7" rx="1" strokeWidth="1.5"/><path d="M17.5 17.5h.01M14 17.5h3.5m0 0V14" strokeWidth="1.5" strokeLinecap="round"/></svg>
            </div>
            <div>
                <h1 className="text-xl font-bold text-[var(--re-text-primary)] mb-2">CTE Coverage Mapper</h1>
                <p className="text-sm text-[var(--re-text-muted)] max-w-sm">Visualize your supply chain nodes and see exactly which Critical Tracking Events and Key Data Elements each link in your chain is responsible for under FSMA 204.</p>
            </div>
            <div className="flex gap-2 items-center text-xs text-[var(--re-text-disabled)]">
                <div className="w-3 h-3 rounded-full border-2 border-emerald-400 border-t-transparent animate-spin" />
                Loading mapper…
            </div>
        </div>
    );
}

export default function CTEMapperPage() {
    return (
        <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
            <JSONLD data={jsonLd} />
            <div className="max-w-7xl mx-auto">
                <Breadcrumbs
                    items={[
                        { label: "Free Tools", href: "/tools" },
                        { label: "CTE Coverage Mapper" }
                    ]}
                />
                <Suspense fallback={<CTEMapperFallback />}>
                    <CTEMapperClient />
                </Suspense>
            </div>
        </div>
    );
}
