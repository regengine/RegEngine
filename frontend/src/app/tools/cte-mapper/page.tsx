import { Metadata } from "next";
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
                <CTEMapperClient />
            </div>
        </div>
    );
}
